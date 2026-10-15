'use strict';
// ECOBuild GUI の窓（Electron）。画面と処理は今までどおり gui/app.py のサーバーが受け持ち、ここは窓を出すだけ。
// - 起動すると、このアプリ専用のサーバー（app.py --electron）を子プロセスで動かし、ハブの窓を開く。
// - 窓をすべて閉じる、またはハブの「GUIを終了」でサーバーが終わると、アプリも終わる（サーバーは標準入力が閉じたら終わる）。
// - 2つめの起動は、動いているアプリにハブの窓を開かせる。
// Python：環境変数 ECOBUILD_GUI_PYTHON、リポジトリの .venv、PATH の python の順。ecobuild の場所：ECOBUILD_GUI_ECOBUILD。
const {app, BrowserWindow, Menu, dialog, shell} = require('electron');
const {spawn} = require('child_process');
const fs = require('fs');
const path = require('path');

const GUI = path.resolve(__dirname, '..');
const ICON = path.join(GUI, 'icon.ico');
const HUB_SIZE = [1000, 720];      // app.py の HUB_WINDOW と同じ（ハブは一覧と設定だけなので小さめ）
const MODULE_SIZE = [1360, 880];   // モジュールの窓

let server = null;      // 子プロセスのサーバー
let hubUrl = '';        // http://127.0.0.1:<port>/hub.html?t=<合言葉>
let quitting = false;

function python() {
  if (process.env.ECOBUILD_GUI_PYTHON) return process.env.ECOBUILD_GUI_PYTHON;
  const venv = process.platform === 'win32'
    ? path.join(GUI, '..', '.venv', 'Scripts', 'python.exe') : path.join(GUI, '..', '.venv', 'bin', 'python');
  return fs.existsSync(venv) ? venv : (process.platform === 'win32' ? 'python' : 'python3');
}

const sameServer = url => { try { return hubUrl && new URL(url).origin === new URL(hubUrl).origin; } catch (e) { return false; } };

function windowOptions([width, height]) {
  return {
    width, height, icon: ICON, backgroundColor: '#14181d', autoHideMenuBar: true,
    webPreferences: {preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true},
  };
}

function openHub() {
  const hub = BrowserWindow.getAllWindows().find(w => new URL(w.webContents.getURL() || hubUrl).pathname === '/hub.html');
  if (hub) {
    if (hub.isMinimized()) hub.restore();
    hub.focus();
    return;
  }
  new BrowserWindow(windowOptions(HUB_SIZE)).loadURL(hubUrl);
}

// Every page: GUI pages open as app windows, other addresses (GitHub etc.) in the default browser.
app.on('web-contents-created', (event, contents) => {
  contents.setWindowOpenHandler(({url}) => {
    if (sameServer(url)) return {action: 'allow', overrideBrowserWindowOptions: windowOptions(MODULE_SIZE)};
    if (/^https?:/i.test(url)) shell.openExternal(url);
    return {action: 'deny'};
  });
  contents.on('will-navigate', (e, url) => {
    if (sameServer(url)) return;
    e.preventDefault();
    if (/^https?:/i.test(url)) shell.openExternal(url);
  });
  // メニューは出さないので、開発用の操作だけキーで残す。
  contents.on('before-input-event', (e, input) => {
    if (input.type !== 'keyDown') return;
    if (input.key === 'F12' || (input.control && input.shift && input.key.toLowerCase() === 'i')) contents.toggleDevTools();
    else if (input.key === 'F5' || (input.control && input.key.toLowerCase() === 'r')) contents.reload();
  });
});

function startServer() {
  const args = [path.join(GUI, 'app.py'), '--electron'];
  if (process.env.ECOBUILD_GUI_ECOBUILD) args.push('--ecobuild', process.env.ECOBUILD_GUI_ECOBUILD);
  server = spawn(python(), args, {
    cwd: GUI, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
    env: {...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8'},
  });
  let output = '';
  const read = chunk => {
    output += chunk.toString('utf8');
    const found = !hubUrl && output.match(/http:\/\/127\.0\.0\.1:\d+\/hub\.html\?t=[\w-]+/);   // app.py の「ECOBuild GUI：<URL>」
    if (found) {
      hubUrl = found[0];
      openHub();
    }
  };
  server.stdout.on('data', read);
  server.stderr.on('data', read);
  server.on('error', error => {
    dialog.showErrorBox('ECOBuild GUI', `GUIのサーバーを起動できませんでした（${python()}）：${error.message}`);
    app.quit();
  });
  server.on('exit', code => {
    server = null;
    if (!hubUrl && !quitting) dialog.showErrorBox('ECOBuild GUI', `GUIのサーバーが終了しました（${code}）。\n\n${output.trim().slice(-2000)}`);
    app.quit();   // 「GUIを終了」でサーバーが終わったときも、アプリを終える
  });
}

function stopServer() {
  quitting = true;
  if (server) {
    server.stdin.end();   // 標準入力が閉じるとサーバーは終わる
    const running = server;
    setTimeout(() => { if (running.exitCode === null) running.kill(); }, 3000).unref();
  }
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.setAppUserModelId('ECOBuild.GUI');
  app.on('second-instance', () => { if (hubUrl) openHub(); });
  app.on('window-all-closed', () => app.quit());
  app.on('before-quit', stopServer);
  app.whenReady().then(() => {
    Menu.setApplicationMenu(null);
    startServer();
  });
}
