'use strict';
// リング（Ring II）の受信係（Electron の main）：ring/listener.py を子プロセスで動かし、ジェスチャー・状態を受け取る。
// 登録表（どの信号がどの操作か）はこのアプリの設定の場所（ring-gestures.json）。調整は新しい窓で listener の --calibrate。
// ほかのアプリも同じリングを受けていると二重に反応するので、使うかは設定で選ぶ（既定は使わない）。
const {app} = require('electron');
const {spawn, execFile} = require('child_process');
const path = require('path');
const readline = require('readline');

const LISTENER = path.join(__dirname, 'ring', 'listener.py').replace('app.asar', 'app.asar.unpacked');
const GESTURES = ['up', 'down', 'left', 'right', 'click', 'hold_left', 'hold_right', 'tap'];
const table = () => path.join(app.getPath('userData'), 'ring-gestures.json');
const logFile = () => path.join(app.getPath('userData'), 'ring.log');

let proc = null, python = () => 'python', handlers = {}, wanted = null, calibrating = null;
let status = {online: false, connected: false, calibrated: false, battery: null, message: '使っていません'};

function setup(options) { python = options.python; handlers = options; }

function publish(patch) { status = {...status, ...patch}; handlers.onStatus?.(status); }

// 動かす（options：{match, guard, keepalive}）。同じ設定で動いていれば何もしない
function start(options) {
  wanted = options;
  if (calibrating) return;
  stop(false);
  if (!options?.match) { publish({online: false, connected: false, message: 'リングの識別子がありません（⚙ の「探す」）'}); return; }
  const args = [LISTENER, '--serve', '--match', options.match, '--table', table(), '--log', logFile()];
  if (options.guard === false) args.push('--no-guard');
  if (options.keepalive !== false) args.push('--keepalive');
  const child = spawn(python(), args, {windowsHide: true, env: {...process.env, PYTHONUNBUFFERED: '1', PYTHONUTF8: '1'}});
  proc = child;
  publish({online: true, message: '起動中'});
  readline.createInterface({input: child.stdout}).on('line', line => {
    let m; try { m = JSON.parse(line); } catch (e) { return; }
    if (m.event === 'gesture') handlers.onGesture?.(m.gesture, m.mode || null);
    else if (m.event === 'status') publish({connected: !!m.connected, calibrated: !!m.calibrated, message: m.connected ? 'つながっています' : '見つかりません（リングを操作して起こしてください）'});
    else if (m.event === 'ble') publish({battery: m.battery ?? status.battery, ...(m.connected === undefined ? {} : {connected: !!m.connected})});
  });
  child.stderr.on('data', d => console.error('[ring]', d.toString().trim()));
  child.on('error', error => { if (proc === child) proc = null; publish({online: false, message: `受信係を起動できませんでした：${error.message}`}); });
  child.on('exit', code => { if (proc === child) { proc = null; publish({online: false, message: `受信係が終わりました（${code}）`}); } });
}

function stop(forget = true) {
  if (forget) wanted = null;
  if (proc) { const p = proc; proc = null; try { p.stdin.write(JSON.stringify({cmd: 'quit'}) + '\n'); } catch (e) { /* 終わっている */ } setTimeout(() => p.kill(), 1500); }
  if (forget) publish({online: false, connected: false, message: '使っていません'});
}

// 前面のアプリへキーを送る（割り当ての oskey:）
function keys(combo) { if (proc) proc.stdin.write(JSON.stringify({cmd: 'keys', keys: combo}) + '\n'); }

// つながっている Ring II を探す：[{match, path}]
function find() {
  return new Promise(resolve => execFile(python(), [LISTENER, '--find'], {windowsHide: true, timeout: 20000}, (error, stdout) => {
    try { resolve(JSON.parse(String(stdout).trim().split('\n').pop())); } catch (e) { resolve([]); }
  }));
}

// 調整：新しい窓で各操作を3回ずつ。prefix：リングのモード（LED）で信号が変わる操作を、そのモードの信号として足す
// （operator：オペレーターモード）。調整の間は受信係を止め、終わったら動かし直す
function calibrate({match, prefix = ''}) {
  if (calibrating) return false;
  stop(false);
  const args = [LISTENER, '--calibrate', '--match', match, '--table', table(), '--gestures', ...GESTURES];
  if (prefix) args.push('--prefix', prefix, '--repeat', '2');
  calibrating = spawn(python(), args, {detached: true, stdio: 'ignore', windowsHide: false});   // 自分の窓（コンソール）で
  publish({message: '調整中（開いた窓の案内に従ってください）'});
  calibrating.on('exit', () => { calibrating = null; if (wanted) start(wanted); });
  calibrating.on('error', error => { calibrating = null; publish({message: `調整を始められませんでした：${error.message}`}); });
  return true;
}

// ---- 常駐（PC にサインインしたときから。ECOBuild が閉じている間だけ働く：listener の --resident） ----------------
// 設定は ring-resident.json（これを消すと常駐は1秒ほどで終わる）。サインインのたびに起動するのは、スタートアップの
// ショートカット（管理者の権限は要らない）。ECOBuild が動いているかは running.pid（起動のたびに書く）で見分ける。
const fs = require('fs');
const os = require('os');
const runningFile = () => path.join(app.getPath('userData'), 'running.pid');
const residentFile = () => path.join(app.getPath('userData'), 'ring-resident.json');
const startupLink = () => path.join(process.env.APPDATA || os.homedir(), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup', 'ECOBuild リング.lnk');

function markRunning() { try { fs.writeFileSync(runningFile(), String(process.pid)); } catch (e) { /* 常駐が待たないだけ */ } }

// 窓を出さない Python（pythonw）。なければ python
function windowless() {
  const p = python();
  const w = p.replace(/python(\.exe)?$/i, m => (m.toLowerCase().endsWith('.exe') ? 'pythonw.exe' : 'pythonw'));
  return w !== p && fs.existsSync(w) ? w : p;
}

function residentEnabled() { return fs.existsSync(residentFile()); }

function enableResident(options) {
  const config = {match: options.match, table: table(), running: runningFile(), guard: options.guard !== false,
                  keepalive: options.keepalive !== false, log: path.join(app.getPath('userData'), 'ring-resident.log'),
                  launch: [process.execPath, ...(app.isPackaged ? [] : [app.getAppPath()])]};
  const restart = residentEnabled();
  if (restart) fs.rmSync(residentFile(), {force: true});   // 動いている常駐を一度終わらせる（設定を読み直させる）
  setTimeout(() => {
    fs.writeFileSync(residentFile(), JSON.stringify(config, null, 2));
    // スタートアップのショートカット（引数は環境変数で渡す：引用符が崩れないように）
    execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command',
      '$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:ECO_LINK); $s.TargetPath = $env:ECO_TARGET; ' +
      '$s.Arguments = $env:ECO_ARGS; $s.WindowStyle = 7; $s.Description = "ECOBuild のリングの常駐"; $s.Save()'],
    {windowsHide: true, env: {...process.env, ECO_LINK: startupLink(), ECO_TARGET: windowless(),
                              ECO_ARGS: `"${LISTENER}" --resident --config "${residentFile()}"`}}, () => {});
    spawn(windowless(), [LISTENER, '--resident', '--config', residentFile()], {detached: true, stdio: 'ignore', windowsHide: true}).unref();
  }, restart ? 1500 : 0);
}

function disableResident() {
  fs.rmSync(residentFile(), {force: true});
  fs.rmSync(startupLink(), {force: true});
}

module.exports = {setup, start, stop, keys, find, calibrate, status: () => status, GESTURES,
                  markRunning, residentEnabled, enableResident, disableResident};
