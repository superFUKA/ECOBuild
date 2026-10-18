'use strict';
// エージェントの窓（Electron の main）：エージェントを、このアプリの小さな窓のタブとして動かす。
// - タブ＝1つのエージェント（作業空間のエージェント：`ecobuild -C <場所> agent start --here`。コンテナならその中で動く。
//   準備・鍵の受け渡しは ecobuild がする）。端末は node-pty。状態を読むため、main 側にも見えない端末（@xterm/headless）を持つ。
// - 番号は 1 から続く（閉じるとそれより大きい番号が詰まる）。窓はいくつでも持て、タブは窓の間で動かせる。
// - 窓は枠なし。最前面の表示は窓ごとに 常に → 自動 → オフ（自動は、返答が届いたとき・選んだときだけ前に出る）。
// - 状態（考え中・裏で実行中・選択肢・待機中・終了）は画面を読んで決め（screen.js）、変わったら窓に知らせる。
// 画面（window.html）とのやり取りは agents/preload.js。ほかの窓（作業空間）からは preload.js の agents.open で開く。
const {app, BrowserWindow, Notification, ipcMain, screen: display} = require('electron');
const fs = require('fs');
const path = require('path');
const pty = require('node-pty');
const {Terminal} = require('@xterm/headless');
const parser = require('./screen');

const HISTORY_LIMIT = 2 * 1024 * 1024;   // 後から開いた窓に流し直す出力（文字数）
const POLL_MS = 1500;                     // 状態を読み直す間隔
const TOPMOST = ['always', 'auto', 'off'];
const WINDOW_SIZE = {width: 760, height: 520};
const STATE_FILE = () => path.join(app.getPath('userData'), 'agents.json');
const ICON = path.join(__dirname, '..', '..', 'icon.ico');

let ecobuildPath = () => 'ecobuild';
const sessions = [];      // {id, num, name, dir, kind, agent, proc, term, history, exited, state, owner}
const windows = [];       // {win, tabs: [id], active, topmost, ready}
let nextId = 1;
let current = null;       // 最後に使った窓（新しいタブはここに）

// ---- 記録（窓の場所・最前面の表示） --------------------------------------------------------------
function readState() { try { return JSON.parse(fs.readFileSync(STATE_FILE(), 'utf8')); } catch (e) { return {}; } }
function writeState(patch) {
  try { fs.writeFileSync(STATE_FILE(), JSON.stringify({...readState(), ...patch}, null, 2)); } catch (e) { /* 記録できなくても動く */ }
}

// ---- エージェント（タブ） -------------------------------------------------------------------------
function findSession(id) { return sessions.find(s => s.id === id); }
function describe(s) {
  return {id: s.id, num: s.num, name: s.name, dir: s.dir, kind: s.kind, exited: s.exited, state: s.state,
          window: windows.indexOf(s.owner)};
}

function spawnSession(s, size) {
  const args = ['-C', s.dir, 'agent', 'start', '--here', ...(s.agent ? ['--agent', s.agent] : [])];
  s.term = new Terminal({cols: size.cols, rows: size.rows, scrollback: 3000, allowProposedApi: true});
  s.proc = pty.spawn(ecobuildPath(), args, {
    name: 'xterm-256color', cols: size.cols, rows: size.rows, cwd: s.dir,
    env: {...process.env, COLORTERM: 'truecolor', FORCE_COLOR: '3'},
  });
  s.proc.onData(data => {
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
  if (same) { select(same.id, true); return describe(same); }   // 同じ作業空間のエージェントは1つ（前に出す）
  const s = {id: nextId++, num: sessions.length + 1, name: name || path.basename(dir), dir, kind: 'workspace', agent,
             history: [], size: 0, exited: false, state: 'starting', owner: null};
  sessions.push(s);
  const w = current && !current.win.isDestroyed() ? current : openWindow();
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
  const w = {win, tabs: [], active: null, topmost: readState().topmost || 'always', ready: false, size: null};
  windows.push(w);
  applyTopmost(w);
  win.loadFile(path.join(__dirname, 'window.html'));
  win.once('ready-to-show', () => win.showInactive());   // 作業中のアプリのフォーカスを奪わない
  win.on('focus', () => { current = w; });
  win.on('close', () => { if (windows.length === 1) writeState({bounds: win.getBounds()}); });
  win.on('closed', () => {
    // 閉じた窓のタブは、ほかの窓へ移す（最後の窓なら、エージェントも終わる）
    windows.splice(windows.indexOf(w), 1);
    const rest = windows[0];
    for (const id of [...w.tabs]) {
      const s = findSession(id); if (!s) continue;
      if (rest) adopt(rest, s); else closeSession(id);
    }
    if (current === w) current = rest || null;
    pushTabs();
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
  s.owner.active = id; current = s.owner;
  send(s.owner, 'agents:select', id);
  if (front) bringToFront(s.owner);
  pushTabs();
}

function bringToFront(w) {
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

function pushTabs() {
  for (const w of windows) {
    send(w, 'agents:tabs', {tabs: w.tabs.map(findSession).filter(Boolean).map(describe), active: w.active,
                            topmost: w.topmost});
  }
}

// ---- 状態（画面を読む） ------------------------------------------------------------------------------
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
    if (read.state !== s.state) {
      if (s.state === 'thinking' && read.state === 'idle') replied(s, read.reply);
      s.state = read.state; changed = true;
    }
    s.reply = read.reply || s.reply;
  }
  if (changed) pushTabs();
}

// 返答が終わった：その窓の最前面が「自動」なら前に出し、窓が見えていなければ知らせる
function replied(s, reply) {
  const w = s.owner;
  if (w?.topmost === 'auto') bringToFront(w);
  if (w && (w.win.isMinimized() || !w.win.isVisible() || w.active !== s.id) && Notification.isSupported()) {
    const n = new Notification({title: `${s.num}  ${s.name}`, body: reply || '返答が終わりました', icon: ICON, silent: false});
    n.on('click', () => select(s.id, true));
    n.show();
  }
}

// ---- やり取り（画面から） ------------------------------------------------------------------------------
const windowOf = event => windows.find(w => w.win.webContents === event.sender);

function setup({ecobuild}) {
  ecobuildPath = ecobuild;
  ipcMain.handle('agents:open', (event, options) => openSession(options || {}));
  ipcMain.handle('agents:list', () => sessions.map(describe));
  ipcMain.on('agents:ready', event => {
    const w = windowOf(event); if (!w) return;
    w.ready = true;
    for (const id of w.tabs) { const s = findSession(id); send(w, 'agents:adopt', describe(s), s.history.join('')); }
    if (w.pending) { const s = w.pending; w.pending = null; adopt(w, s); }
    send(w, 'agents:topmost', w.topmost);
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
  ipcMain.on('agents:close-tab', (event, id) => closeSession(id));
  ipcMain.on('agents:rename', (event, id, name) => renameSession(id, String(name || '')));
  ipcMain.on('agents:reorder', (event, ids) => {
    const w = windowOf(event); if (!w) return;
    w.tabs = ids.filter(id => w.tabs.includes(id)); pushTabs();
  });
  ipcMain.on('agents:new-window', (event, id) => moveToNewWindow(id));
  ipcMain.on('agents:topmost', event => { const w = windowOf(event); if (w) cycleTopmost(w); });
  ipcMain.on('agents:minimize', event => windowOf(event)?.win.minimize());
  ipcMain.on('agents:close-window', event => windowOf(event)?.win.close());
  ipcMain.on('agents:restart', (event, id) => {
    const s = findSession(id); if (!s || !s.owner) return;
    try { s.proc?.kill(); } catch (e) { /* もう終わっている */ }
    s.term?.dispose(); s.history = []; s.size = 0; s.exited = false; s.state = 'starting';
    send(s.owner, 'agents:reset', s.id);
    spawnSession(s, s.owner.size || {cols: 100, rows: 30});
    pushTabs();
  });
  setInterval(poll, POLL_MS);
  app.on('before-quit', () => { for (const s of sessions) try { s.proc?.kill(); } catch (e) { /* 終わっている */ } });
}

// 外から（試験・GUIの操作）：タブに文字を送る
function input(id, data) { findSession(id)?.proc?.write(data); }

module.exports = {setup, openSession, input, sessions: () => sessions.map(describe)};
