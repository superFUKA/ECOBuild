'use strict';
// エージェントの窓（Electron の main）：エージェントを、このアプリの小さな窓のタブとして動かす。
// - タブ＝1つのエージェント（作業空間のエージェント：`ecobuild -C <場所> agent start --here`。コンテナならその中で動く。
//   準備・鍵の受け渡しは ecobuild がする）。端末は node-pty。状態を読むため、main 側にも見えない端末（@xterm/headless）を持つ。
// - 番号は 1 から続く（閉じるとそれより大きい番号が詰まる）。窓はいくつでも持て、タブは窓の間で動かせる。
// - 窓は枠なし。最前面の表示は窓ごとに 常に → 自動 → オフ（自動は、返答が届いたとき・選んだときだけ前に出る）。
// - 状態（考え中・裏で実行中・選択肢・待機中・終了）は画面を読んで決める（screen.js）。モデル・使用量の制限・返答の終わりは、
//   エージェントが書き出すもの（status.js。ecobuild が置き場所を端末の見えない印で知らせる）。
// - 最小化すると窓は隠れ、右下の表示（dock.js）になる。返答の知らせは Windows の通知か、右下のカードと音（notify）。
// - オペレーター（ECOBuild の操作係）は番号 0 で、ふだんはタブにせず裏で動かす（`ecobuild agent operator --here`）。
//   ハブの「AI に頼む」がこれと話す（会話の記録はここが持つ）。頼まれればタブで開く。
// - 外（ecobuild gui・MCP・オペレーター）からの操作は、GUI のサーバーを通して届く（link.js）。
// - 音声入力：Claude Code の音声入力（hold モード：Space を押し続ける間だけ録音）を、Space のキーリピートを送ってまねる。
//   ほかのアプリを使っていても効くキー：Ctrl+Alt+V で録音の開始・停止、Ctrl+Alt+↓ で送信（録音中なら止めて、聞き取りが
//   入力欄に入ってから）、Ctrl+Alt+↑ で入力欄を消す、Ctrl+Alt+← / → で前・次のタブ。対象は最後に使った窓の選んでいるタブ。
// - リング（Ring II）：ジェスチャーを操作に割り当てる（ring.js が受信係を動かす）。作業モードとオペレーターモード
//   （リングの LED のモード。信号が変わる操作は調整で「operator:<操作>」として登録）。選択肢が出ているときに押し込むと
//   選択モード（上下左右で選び、押し込みで決定）。右下に返答のカードが出ているときのタッチは、カードを閉じる。
// 画面（window.html）とのやり取りは agents/preload.js。ほかの窓（作業空間・ハブ）からは preload.js の agents で。
const {app, BrowserWindow, Notification, clipboard, dialog, globalShortcut, ipcMain, nativeImage, screen: display} = require('electron');
const fs = require('fs');
const path = require('path');
const pty = require('node-pty');
const {Terminal} = require('@xterm/headless');
const parser = require('./screen');
const status = require('./status');
const dock = require('./dock');
const link = require('./link');
const ring = require('./ring');

const HISTORY_LIMIT = 2 * 1024 * 1024;   // 後から開いた窓に流し直す出力（文字数）
const POLL_MS = 1500;                     // 状態を読み直す間隔
const TOPMOST = ['always', 'auto', 'off'];
const WINDOW_SIZE = {width: 760, height: 520};
const STATE_FILE = () => path.join(app.getPath('userData'), 'agents.json');
const OPERATOR_LOG = () => path.join(app.getPath('userData'), 'operator.json');   // オペレーターとの会話（表示用）
const OPERATOR_SIZE = {cols: 110, rows: 32};   // 裏で動かすときの端末の大きさ
const ICON = path.join(__dirname, '..', '..', 'icon.ico');
// 返答の知らせ。style：windows（Windows の通知。音も Windows の設定どおり）・ecobuild（右下のカードと音）・off。
// hold：右下に返答を出しておく時間（ミリ秒。-1 は消さない）
const NOTIFY_DEFAULTS = {style: 'windows', sound: 'chime', volume: 0.6, hold: 8000};
const HOLD_STEPS = [3000, 5000, 8000, 15000, 30000, 60000, -1];
const KEY_REPEAT_MS = 33;      // 録音中に Space を送る間隔（端末のキーリピートと同じくらい。Claude Code はこれで押し続けと見る）
const CLEAR_REPEAT = 30;       // 入力欄を消すときの Ctrl+U の数（複数行も消えるように）
// リングの割り当て（動作の名前は runAction）。左右・長押しはどちらのモードでも同じ（モードで信号が変わらないため）
const RING_DEFAULTS = {
  enabled: false, match: '', guard: true, keepalive: true, scroll_lines: 3,
  actions: {left: 'prev', right: 'next', up: 'clear_or_minimize', down: 'submit', click: 'voice',
            hold_left: 'scroll_up', hold_right: 'scroll_down', tap: 'dismiss'},
  operator_actions: {click: 'operator_voice', down: 'operator_submit', up: 'operator_clear', left: 'prev', right: 'next',
                     hold_left: 'scroll_up', hold_right: 'scroll_down', tap: 'dismiss'},
  choice_actions: {up: 'key:up', down: 'key:down', left: 'key:left', right: 'key:right', click: 'key:enter'},
};
const HOLD_AFTER_CLICK_MS = 300;   // 強く押し込むと、続けて長押しの信号が届くことがある：押し込みの直後の長押しは無視する
const SHORTCUTS = {'Control+Alt+V': () => toggleVoice(), 'Control+Alt+Down': () => submitActive(),
                   'Control+Alt+Up': () => clearActive(), 'Control+Alt+Left': () => step(-1), 'Control+Alt+Right': () => step(1)};
// 親（このアプリを Claude Code の中から起動したとき等）から受け継ぐと、子のエージェントが自分を別の会話の一部だと思う
// （会話を保存しない・題名が親のもの・白黒になる）印。端末を起動するときに外す
const PARENT_MARKERS = ['CLAUDECODE', 'CLAUDE_PID', 'CLAUDE_EFFORT', 'CLAUDE_CODE_CHILD_SESSION', 'CLAUDE_CODE_SESSION_ID',
  'CLAUDE_CODE_SESSION_ATTENDED', 'CLAUDE_CODE_ENTRYPOINT', 'CLAUDE_CODE_EXECPATH', 'CLAUDE_CODE_MESSAGING_SOCKET',
  'CLAUDE_CODE_MESSAGING_TOKEN', 'CLAUDE_JOB_DIR', 'CLAUDE_CODE_ALT_SCREEN_FULL_REPAINT', 'AI_AGENT', 'NO_COLOR'];
function childEnv() {
  const env = {...process.env, COLORTERM: 'truecolor', FORCE_COLOR: '3'};
  for (const key of PARENT_MARKERS) delete env[key];
  return env;
}

let ecobuildPath = () => 'ecobuild';
let groupWith = () => {};   // 窓をモジュールの窓の仲間にする（main.js の asModuleApp）
const sessions = [];      // {id, num, name, dir, kind, agent, proc, term, history, exited, state, owner, statusDir, info}
const windows = [];       // {win, tabs: [id], active, topmost, ready, mini}
let nextId = 1;
let current = null;       // 最後に使った窓（新しいタブはここに）
let notify = {...NOTIFY_DEFAULTS};
const cards = [];         // 右下の返答のカード：{key, id, num, name, text, until}
let peekOn = false;
let operatorLog = [];     // [{role: user|agent, text, at}]
let operatorWatchers = new Set();   // オペレーターとの会話を表示している画面（その窓が前にあれば右下に出さない）
let operatorQueue = [];   // 起動を待っている間に頼まれた発言
// オペレーターのモデル（簡単な操作が主なので、既定は速いもの。'' は Claude Code の既定）
const OPERATOR_MODELS = ['sonnet', 'haiku', 'opus', ''];
let operatorModel = 'sonnet';
let reopenTabs = true;    // GUI を開き直したとき、前回のタブを会話の続きから開き直す
let pickerWindow = null;  // タブの一覧（☰）を出している窓（リングで選ぶ）
// アイコン（オペレーター・作業用。小さくした PNG の data URL。'' は既定）と、話し方（ECOBuild の設定。ここは表示と書き換えだけ）
let icons = {operator: '', agent: ''};
let styles = {operator: '', agent: ''};
const iconOf = s => icons[s?.kind === 'operator' ? 'operator' : 'agent'] || '';
let ringConfig = {...RING_DEFAULTS};
let ringMode = 'work';    // work・operator
let choosing = null;      // 選択モードのタブの id
let ignoreHoldUntil = 0;

// ---- 記録（窓の場所・最前面・知らせ方・右下の場所） --------------------------------------------------
function readState() { try { return JSON.parse(fs.readFileSync(STATE_FILE(), 'utf8')); } catch (e) { return {}; } }
function writeState(patch) {
  try { fs.writeFileSync(STATE_FILE(), JSON.stringify({...readState(), ...patch}, null, 2)); } catch (e) { /* 記録できなくても動く */ }
}

// ---- エージェント（タブ） -------------------------------------------------------------------------
function findSession(id) { return sessions.find(s => s.id === id); }
function describe(s) {
  return {id: s.id, num: s.num, name: s.name, dir: s.dir, kind: s.kind, exited: s.exited, state: s.recording ? 'listening' : s.state,
          unread: !!s.unread,
          window: windows.indexOf(s.owner), info: status.summary(s)};
}
const findOperator = () => sessions.find(s => s.kind === 'operator');

function spawnSession(s, size) {
  const args = s.kind === 'operator' ? ['agent', 'operator', '--here', ...(s.agent ? ['--agent', s.agent] : [])]
    : ['-C', s.dir, 'agent', 'start', '--here', ...(s.agent ? ['--agent', s.agent] : [])];
  s.term = new Terminal({cols: size.cols, rows: size.rows, scrollback: 3000, allowProposedApi: true});
  s.startedAt = Date.now(); s.statusDir = null; s.info = null; s.repliedAt = undefined;
  const proc = s.proc = pty.spawn(ecobuildPath(), args, {
    name: 'xterm-256color', cols: size.cols, rows: size.rows, cwd: s.dir,
    env: childEnv(),
  });
  // 起動し直したあとに届く前のプロセスの出力・終わりは捨てる（新しいほうを「終わった」にしない）
  proc.onData(data => {
    if (s.proc !== proc) return;
    if (!s.statusDir) s.statusDir = status.found(data);
    s.history.push(data); s.size += data.length;
    while (s.size > HISTORY_LIMIT && s.history.length > 1) s.size -= s.history.shift().length;
    s.term.write(data);
    send(s.owner, 'agents:data', s.id, data);
  });
  proc.onExit(({exitCode}) => {
    if (s.proc !== proc) return;
    s.exited = true; s.state = 'exited';
    send(s.owner, 'agents:exit', s.id, exitCode);
    pushTabs();
  });
}

function openSession({dir, agent = '', name = '', resume = false} = {}) {
  if (!dir) throw new Error('作業空間の場所がありません。');
  const same = sessions.find(s => !s.exited && s.kind === 'workspace' && sameDir(s.dir, dir));
  if (same) { focusTab(same.id); return describe(same); }   // 同じ作業空間のエージェントは1つ（前に出す）
  const s = {id: nextId++, num: sessions.filter(x => x.kind !== 'operator').length + 1, name: name || path.basename(dir), dir, kind: 'workspace',
             agent: agent || (resume ? 'claude --continue' : ''), savedAgent: agent,
             history: [], size: 0, exited: false, state: 'starting', owner: null};
  sessions.push(s);
  // 作業空間ごとの窓（タスクバーでは、その作業空間のモジュールの窓と一緒にまとまる）。なければ作る
  const w = windows.find(x => x.module && sameDir(x.module, dir) && !x.win.isDestroyed()) || openWindow({module: dir});
  if (w.mini) restoreWindow(w);
  spawnSession(s, w.size || {cols: 100, rows: 30});
  adopt(w, s);
  select(s.id, true);
  saveTabs();
  return describe(s);
}

// 開いているタブ（作業空間のエージェント）を覚える：GUI を開き直したとき、会話の続きから開き直す（reopen）
function saveTabs() {
  if (app.isQuitting) return;   // 終わるときに閉じたものは忘れない
  writeState({tabs: sessions.filter(s => s.kind === 'workspace' && !s.exited).sort((a, b) => a.num - b.num)
    .map(s => ({dir: s.dir, name: s.name, agent: s.savedAgent || ''}))});
}

function closeSession(id) {
  const s = findSession(id); if (!s) return;
  if (s.kind === 'operator' && !app.isQuitting) { hideOperator(); return; }   // オペレーターは閉じずに裏に戻す
  try { s.proc?.kill(); } catch (e) { /* もう終わっている */ }
  s.term?.dispose();
  sessions.splice(sessions.indexOf(s), 1);
  for (const other of sessions) if (other.kind !== 'operator' && other.num > s.num) other.num--;   // 番号は 1 から続く
  if (s.owner) leave(s.owner, s);
  dropCards(c => c.id === id);
  pushTabs();
  saveTabs();
}

function restartSession(id, agent) {
  const s = findSession(id); if (!s || (!s.owner && s.kind !== 'operator')) return;
  try { s.proc?.kill(); } catch (e) { /* もう終わっている */ }
  s.term?.dispose(); s.history = []; s.size = 0; s.exited = false; s.state = 'starting';
  if (agent !== undefined) s.agent = agent;
  send(s.owner, 'agents:reset', s.id);
  spawnSession(s, s.owner?.size || (s.kind === 'operator' ? OPERATOR_SIZE : {cols: 100, rows: 30}));
  pushTabs();
}

function renameSession(id, name) {
  const s = findSession(id); if (!s || !name.trim()) return;
  s.name = name.trim(); pushTabs(); saveTabs();
  // Claude Code の会話の名前もそろえる（続きから再開の一覧にその名前で出る）。書きかけ・考え中に混ざらないよう、
  // 待機中で入力欄が空になってから /rename を送る（poll）
  if (isClaude(s)) s.pendingTitle = s.name;
}
const isClaude = s => !s.agent || /^claude(\s|$)/.test(s.agent);

const sameDir = (a, b) => path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase();

// ---- 窓 --------------------------------------------------------------------------------------------
function send(w, channel, ...args) { if (w && !w.win.isDestroyed() && w.ready) w.win.webContents.send(channel, ...args); }

function openWindow({bounds, module = null} = {}) {
  const saved = readState().bounds;
  const area = display.getPrimaryDisplay().workArea;
  const b = bounds || (windows.length === 0 && saved) || {
    ...WINDOW_SIZE, x: area.x + area.width - WINDOW_SIZE.width - 24 - windows.length * 32, y: area.y + 48 + windows.length * 32};
  const win = new BrowserWindow({
    ...b, minWidth: 360, minHeight: 200, frame: false, icon: ICON, backgroundColor: '#14181d', show: false,
    webPreferences: {preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true},
  });
  const w = {win, tabs: [], active: null, topmost: readState().topmost || 'always', ready: false, size: null, mini: false, module};
  windows.push(w);
  if (module) groupWith(win, module);   // タスクバーではモジュールの窓と同じ仲間（同じ ID・アイコン）
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
  s.owner.active = id; current = s.owner; s.unseen = false; s.unread = false;
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
  const w = openWindow({bounds: from && {...from, x: from.x + 40, y: from.y + 40}, module: s.kind === 'workspace' ? s.dir : null});
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
  link.changed();
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
    const screen = screenText(s), read = parser.parse(screen);
    // オペレーターの作業フォルダーは ECOBuild が作った一式なので、初めての「このフォルダーを信頼するか」には信頼すると答える
    if (s.kind === 'operator' && read.state === 'choice' && !s.trusted && /Yes, I trust this folder/i.test(screen)) {
      s.trusted = true;
      const options = screen.split('\n').filter(l => /^\s*❯?\s*(No, exit|Yes, I trust this folder)/.test(l));
      const down = options.findIndex(l => /Yes, I trust/.test(l)) - options.findIndex(l => /❯/.test(l));
      s.proc.write('\x1b[B'.repeat(Math.max(0, down)) + '\r');
      operatorLog.push({role: 'system', text: '（ECOBuild が作ったオペレーターのフォルダーを、初めての確認で「信頼する」にしました）', at: Date.now()});
      saveOperatorLog();
      continue;
    }
    if (read.reply) s.reply = read.reply;
    s.input = read.input || ''; s.choice = read.state === 'choice' ? {question: read.question, choice: read.choice} : null;
    if (read.state !== s.state) {
      // 返答の終わりは Stop フック（status.json の置き場所が分かっているとき）、分からなければ画面で見る
      if (!s.statusDir && s.state === 'thinking' && read.state === 'idle') replied(s, read.reply);
      // Stop フックの返答が届かなかったとき（置き場所が消された等）のために、画面の返答を少し待って使う
      if (s.statusDir && s.state === 'thinking' && read.state === 'idle') s.screenReply = {at: Date.now(), text: read.reply};
      s.state = read.state; changed = true;
    }
    const got = status.poll(s);
    if (got.info) changed = true;
    if (got.replied) { s.screenReply = null; replied(s, got.replied.message); }
    else if (s.screenReply && Date.now() - s.screenReply.at > 4000) { const text = s.screenReply.text; s.screenReply = null; replied(s, text); }
    if (s.kind === 'operator' && read.state === 'idle' && operatorQueue.length) operatorType(operatorQueue.shift());
    if (s.voicePending && read.state === 'idle') { s.voicePending = false; toggleVoice(s, true); }
    // 名前・モデルの変更は、待機中で入力欄が空のときに送る
    if (read.state === 'idle' && !read.input && !s.recording) {
      if (s.pendingTitle) { s.proc.write(`/rename ${s.pendingTitle}\r`); s.pendingTitle = null; }
      else if (s.pendingModel) { s.proc.write(`/model ${s.pendingModel}\r`.replace('/model \r', '/model\r')); s.pendingModel = null; }
    }
    if (s.kind === 'operator' && (s.recording || read.state === 'choice' || read.state === 'starting')) changed = true;   // 聞き取った文・選択肢を右下に出し直す
  }
  if (changed) { pushTabs(); pushDock(); pushOperator(); }
  const now = Date.now();
  if (dropCards(c => c.until !== -1 && c.until < now)) pushDock();
}

// 返答が終わった：最小化中なら右下でバッジとカード。そうでなく最前面が「自動」なら前に出す。
// 見ている（その窓にフォーカスがあり、そのタブを出している）ときは知らせない。知らせ方は notify.style
function replied(s, message) {
  const text = (message || '').trim().slice(0, 1200);
  if (text) s.reply = text;
  if (message?.trim()) s.lastMessage = message.trim();   // 全文（「最後の返答をコピー」）
  if (s.kind === 'operator') { operatorReplied(s, text); return; }
  const w = s.owner; if (!w) return;
  if (w.mini) { s.unseen = true; addCard(s, text); if (notify.style === 'ecobuild') dock.play({id: notify.sound, volume: notify.volume}); return; }
  if (w.topmost === 'auto') bringToFront(w);
  const watching = w.win.isFocused() && w.active === s.id;
  if (w.active !== s.id) { s.unread = true; pushTabs(); }   // 見ていないタブ：タブに印
  if (watching || notify.style === 'off') return;
  if (notify.style === 'ecobuild') { addCard(s, text); dock.play({id: notify.sound, volume: notify.volume}); return; }
  if (Notification.isSupported()) {
    const n = new Notification({title: `${s.num}  ${s.name}`, body: text.replace(/\s+/g, ' ').slice(0, 200) || '返答が終わりました',
                                icon: iconOf(s) ? nativeImage.createFromDataURL(iconOf(s)) : ICON, silent: false});
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

// 右下に出すもの。オペレーター（◆）は、オペレーターモードの間・聞き取り中・起動待ち・考え中・返答の直後に出す（最小化中の
// タブより先に）。聞き取り中は、聞き取った文（オペレーターの入力欄）をカードで出す
let operatorHoldUntil = 0;
function operatorShown() {
  const op = findOperator();
  return !!op && !op.owner && (ringMode === 'operator' || !!op.recording || !!op.voicePending || op.state === 'thinking'
    || op.state === 'choice' || Date.now() < operatorHoldUntil);
}
function pushDock() {
  const hidden = windows.filter(w => w.mini && !w.win.isDestroyed());
  const target = hidden.at(-1), s = target && findSession(target.active);
  const badge = sessions.filter(x => x.unseen && x.owner?.mini).length;
  const op = findOperator();
  let chip = s ? {kind: 'tab', num: s.num, name: s.name, state: s.state, badge} : null;
  const extra = [];
  if (operatorShown()) {
    const state = op.recording ? 'listening' : op.voicePending ? 'starting' : op.state;
    chip = {kind: 'operator', num: '◆', name: 'オペレーター', state, badge};
    if (op.recording || op.voicePending) extra.push({key: 'heard', id: op.id, num: '◆', name: 'オペレーター', label: '聞き取り中',
                                                    text: op.voicePending ? '起動しています。準備ができたら聞き取りを始めます…' : (op.input || '（話してください）')});
    else if (op.state === 'choice' && op.choice) extra.push({key: 'choice', id: op.id, num: '◆', name: 'オペレーター', label: '選択肢',
                                                            text: `${op.choice.question || ''}\n❯ ${op.choice.choice || ''}`.trim()});
  }
  const peekTarget = chip?.kind === 'operator' ? op : s;
  const peek = chip && peekOn && peekTarget?.term ? {lines: parser.lastLines(screenText(peekTarget), 12), input: peekTarget.input} : null;
  dock.update({chip, peek, icons, cards: [...cards.map(c => ({...c, num: findSession(c.id)?.kind === 'operator' ? '◆' : findSession(c.id)?.num ?? c.num,
                                                              kind: findSession(c.id)?.kind === 'operator' ? 'operator' : 'agent'})),
                                          ...extra.map(c => ({...c, kind: 'operator'}))]});
}

// ---- オペレーター（番号 0。裏で動かす） ----------------------------------------------------------------------
function startOperator() {
  let s = findOperator();
  if (s && !s.exited) return s;
  if (!s) {
    s = {id: nextId++, num: 0, name: 'オペレーター', dir: app.getPath('home'), kind: 'operator',
         agent: operatorModel ? `claude --model ${operatorModel}` : '',
         history: [], size: 0, exited: false, state: 'starting', owner: null};
    sessions.push(s);
    spawnSession(s, OPERATOR_SIZE);
  } else restartSession(s.id);
  return s;
}

// 発言を送る（入力欄に貼り付けて Enter）。起動中なら、入力を待つようになってから
function operatorSend(text) {
  text = String(text || '').trim(); if (!text) return;
  const s = startOperator();
  operatorLog.push({role: 'user', text, at: Date.now()}); saveOperatorLog();
  if (s.state === 'idle' || s.state === 'thinking' || s.state === 'waiting') operatorType(text); else operatorQueue.push(text);
  pushOperator();
}
function operatorType(text) {
  const s = findOperator(); if (!s?.proc) return;
  s.proc.write('\x1b[200~' + text + '\x1b[201~');
  setTimeout(() => s.proc?.write('\r'), 120);
}
const KEYS = {up: '\x1b[A', down: '\x1b[B', right: '\x1b[C', left: '\x1b[D', enter: '\r', esc: '\x1b', tab: '\t'};
function operatorKey(name) { const s = findOperator(); if (s?.proc && KEYS[name]) s.proc.write(KEYS[name]); }

function operatorReplied(s, text) {
  operatorLog.push({role: 'agent', text: text || '（返答の文はありませんでした）', at: Date.now()}); saveOperatorLog();
  operatorHoldUntil = notify.hold === -1 ? Infinity : Date.now() + notify.hold;   // 返答の直後は右下に ◆ を残す
  pushOperator();
  // 会話を見ている画面が前にあれば、右下には出さない
  const watching = [...operatorWatchers].some(contents => {
    const w = BrowserWindow.fromWebContents(contents); return w && !w.isDestroyed() && w.isFocused();
  });
  if (!watching && !(s.owner && s.owner.win.isFocused() && s.owner.active === s.id)) {
    addCard(s, text); if (notify.style === 'ecobuild') dock.play({id: notify.sound, volume: notify.volume});
  }
}

// オペレーターを止める（裏で動いているものも終わらせる。次に話しかけたときにまた起動する）
function stopOperator() {
  const s = findOperator(); if (!s) return;
  if (s.recording) toggleVoice(s, false);
  try { s.proc?.kill(); } catch (e) { /* もう終わっている */ }
  s.term?.dispose();
  if (s.owner) leave(s.owner, s);
  sessions.splice(sessions.indexOf(s), 1);
  operatorQueue = [];
  pushTabs(); pushDock(); pushOperator(); pushQuick();
}

function showOperator() {
  const s = startOperator();
  const w = current && !current.win.isDestroyed() && !current.mini ? current : windows.find(x => !x.mini) || openWindow();
  if (w.mini) restoreWindow(w);
  adopt(w, s); select(s.id, true);
}
function hideOperator() {
  const s = findOperator(); if (!s?.owner) return;
  const w = s.owner; leave(w, s); s.owner = null; pushTabs();
}

function operatorView() {
  const s = findOperator();
  // 起動中・選択肢のときは画面の最後の数行も（入力欄が出ないまま止まっているときに、何が出ているか分かるように）
  const screen = s?.term && ['starting', 'choice'].includes(s.state) ? parser.lastLines(screenText(s), 6) : '';
  const startingFor = s?.state === 'starting' && s.startedAt ? Date.now() - s.startedAt : 0;
  return {state: s ? (s.recording ? 'listening' : s.state) : 'none', input: s?.input || '', choice: s?.choice || null, shown: !!s?.owner,
          screen, startingFor, icon: icons.operator,
          log: operatorLog.slice(-100), queued: operatorQueue.length};
}
function pushOperator() {
  pushQuick();
  const view = operatorView();
  for (const contents of operatorWatchers) if (!contents.isDestroyed()) contents.send('operator:update', view);
}
function loadOperatorLog() { try { operatorLog = JSON.parse(fs.readFileSync(OPERATOR_LOG(), 'utf8')).slice(-200); } catch (e) { operatorLog = []; } }
function saveOperatorLog() {
  operatorLog = operatorLog.slice(-200);
  try { fs.writeFileSync(OPERATOR_LOG(), JSON.stringify(operatorLog)); } catch (e) { /* 記録できなくても話せる */ }
}

// ---- 音声入力・キー ------------------------------------------------------------------------------------------
function activeSession() {
  const w = current && !current.win.isDestroyed() ? current : windows[0];
  return w ? findSession(w.active) : null;
}

// 録音の開始・停止（Space のキーリピートを送る間が録音中）
function toggleVoice(s = activeSession(), on = !s?.recording) {
  if (!s?.proc || s.exited) return;
  // 起動中（入力欄がまだない）なら、準備ができてから聞き取りを始める（poll が始める）
  if (on && !s.recording && s.state === 'starting') { s.voicePending = true; pushDock(); if (s.kind === 'operator') pushOperator(); return; }
  if (!on) s.voicePending = false;
  if (on && !s.recording) {
    for (const other of sessions) if (other.recording && other !== s) toggleVoice(other, false);   // 同時に録音するのは1つ
    s.recording = setInterval(() => s.proc?.write(' '), KEY_REPEAT_MS);
  } else if (!on && s.recording) {
    clearInterval(s.recording); s.recording = null;
  }
  pushTabs(); pushDock(); if (s.kind === 'operator') pushOperator();
}

// 送信：録音中なら止め、聞き取りが入力欄に入りきってから（入力欄の文字がしばらく変わらなくなってから）Enter
async function submit(s) {
  if (!s?.proc) return;
  const was = !!s.recording;
  if (was) toggleVoice(s, false);
  if (was) {
    let last = null, stable = 0;
    for (let i = 0; i < 40 && stable < 3; i++) {
      await new Promise(r => setTimeout(r, 200));
      const input = parser.parse(screenText(s)).input ?? '';
      stable = input === last ? stable + 1 : 0; last = input;
    }
  }
  const input = parser.parse(screenText(s)).input || '';
  if (s.kind === 'operator' && input.trim()) { operatorLog.push({role: 'user', text: input.trim(), at: Date.now()}); saveOperatorLog(); pushOperator(); }
  s.proc.write('\r');
}
const submitActive = () => submit(activeSession());

function clear(s) {
  if (!s?.proc) return;
  if (s.recording) { toggleVoice(s, false); s.proc.write('\x1b'); return; }   // 録音中は取り消す（Esc：聞き取りを捨てる）
  s.proc.write('\x15'.repeat(CLEAR_REPEAT));
}
const clearActive = () => clear(activeSession());

// 前・次のタブ（番号の順。別の窓のタブなら、その窓へ）
function step(delta) {
  const list = sessions.filter(s => s.owner).sort((a, b) => a.num - b.num);
  if (!list.length) return;
  const at = list.indexOf(activeSession());
  const next = list[(at + delta + list.length) % list.length];
  if (next.owner.mini) restoreWindow(next.owner);
  select(next.id, true);
}

function registerShortcuts() {
  const taken = [];
  for (const [key, run] of Object.entries(SHORTCUTS)) {
    try { if (!globalShortcut.register(key, run)) taken.push(key); } catch (e) { taken.push(key); }
  }
  if (taken.length) console.warn('agents: これらのキーはほかのアプリが使っています：', taken.join(', '));
}

// ---- リング ----------------------------------------------------------------------------------------------
function ringView() { return {...ring.status(), mode: ringMode, enabled: ringConfig.enabled, match: ringConfig.match,
                              guard: ringConfig.guard, keepalive: ringConfig.keepalive, choosing: !!choosing,
                              resident: ring.residentEnabled()}; }
// ほかの窓（ハブ）でリング・オペレーターの様子を出すもの（agents:status-watch）
const statusWatchers = new Set();
function quickView() { const op = findOperator(); return {ring: ringView(), operator: {running: !!op && !op.exited, state: op?.state || 'none'}}; }
function pushQuick() { const view = quickView(); for (const c of statusWatchers) if (!c.isDestroyed()) c.send('agents:quick', view); }
function pushRing() { for (const w of windows) send(w, 'agents:ring', ringView()); pushQuick(); }

function setRing(patch) {
  const {resident, ...rest} = patch;
  ringConfig = {...ringConfig, ...rest};
  writeState({ring: ringConfig});
  // 常駐：選んだとき・識別子などが変わったときに置き直す（常駐は ECOBuild が閉じている間だけ働く）
  if (resident === false) ring.disableResident();
  else if (resident === true || (ring.residentEnabled() && ['match', 'guard', 'keepalive'].some(k => k in rest))) {
    if (ringConfig.match) ring.enableResident(ringConfig);
  }
  if (ringConfig.enabled && ringConfig.match) ring.start(ringConfig); else ring.stop();
  pushRing();
}

function setRingMode(next) {
  if (next === ringMode || !['work', 'operator'].includes(next)) return;
  ringMode = next; choosing = null; pushRing(); pushDock();
}

async function onGesture(gesture, gestureMode) {
  const now = Date.now();
  if (gesture === 'click') ignoreHoldUntil = now + HOLD_AFTER_CLICK_MS;
  if (gesture.startsWith('hold_') && now < ignoreHoldUntil) { ignoreHoldUntil = now + HOLD_AFTER_CLICK_MS; return; }
  if (gestureMode) setRingMode(gestureMode === 'work' ? 'work' : 'operator');
  // タブの一覧が出ている間：上・左で前、下・右で次、押し込みで決定、ほかで閉じる
  if (pickerWindow && !pickerWindow.win.isDestroyed()) { send(pickerWindow, 'agents:picker-key', gesture); return; }
  if (gesture === 'tap' && cards.length) { dropCards(() => true); pushDock(); return; }   // 右下の返答を閉じる
  // 選択肢：出ているときに押し込むと選択モードへ。その間は上下左右で選び、押し込みで決定
  const target = ringMode === 'operator' ? findOperator() : activeSession();
  if (target && !target.recording) {
    const shown = parser.parse(screenText(target)).state === 'choice';
    if (!shown) choosing = null;
    else if (choosing !== target.id && gesture === 'click') { choosing = target.id; pushRing(); return; }
    else if (choosing === target.id && ringConfig.choice_actions[gesture]) {
      runAction(ringConfig.choice_actions[gesture], target);
      if (gesture === 'click') { choosing = null; pushRing(); }
      return;
    }
  }
  const action = (ringMode === 'operator' ? ringConfig.operator_actions : ringConfig.actions)[gesture];
  if (action) runAction(action);
}

// 動作の名前：prev・next・submit・clear・clear_or_minimize・voice・scroll_up・scroll_down・minimize・picker・dismiss・
// operator_voice・operator_submit・operator_clear・operator（タブで開く・裏に戻す）・mode。
// key:<名前>（タブへキー：up・down・left・right・enter・esc）・text:<文字>（タブへ文字）・oskey:<組み合わせ>（前面のアプリへ）
function runAction(action, target = null) {
  const s = target || activeSession();
  if (action.startsWith('key:')) { const k = KEYS[action.slice(4)]; if (k) s?.proc?.write(k); return; }
  if (action.startsWith('text:')) { s?.proc?.write(action.slice(5)); return; }
  if (action.startsWith('oskey:')) { ring.keys(action.slice(6)); return; }
  const w = s?.owner || current;
  switch (action) {
    case 'prev': return step(-1);
    case 'next': return step(1);
    case 'submit': return submit(s);
    case 'clear': return clear(s);
    case 'clear_or_minimize': {
      const mini = windows.find(x => x.mini);
      if (mini) return restoreWindow(mini);
      if (s && (s.recording || (parser.parse(screenText(s)).input || '').trim())) return clear(s);
      if (w && !w.mini) return minimizeWindow(w);
      return;
    }
    case 'voice': return toggleVoice(s);
    case 'scroll_up': case 'scroll_down':
      if (s?.owner) send(s.owner, 'agents:scroll', s.id, (action === 'scroll_up' ? -1 : 1) * ringConfig.scroll_lines);
      return;
    case 'minimize': return w?.mini ? restoreWindow(w) : w && minimizeWindow(w);
    case 'picker': return w && send(w, 'agents:picker');
    case 'dismiss': dropCards(() => true); peekOn = false; return pushDock();
    case 'operator_voice': { const op = startOperator(); return toggleVoice(op, !(op.recording || op.voicePending)); }
    case 'operator_submit': return submit(findOperator());
    case 'operator_clear': return clear(findOperator());
    case 'operator': return findOperator()?.owner ? hideOperator() : showOperator();
    case 'mode': return setRingMode(ringMode === 'work' ? 'operator' : 'work');
  }
}

// ---- 外からの操作（GUI のサーバーを通して：ecobuild gui agent-… ） --------------------------------------------
const byNum = num => sessions.find(s => s.num === Number(num));
function external(op, p) {
  if (op === 'agent-open') return openSession({dir: p.dir, name: p.name || '', agent: p.agent || ''});
  if (op === 'agent-send') {
    const s = byNum(p.tab); if (!s?.proc) return;
    if (s.kind === 'operator') { operatorSend(p.text); return; }
    s.proc.write('\x1b[200~' + p.text + '\x1b[201~');
    if (p.enter !== false) setTimeout(() => s.proc?.write('\r'), 120);
    return;
  }
  if (op === 'agent-show') { const s = byNum(p.tab); if (s?.kind === 'operator') showOperator(); else if (s) focusTab(s.id); return; }
  if (op === 'agent-close') { const s = byNum(p.tab); if (s) closeSession(s.id); return; }
  if (op === 'agent-rename') { const s = byNum(p.tab); if (s && s.kind !== 'operator') renameSession(s.id, p.name); return; }
  if (op === 'agent-restart') {
    const s = byNum(p.tab); if (!s) return;
    const base = s.kind === 'operator' ? s.agent.replace(' --continue', '') : (s.savedAgent || '');
    restartSession(s.id, p.continue ? (base || 'claude') + ' --continue' : base);
    return;
  }
  if (op === 'agent-model') { const s = byNum(p.tab); if (s && isClaude(s)) s.pendingModel = String(p.model); return; }
  if (op === 'agents-window') {
    if (p.state === 'minimize') for (const w of windows.filter(x => !x.mini)) minimizeWindow(w);
    else for (const w of windows.filter(x => x.mini)) restoreWindow(w);
    return;
  }
  if (op === 'operator') { if (p.state === 'show') showOperator(); else hideOperator(); }
}
function externalList() {
  return sessions.map(s => ({num: s.num, name: s.name, dir: s.kind === 'operator' ? null : s.dir, kind: s.kind, state: s.state,
                             reply: s.reply || '', minimized: !!s.owner?.mini, shown: !!s.owner}));
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

function setup({ecobuild, python, group}) {
  ecobuildPath = ecobuild;
  if (group) groupWith = group;
  loadOperatorLog();
  const saved = readState();
  if (OPERATOR_MODELS.includes(saved.operatorModel)) operatorModel = saved.operatorModel;
  if (saved.icons) icons = {operator: String(saved.icons.operator || ''), agent: String(saved.icons.agent || '')};
  loadStyles();
  reopenTabs = saved.reopen !== false;
  if (reopenTabs && Array.isArray(saved.tabs) && saved.tabs.length) {
    setTimeout(() => { for (const t of saved.tabs) if (t?.dir) try { openSession({dir: t.dir, name: t.name, agent: t.agent || '', resume: true}); } catch (e) { /* もうない */ } }, 1500);
  }
  ringConfig = {...RING_DEFAULTS, ...(saved.ring || {})};
  for (const key of ['actions', 'operator_actions', 'choice_actions']) ringConfig[key] = {...RING_DEFAULTS[key], ...(saved.ring?.[key] || {})};
  ring.setup({python: python || (() => 'python'), onGesture: (g, m) => onGesture(g, m).catch(() => {}), onStatus: pushRing});
  ring.markRunning();   // 常駐に、ECOBuild が動いていることを知らせる（常駐はその間リングを手放す）
  if (ringConfig.enabled && ringConfig.match) ring.start(ringConfig);
  notify = {...NOTIFY_DEFAULTS, ...(saved.notify || {})};
  dock.setup({
    initialAnchor: saved.dock, onAnchor: anchor => writeState({dock: anchor}),
    actions: {
      peek: () => { peekOn = !peekOn; pushDock(); },
      // ◆ を押す：オペレーターをタブで開く（開いていれば裏に戻す）
      operator: () => { if (findOperator()?.owner) hideOperator(); else showOperator(); pushDock(); },
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
  // クリップボード（窓の画面からは使えないことがあるので main で）
  ipcMain.on('agents:copy', (event, text) => { if (typeof text === 'string' && text) clipboard.writeText(text); });
  ipcMain.handle('agents:paste', () => clipboard.readText());
  ipcMain.handle('agents:last-reply', (event, id) => findSession(id)?.lastMessage || findSession(id)?.reply || '');
  // ＋：このPCの作業空間（ecobuild workspace list）
  ipcMain.handle('agents:workspaces', () => new Promise(resolve => require('child_process').execFile(ecobuildPath(),
    ['workspace', 'list', '--json'], {windowsHide: true, timeout: 30000, env: {...process.env, PYTHONIOENCODING: 'utf-8'}}, (error, stdout) => {
      try { resolve((JSON.parse(String(stdout).trim().split('\n').pop()).result || []).filter(w => w.exists !== false)); }
      catch (e) { resolve([]); }
    })));
  ipcMain.on('agents:ready', event => {
    const w = windowOf(event); if (!w) return;
    w.ready = true;
    for (const id of w.tabs) { const s = findSession(id); send(w, 'agents:adopt', describe(s), s.history.join('')); }
    if (w.pending) { const s = w.pending; w.pending = null; adopt(w, s); }
    send(w, 'agents:topmost', w.topmost);
    send(w, 'agents:notify', notify, HOLD_STEPS);
    send(w, 'agents:ring', ringView());
    send(w, 'agents:prefs', prefsView());
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
  // オペレーター（ハブの「AI に頼む」から）
  ipcMain.handle('operator:watch', (event, on) => {
    if (on) { operatorWatchers.add(event.sender); event.sender.once('destroyed', () => operatorWatchers.delete(event.sender)); startOperator(); }
    else operatorWatchers.delete(event.sender);
    return operatorView();
  });
  ipcMain.on('operator:send', (event, text) => operatorSend(text));
  ipcMain.on('operator:run', (event, on) => { if (on) { startOperator(); pushQuick(); } else stopOperator(); });
  ipcMain.handle('agents:status-watch', event => {
    statusWatchers.add(event.sender); event.sender.once('destroyed', () => statusWatchers.delete(event.sender));
    return quickView();
  });
  ipcMain.on('operator:key', (event, name) => operatorKey(name));
  ipcMain.on('operator:show', (event, on) => (on ? showOperator() : hideOperator()));
  ipcMain.on('operator:restart', () => { const s = findOperator(); if (s) restartSession(s.id); else startOperator(); });
  ipcMain.on('operator:clear', () => { operatorLog = []; saveOperatorLog(); pushOperator(); });
  ipcMain.on('operator:voice', (event, on) => toggleVoice(startOperator(), on));
  ipcMain.on('operator:voice-submit', () => submit(findOperator()));
  ipcMain.on('operator:voice-clear', () => clear(findOperator()));
  ipcMain.on('agents:voice', (event, id) => toggleVoice(findSession(id)));
  ipcMain.on('agents:submit', (event, id) => submit(findSession(id)));
  ipcMain.on('agents:clear-input', (event, id) => clear(findSession(id)));
  registerShortcuts();
  ipcMain.on('agents:ring-config', (event, patch) => setRing(patch || {}));
  ipcMain.on('agents:model', (event, id, model) => { const s = findSession(id); if (s && isClaude(s)) s.pendingModel = String(model || ''); });
  ipcMain.on('agents:picker-open', (event, open) => { const w = windowOf(event); pickerWindow = open ? w : (pickerWindow === w ? null : pickerWindow); });
  ipcMain.on('agents:prefs', (event, patch) => {
    if (patch && OPERATOR_MODELS.includes(patch.operatorModel)) { operatorModel = patch.operatorModel; writeState({operatorModel}); }
    if (patch && typeof patch.reopen === 'boolean') { reopenTabs = patch.reopen; writeState({reopen: reopenTabs}); }
    pushPrefs();
  });
  ipcMain.handle('agents:icon-pick', async (event, kind) => {
    if (!(kind in icons)) return;
    const w = windowOf(event);
    const picked = await dialog.showOpenDialog(w?.win, {title: 'アイコンの画像', properties: ['openFile'],
      filters: [{name: '画像', extensions: ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'ico']}]});
    if (picked.canceled || !picked.filePaths[0]) return;
    const image = nativeImage.createFromPath(picked.filePaths[0]);
    if (image.isEmpty()) return;
    const {width, height} = image.getSize(), side = Math.min(width, height);   // 真ん中の正方形を 96px に
    icons[kind] = image.crop({x: Math.floor((width - side) / 2), y: Math.floor((height - side) / 2), width: side, height: side})
      .resize({width: 96, height: 96, quality: 'best'}).toDataURL();
    writeState({icons}); pushPrefs(); pushTabs(); pushDock(); pushOperator();
  });
  ipcMain.on('agents:icon-clear', (event, kind) => {
    if (!(kind in icons)) return;
    icons[kind] = ''; writeState({icons}); pushPrefs(); pushTabs(); pushDock(); pushOperator();
  });
  ipcMain.handle('agents:style-set', async (event, kind, text) => {
    if (!(kind in styles)) return;
    const key = kind === 'operator' ? 'operator_style' : 'agent_style';
    const value = String(text || '').trim();
    const ok = await ecobuildRun(value ? ['config', 'set', key, value] : ['config', 'unset', key]);
    if (ok) styles[kind] = value;
    pushPrefs();
    return ok;
  });
  ipcMain.handle('agents:ring-find', () => ring.find());
  ipcMain.on('agents:ring-calibrate', (event, prefix) => {
    if (ringConfig.match) ring.calibrate({match: ringConfig.match, prefix: prefix || ''});
  });
  setInterval(poll, POLL_MS);
  app.on('before-quit', () => {
    app.isQuitting = true; link.stop(); globalShortcut.unregisterAll(); ring.stop();
    for (const s of sessions) if (!s.exited) try { s.proc?.kill(); } catch (e) { /* 終わっている */ }
  });
}

// GUI のサーバーにつなぐ（外からの操作を受ける。main.js がサーバーの起動後に呼ぶ）
function connect(hubUrl, openPage) { link.connect(hubUrl, {describe: externalList, handle: external, openPage}); }

// 外から（試験・GUIの操作）：タブに文字を送る
function input(id, data) { findSession(id)?.proc?.write(data); }

// 試験用：番号のタブの画面の文字
function screenOf(num) { const s = sessions.find(x => x.num === num); return s?.term ? screenText(s) : ''; }

module.exports = {setup, connect, openSession, input, operatorSend, screenOf, sessions: () => sessions.map(describe),
                  operator: () => operatorView()};

// ---- アイコン・話し方 ----------------------------------------------------------------------------------
function prefsView() {
  return {operatorModel, operatorModels: OPERATOR_MODELS, reopen: reopenTabs, icons, styles};
}
function pushPrefs() { for (const w of windows) send(w, 'agents:prefs', prefsView()); }

// ecobuild を実行する（設定の読み書き）。答えの JSON を返す（失敗は null）
function ecobuildRun(args) {
  return new Promise(resolve => {
    const program = ecobuildPath?.(); if (!program) return resolve(null);
    require('child_process').execFile(program, [...args, '--json'], {windowsHide: true, timeout: 30000, encoding: 'utf8'}, (error, stdout) => {
      try { const doc = JSON.parse(String(stdout).trim().split(/\r?\n/).pop()); resolve(doc.ok ? doc : null); } catch (e) { resolve(null); }
    });
  });
}
async function loadStyles() {
  for (const [kind, key] of [['operator', 'operator_style'], ['agent', 'agent_style']]) {
    const doc = await ecobuildRun(['config', 'get', key]);
    styles[kind] = doc?.result?.value || '';
  }
  pushPrefs();
}
