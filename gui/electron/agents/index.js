'use strict';
// エージェントの窓（Electron の main）：エージェントを、このアプリの小さな窓のタブとして動かす。
// - タブ＝1つのエージェント（作業空間のエージェント：`ecobuild -C <場所> agent start --here`。コンテナならその中で動く。
//   準備・鍵の受け渡しは ecobuild がする）。端末は node-pty。状態を読むため、main 側にも見えない端末（@xterm/headless）を持つ。
// - 番号は 1 から続く（閉じるとそれより大きい番号が詰まる）。窓はいくつでも持て、タブは窓の間で動かせる。
// - 窓は枠なし。最前面の表示は窓ごとに 常に → 自動 → オフ（自動は、返答が届いたとき・選んだときだけ前に出る）。
// - 状態（考え中・裏で実行中・選択肢・待機中・終了）は画面を読んで決める（screen.js）。モデル・使用量の制限・返答の終わりは、
//   エージェントが書き出すもの（status.js。ecobuild が置き場所を端末の見えない印で知らせる）。
// - 最小化すると窓は隠れ、右下の表示（dock.js）になる。返答の知らせは Windows の通知か、右下のカードと音（notify）。
// 画面（window.html）とのやり取りは agents/preload.js。ほかの窓（作業空間）からは preload.js の agents.open で開く。
const {app, BrowserWindow, Notification, ipcMain, screen: display} = require('electron');
const fs = require('fs');
const path = require('path');
const pty = require('node-pty');
const {Terminal} = require('@xterm/headless');
const parser = require('./screen');
const status = require('./status');
const dock = require('./dock');

const HISTORY_LIMIT = 2 * 1024 * 1024;   // 後から開いた窓に流し直す出力（文字数）
const POLL_MS = 1500;                     // 状態を読み直す間隔
const TOPMOST = ['always', 'auto', 'off'];
const WINDOW_SIZE = {width: 760, height: 520};
const STATE_FILE = () => path.join(app.getPath('userData'), 'agents.json');
const ICON = path.join(__dirname, '..', '..', 'icon.ico');
// 返答の知らせ。style：windows（Windows の通知。音も Windows の設定どおり）・ecobuild（右下のカードと音）・off。
// hold：右下に返答を出しておく時間（ミリ秒。-1 は消さない）
const NOTIFY_DEFAULTS = {style: 'windows', sound: 'chime', volume: 0.6, hold: 8000};
const HOLD_STEPS = [3000, 5000, 8000, 15000, 30000, 60000, -1];

let ecobuildPath = () => 'ecobuild';
const sessions = [];      // {id, num, name, dir, kind, agent, proc, term, history, exited, state, owner, statusDir, info}
const windows = [];       // {win, tabs: [id], active, topmost, ready, mini}
let nextId = 1;
let current = null;       // 最後に使った窓（新しいタブはここに）
let notify = {...NOTIFY_DEFAULTS};
const cards = [];         // 右下の返答のカード：{key, id, num, name, text, until}
let peekOn = false;

// ---- 記録（窓の場所・最前面・知らせ方・右下の場所） --------------------------------------------------
function readState() { try { return JSON.parse(fs.readFileSync(STATE_FILE(), 'utf8')); } catch (e) { return {}; } }
function writeState(patch) {
  try { fs.writeFileSync(STATE_FILE(), JSON.stringify({...readState(), ...patch}, null, 2)); } catch (e) { /* 記録できなくても動く */ }
}

// ---- エージェント（タブ） -------------------------------------------------------------------------
function findSession(id) { return sessions.find(s => s.id === id); }
function describe(s) {
  return {id: s.id, num: s.num, name: s.name, dir: s.dir, kind: s.kind, exited: s.exited, state: s.state,
          window: windows.indexOf(s.owner), info: status.summary(s)};
}

function spawnSession(s, size) {
  const args = ['-C', s.dir, 'agent', 'start', '--here', ...(s.agent ? ['--agent', s.agent] : [])];
  s.term = new Terminal({cols: size.cols, rows: size.rows, scrollback: 3000, allowProposedApi: true});
  s.startedAt = Date.now(); s.statusDir = null; s.info = null; s.repliedAt = undefined;
  s.proc = pty.spawn(ecobuildPath(), args, {
    name: 'xterm-256color', cols: size.cols, rows: size.rows, cwd: s.dir,
    env: {...process.env, COLORTERM: 'truecolor', FORCE_COLOR: '3'},
  });
  s.proc.onData(data => {
    if (!s.statusDir) s.statusDir = status.found(data);
    s.history.push(data); s.size += data.length;
    while (s.size > HISTORY_LIMIT && s.history.length > 1) s.size -= s.history.shift().length;
    s.term.write(data);
    send(s.owner, 'agents:data', s.id, data);
  });
  s.proc.onExit(({exitCode}) => {
    s.exited = true; s.state = 'exited';
    send(s.owner, 'agents:exit', s.id, exitCode);
    pushTabs();
  });
}

function openSession({dir, agent = '', name = ''} = {}) {
  if (!dir) throw new Error('作業空間の場所がありません。');
  const same = sessions.find(s => !s.exited && s.kind === 'workspace' && sameDir(s.dir, dir));
  if (same) { focusTab(same.id); return describe(same); }   // 同じ作業空間のエージェントは1つ（前に出す）
  const s = {id: nextId++, num: sessions.length + 1, name: name || path.basename(dir), dir, kind: 'workspace', agent,
             history: [], size: 0, exited: false, state: 'starting', owner: null};
  sessions.push(s);
  const w = current && !current.win.isDestroyed() && !current.mini ? current : windows.find(x => !x.mini) || openWindow();
  spawnSession(s, w.size || {cols: 100, rows: 30});
  adopt(w, s);
  select(s.id, true);
  return describe(s);
}

function closeSession(id) {
  const s = findSession(id); if (!s) return;
  try { s.proc?.kill(); } catch (e) { /* もう終わっている */ }
  s.term?.dispose();
  sessions.splice(sessions.indexOf(s), 1);
  for (const other of sessions) if (other.num > s.num) other.num--;   // 番号は 1 から続く
  if (s.owner) leave(s.owner, s);
  dropCards(c => c.id === id);
  pushTabs();
}

function restartSession(id, agent) {
  const s = findSession(id); if (!s || !s.owner) return;
  try { s.proc?.kill(); } catch (e) { /* もう終わっている */ }
  s.term?.dispose(); s.history = []; s.size = 0; s.exited = false; s.state = 'starting';
  if (agent !== undefined) s.agent = agent;
  send(s.owner, 'agents:reset', s.id);
  spawnSession(s, s.owner.size || {cols: 100, rows: 30});
  pushTabs();
}

function renameSession(id, name) {
  const s = findSession(id); if (!s || !name.trim()) return;
  s.name = name.trim(); pushTabs();
}

const sameDir = (a, b) => path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase();

// ---- 窓 --------------------------------------------------------------------------------------------
function send(w, channel, ...args) { if (w && !w.win.isDestroyed() && w.ready) w.win.webContents.send(channel, ...args); }

function openWindow({bounds} = {}) {
  const saved = readState().bounds;
  const area = display.getPrimaryDisplay().workArea;
  const b = bounds || (windows.length === 0 && saved) || {
    ...WINDOW_SIZE, x: area.x + area.width - WINDOW_SIZE.width - 24 - windows.length * 32, y: area.y + 48 + windows.length * 32};
  const win = new BrowserWindow({
    ...b, minWidth: 360, minHeight: 200, frame: false, icon: ICON, backgroundColor: '#14181d', show: false,
    webPreferences: {preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true},
  });
  const w = {win, tabs: [], active: null, topmost: readState().topmost || 'always', ready: false, size: null, mini: false};
  windows.push(w);
  applyTopmost(w);
  win.loadFile(path.join(__dirname, 'window.html'));
  win.once('ready-to-show', () => { if (!w.mini) win.showInactive(); });   // 作業中のアプリのフォーカスを奪わない
  win.on('focus', () => { current = w; });
  win.on('close', () => { if (windows.length === 1) writeState({bounds: win.getBounds()}); });
  win.on('closed', () => {
    // 閉じた窓のタブは、ほかの窓へ移す（最後の窓なら、エージェントも終わる）
    windows.splice(windows.indexOf(w), 1);
    const rest = windows.find(x => !x.mini) || windows[0];
    for (const id of [...w.tabs]) {
      const s = findSession(id); if (!s) continue;
      if (rest) adopt(rest, s); else closeSession(id);
    }
    if (current === w) current = rest || null;
    pushTabs(); pushDock();
  });
  current = w;
  return w;
}

function adopt(w, s) {
  if (s.owner && s.owner !== w) leave(s.owner, s);
  s.owner = w;
  if (!w.tabs.includes(s.id)) w.tabs.push(s.id);
  w.active = s.id;
  send(w, 'agents:adopt', describe(s), s.history.join(''));
  pushTabs();
}

function leave(w, s) {
  w.tabs = w.tabs.filter(id => id !== s.id);
  if (w.active === s.id) w.active = w.tabs.at(-1) ?? null;
  send(w, 'agents:release', s.id);
  if (!w.tabs.length && !w.win.isDestroyed() && windows.length > 1) w.win.close();   // 空になった窓は閉じる
}

function select(id, front) {
  const s = findSession(id); if (!s?.owner) return;
  s.owner.active = id; current = s.owner; s.unseen = false;
  send(s.owner, 'agents:select', id);
  if (front) bringToFront(s.owner);
  pushTabs(); pushDock();
}

// タブを前に出す（最小化していれば戻す）。人が押したときは focus して、すぐ打てるように
function focusTab(id, focus = false) {
  const s = findSession(id); if (!s?.owner) return;
  if (s.owner.mini) restoreWindow(s.owner);
  select(id, true);
  if (focus) { s.owner.win.show(); s.owner.win.focus(); }
}

function bringToFront(w) {
  if (w.mini) return;   // 最小化中は右下の表示で知らせる
  if (w.win.isMinimized()) w.win.restore();
  if (w.topmost === 'auto') { w.win.setAlwaysOnTop(true, 'floating'); setTimeout(() => applyTopmost(w), 1500); }
  w.win.showInactive();
}

function applyTopmost(w) {
  if (!w.win.isDestroyed()) w.win.setAlwaysOnTop(w.topmost === 'always', 'floating');
}

function cycleTopmost(w) {
  w.topmost = TOPMOST[(TOPMOST.indexOf(w.topmost) + 1) % TOPMOST.length];
  applyTopmost(w); writeState({topmost: w.topmost});
  send(w, 'agents:topmost', w.topmost);
}

function moveToNewWindow(id) {
  const s = findSession(id); if (!s) return;
  const from = s.owner?.win.getBounds();
  const w = openWindow({bounds: from && {...from, x: from.x + 40, y: from.y + 40}});
  w.pending = s;   // 窓の画面ができてから移す
}

// 最小化：窓を隠して右下の表示にする（ほかの窓はそのまま）
function minimizeWindow(w) {
  w.mini = true; w.win.hide(); peekOn = false;
  for (const id of w.tabs) { const s = findSession(id); if (s) s.unseen = false; }
  pushDock();
}

function restoreWindow(w, focus = false) {
  w.mini = false; peekOn = false;
  for (const id of w.tabs) { const s = findSession(id); if (s) s.unseen = false; }
  dropCards(c => w.tabs.includes(c.id));
  if (focus) { w.win.show(); w.win.focus(); } else w.win.showInactive();
  applyTopmost(w); pushDock();
}

function pushTabs() {
  for (const w of windows) {
    send(w, 'agents:tabs', {tabs: w.tabs.map(findSession).filter(Boolean).map(describe), active: w.active,
                            topmost: w.topmost});
  }
}

// ---- 状態（画面と、エージェントが書き出すもの） ----------------------------------------------------------
function screenText(s) {
  const buffer = s.term.buffer.active, lines = [];
  for (let y = buffer.viewportY; y < buffer.viewportY + s.term.rows; y++) lines.push(buffer.getLine(y)?.translateToString(true) ?? '');
  return lines.join('\n');
}

function poll() {
  let changed = false;
  for (const s of sessions) {
    if (s.exited || !s.term) continue;
    const read = parser.parse(screenText(s));
    s.input = read.input || '';
    if (read.state !== s.state) {
      // 返答の終わりは Stop フック（status.json の置き場所が分かっているとき）、分からなければ画面で見る
      if (!s.statusDir && s.state === 'thinking' && read.state === 'idle') replied(s, read.reply);
      s.state = read.state; changed = true;
    }
    const got = status.poll(s);
    if (got.info) changed = true;
    if (got.replied) replied(s, got.replied.message);
  }
  if (changed) { pushTabs(); pushDock(); }
  const now = Date.now();
  if (dropCards(c => c.until !== -1 && c.until < now)) pushDock();
}

// 返答が終わった：最小化中なら右下でバッジとカード。そうでなく最前面が「自動」なら前に出す。
// 見ている（その窓にフォーカスがあり、そのタブを出している）ときは知らせない。知らせ方は notify.style
function replied(s, message) {
  const w = s.owner; if (!w) return;
  const text = (message || '').trim().slice(0, 1200);
  if (w.mini) { s.unseen = true; addCard(s, text); if (notify.style === 'ecobuild') dock.play({id: notify.sound, volume: notify.volume}); return; }
  if (w.topmost === 'auto') bringToFront(w);
  const watching = w.win.isFocused() && w.active === s.id;
  if (watching || notify.style === 'off') return;
  if (notify.style === 'ecobuild') { addCard(s, text); dock.play({id: notify.sound, volume: notify.volume}); return; }
  if (Notification.isSupported()) {
    const n = new Notification({title: `${s.num}  ${s.name}`, body: text.replace(/\s+/g, ' ').slice(0, 200) || '返答が終わりました',
                                icon: ICON, silent: false});
    n.on('click', () => focusTab(s.id, true));
    live.add(n); n.on('close', () => live.delete(n));
    n.show();
  }
}
const live = new Set();   // 出ている通知（参照がなくなると、クリックが効かなくなる）

// ---- 右下の表示 ----------------------------------------------------------------------------------------
let cardKey = 1;
function addCard(s, text) {
  for (let i = cards.length - 1; i >= 0; i--) if (cards[i].id === s.id) cards.splice(i, 1);   // タブごとに最新の1枚
  cards.push({key: cardKey++, id: s.id, num: s.num, name: s.name, text,
              until: notify.hold === -1 ? -1 : Date.now() + notify.hold});
  while (cards.length > 3) cards.shift();
  pushDock();
}
function dropCards(test) {
  let dropped = false;
  for (let i = cards.length - 1; i >= 0; i--) if (test(cards[i])) { cards.splice(i, 1); dropped = true; }
  return dropped;
}

function pushDock() {
  const hidden = windows.filter(w => w.mini && !w.win.isDestroyed());
  const target = hidden.at(-1), s = target && findSession(target.active);
  const badge = sessions.filter(x => x.unseen && x.owner?.mini).length;
  const chip = s ? {num: s.num, name: s.name, state: s.state, badge} : null;
  const peek = chip && peekOn ? {lines: parser.lastLines(screenText(s), 12), input: s.input} : null;
  dock.update({chip, peek, cards: cards.map(c => ({...c, num: findSession(c.id)?.num ?? c.num}))});
}

// ---- タブの一覧（☰） --------------------------------------------------------------------------------------
function pickerList() {
  return sessions.map(s => ({...describe(s), lines: s.term ? parser.lastLines(screenText(s), 2) : '', input: s.input || '',
                             mini: !!s.owner?.mini}));
}

// ---- やり取り（画面から） ------------------------------------------------------------------------------
const windowOf = event => windows.find(w => w.win.webContents === event.sender);

function setNotify(patch) {
  notify = {...notify, ...patch};
  if (!['windows', 'ecobuild', 'off'].includes(notify.style)) notify.style = NOTIFY_DEFAULTS.style;
  notify.volume = Math.max(0, Math.min(1, Number(notify.volume) || 0));
  if (!HOLD_STEPS.includes(notify.hold)) notify.hold = NOTIFY_DEFAULTS.hold;
  writeState({notify});
  for (const w of windows) send(w, 'agents:notify', notify, HOLD_STEPS);
}

function setup({ecobuild}) {
  ecobuildPath = ecobuild;
  const saved = readState();
  notify = {...NOTIFY_DEFAULTS, ...(saved.notify || {})};
  dock.setup({
    initialAnchor: saved.dock, onAnchor: anchor => writeState({dock: anchor}),
    actions: {
      peek: () => { peekOn = !peekOn; pushDock(); },
      restore: () => { for (const w of windows.filter(x => x.mini)) restoreWindow(w, true); },
      open: id => { dropCards(c => c.id === id); focusTab(id, true); },
      dismiss: key => { dropCards(c => c.key === key); pushDock(); },
      'dismiss-all': () => { dropCards(() => true); peekOn = false; pushDock(); },
    },
  });
  dock.wire(ipcMain);
  ipcMain.handle('agents:open', (event, options) => openSession(options || {}));
  ipcMain.handle('agents:list', () => sessions.map(describe));
  ipcMain.handle('agents:picker', () => pickerList());
  ipcMain.on('agents:ready', event => {
    const w = windowOf(event); if (!w) return;
    w.ready = true;
    for (const id of w.tabs) { const s = findSession(id); send(w, 'agents:adopt', describe(s), s.history.join('')); }
    if (w.pending) { const s = w.pending; w.pending = null; adopt(w, s); }
    send(w, 'agents:topmost', w.topmost);
    send(w, 'agents:notify', notify, HOLD_STEPS);
    if (w.active) send(w, 'agents:select', w.active);
    pushTabs();
  });
  ipcMain.on('agents:input', (event, id, data) => findSession(id)?.proc?.write(data));
  ipcMain.on('agents:resize', (event, id, cols, rows) => {
    const s = findSession(id), w = windowOf(event); if (!s || !cols || !rows) return;
    if (w) w.size = {cols, rows};
    try { s.proc?.resize(cols, rows); s.term?.resize(cols, rows); } catch (e) { /* 終わったところ */ }
  });
  ipcMain.on('agents:select', (event, id) => select(id, false));
  ipcMain.on('agents:focus-tab', (event, id) => focusTab(id, true));
  ipcMain.on('agents:close-tab', (event, id) => closeSession(id));
  ipcMain.on('agents:rename', (event, id, name) => renameSession(id, String(name || '')));
  ipcMain.on('agents:reorder', (event, ids) => {
    const w = windowOf(event); if (!w) return;
    w.tabs = ids.filter(id => w.tabs.includes(id)); pushTabs();
  });
  ipcMain.on('agents:new-window', (event, id) => moveToNewWindow(id));
  ipcMain.on('agents:topmost', event => { const w = windowOf(event); if (w) cycleTopmost(w); });
  ipcMain.on('agents:minimize', event => { const w = windowOf(event); if (w) minimizeWindow(w); });
  ipcMain.on('agents:close-window', event => windowOf(event)?.win.close());
  ipcMain.on('agents:restart', (event, id, resume) => restartSession(id, resume ? 'claude --continue' : undefined));
  ipcMain.on('agents:notify', (event, patch) => setNotify(patch || {}));
  ipcMain.on('agents:test-sound', () => dock.play({id: notify.sound, volume: notify.volume}));
  setInterval(poll, POLL_MS);
  app.on('before-quit', () => { for (const s of sessions) try { s.proc?.kill(); } catch (e) { /* 終わっている */ } });
}

// 外から（試験・GUIの操作）：タブに文字を送る
function input(id, data) { findSession(id)?.proc?.write(data); }

module.exports = {setup, openSession, input, sessions: () => sessions.map(describe)};
