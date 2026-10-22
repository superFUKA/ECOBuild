'use strict';
// ECOBuild GUI の窓（Electron）。画面と処理は今までどおり gui/app.py のサーバーが受け持ち、ここは窓を出すだけ。
// - 起動すると、このアプリ専用のサーバー（app.py --electron）を子プロセスで動かし、ハブの窓を開く。
// - 窓をすべて閉じる、またはハブの「GUIを終了」でサーバーが終わると、アプリも終わる（サーバーは標準入力が閉じたら終わる）。
// - 2つめの起動は、動いているアプリにハブの窓を開かせる。
// - --open-module=<モジュールのフォルダ>：ハブではなく、そのモジュールの開発環境の窓を開く（開いていれば前に出す）。
//   開発環境の窓はハブとは別のアプリ（モジュールごとの AppUserModelID・アイコン）なので、タスクバーのボタンが分かれ、
//   ピン留めするとそのモジュールを開くボタンになる。ハブを閉じても開発環境の窓は残る（同じサーバーを使う）。
// Python：環境変数 ECOBUILD_GUI_PYTHON、リポジトリの .venv、PATH の python の順。ecobuild の場所：ECOBUILD_GUI_ECOBUILD。
// インストールしたアプリ（Setup.exe。app.isPackaged）は、同梱の Python（resources/python）・GUI（resources/gui）と、
// インストール時に入れた ecobuild（bin/ecobuild.exe）を使う（bundle/ と package.json の build）。
const {app, BrowserWindow, Menu, dialog, ipcMain, shell} = require('electron');
const {spawn} = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const agents = require('./agents');   // エージェントの窓（タブの端末）

const GUI = app.isPackaged ? path.join(process.resourcesPath, 'gui') : path.resolve(__dirname, '..');
const BUNDLED_ECOBUILD = path.join(path.dirname(process.execPath), 'bin', 'ecobuild.exe');
const ICON = path.join(GUI, 'icon.ico');
const MODULE_ICON = path.join(GUI, 'module.ico');   // 開発環境の窓（ハブと見分ける）
const HUB_SIZE = [1000, 720];      // app.py の HUB_WINDOW と同じ（ハブは一覧と設定だけなので小さめ）
const MODULE_SIZE = [1360, 880];   // モジュールの窓
const LOG_SIZE = [1100, 760];      // ファイル・フォルダのログの窓（log.html。いくつも並べる）

let server = null;      // 子プロセスのサーバー
let hubUrl = '';        // http://127.0.0.1:<port>/hub.html?t=<合言葉>
let quitting = false;
let pendingModule = '';   // サーバーが起動する前に頼まれた --open-module

function python() {
  if (process.env.ECOBUILD_GUI_PYTHON) return process.env.ECOBUILD_GUI_PYTHON;
  if (app.isPackaged) return path.join(process.resourcesPath, 'python', 'python.exe');
  const venv = process.platform === 'win32'
    ? path.join(GUI, '..', '.venv', 'Scripts', 'python.exe') : path.join(GUI, '..', '.venv', 'bin', 'python');
  return fs.existsSync(venv) ? venv : (process.platform === 'win32' ? 'python' : 'python3');
}

const sameServer = url => { try { return hubUrl && new URL(url).origin === new URL(hubUrl).origin; } catch (e) { return false; } };

// The window's top is the app's own (Windows・Linux): no system title bar; the close・maximize・minimize buttons stay,
// in the app's colors (titleBarOverlay). The page draws the bar (frameless: preload.js) and makes it draggable.
// 39px: the page's bar is 40px with a line at its bottom, which stays visible under the buttons too.
const TITLE_BAR = {color: '#14171b', symbolColor: '#a5aeba', height: 39};
// minimum: below it the hub's and the module's pages break (the module's sidebar is 290px).
const HUB_MIN = [640, 420], MODULE_MIN = [760, 480];
function windowOptions([width, height], icon = ICON, [minWidth, minHeight] = HUB_MIN) {
  return {
    width, height, minWidth, minHeight, icon, backgroundColor: '#14171b', autoHideMenuBar: true,
    ...(process.platform === 'darwin' ? {} : {titleBarStyle: 'hidden', titleBarOverlay: TITLE_BAR}),
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

// The module's development environment (module.html?path=…) is an app of its own on the taskbar: one AppUserModelID
// per module (app.py module_app_id makes the same one for the module's shortcut), its own icon, and pinning the window
// gives a button that opens that module (relaunchCommand).
const moduleArg = argv => (argv.find(a => a.toLowerCase().startsWith('--open-module=')) || '').slice('--open-module='.length);
const moduleKey = root => root.replaceAll('\\', '/').replace(/\/+$/, '').toLowerCase();
const moduleAppId = root => 'ECOBuild.Module.' + crypto.createHash('sha1').update(moduleKey(root), 'utf8').digest('hex').slice(0, 12);
function moduleOf(url) {
  try { const u = new URL(url); return sameServer(url) && u.pathname === '/module.html' ? u.searchParams.get('path') || '' : ''; }
  catch (e) { return ''; }
}
// The module a window belongs to on the taskbar: its window (module.html?path=), or a window it opened (log.html・panel.html?module=).
// Only the hub is the hub's.
function ownerOf(url) {
  try { const u = new URL(url); return moduleOf(url) || (sameServer(url) && ['/log.html', '/panel.html'].includes(u.pathname) ? u.searchParams.get('module') || '' : ''); }
  catch (e) { return ''; }
}

function asModuleApp(window, root) {
  if (!root || process.platform !== 'win32') return;
  const command = app.isPackaged ? [process.execPath] : [process.execPath, app.getAppPath()];
  window.setAppDetails({
    appId: moduleAppId(root), appIconPath: MODULE_ICON, appIconIndex: 0,
    relaunchCommand: [...command, `--open-module=${root}`].map(a => `"${a}"`).join(' '),
    relaunchDisplayName: path.basename(root),
  });
}

function openModule(root) {
  const open = BrowserWindow.getAllWindows().find(w => moduleKey(moduleOf(w.webContents.getURL())) === moduleKey(root));
  if (open) {
    if (open.isMinimized()) open.restore();
    open.focus();
    return;
  }
  const hub = new URL(hubUrl);
  const window = new BrowserWindow(windowOptions(MODULE_SIZE, MODULE_ICON, MODULE_MIN));
  asModuleApp(window, root);
  window.loadURL(`${hub.origin}/module.html?path=${encodeURIComponent(root)}&t=${hub.searchParams.get('t')}`);
}

const openRequested = argv => { const root = moduleArg(argv); if (root) openModule(root); else openHub(); };

// A panel dragged out of a window (panel.html, as Visual Studio's floating tool window): where it was dropped
// (features left・top・width・height), over the window it came from (parent: it stays in front of it, has no
// taskbar button of its own, and closes with it).
function panelOptions(opener, url, features) {
  const f = Object.fromEntries(String(features || '').split(',').map(kv => kv.split('=').map(s => s.trim())));
  const number = (key, fallback) => Number.isFinite(Number(f[key])) && f[key] !== undefined && f[key] !== '' ? Number(f[key]) : fallback;
  const parent = BrowserWindow.fromWebContents(opener);
  return {
    ...windowOptions([number('width', 900), number('height', 440)], ownerOf(url) ? MODULE_ICON : ICON),
    ...(f.left !== undefined ? {x: number('left', 0), y: number('top', 0)} : {}),
    ...(parent ? {parent} : {}), skipTaskbar: !!parent, minWidth: 360, minHeight: 160,
  };
}

// Every page: GUI pages open as app windows, other addresses (GitHub etc.) in the default browser.
// outlivesOpener: a window stays when the one that opened it closes (closing the hub leaves the modules open).
app.on('web-contents-created', (event, contents) => {
  contents.setWindowOpenHandler(({url, features}) => {
    if (sameServer(url)) {
      const page = new URL(url).pathname;
      const size = page === '/log.html' ? LOG_SIZE : MODULE_SIZE;
      if (page === '/panel.html') return {action: 'allow', overrideBrowserWindowOptions: panelOptions(contents, url, features)};
      return {action: 'allow', outlivesOpener: true,
              overrideBrowserWindowOptions: windowOptions(size, ownerOf(url) ? MODULE_ICON : ICON, page === '/module.html' ? MODULE_MIN : HUB_MIN)};
    }
    if (/^https?:/i.test(url)) shell.openExternal(url);
    return {action: 'deny'};
  });
  contents.on('will-navigate', (e, url) => {
    if (sameServer(url)) return;
    e.preventDefault();
    if (/^https?:/i.test(url)) shell.openExternal(url);
  });
  contents.on('did-create-window', (window, {url}) => asModuleApp(window, ownerOf(url)));
  // メニューは出さないので、開発用の操作だけキーで残す。読み直し（F5・Ctrl+R）は GUI のページだけ：エージェントの窓
  // （file://）では Ctrl+R は端末のキー（Claude Code の履歴の検索）なので、そのまま端末へ通す。
  contents.on('before-input-event', (e, input) => {
    if (input.type !== 'keyDown') return;
    if (input.key === 'F12' || (input.control && input.shift && input.key.toLowerCase() === 'i')) contents.toggleDevTools();
    else if ((input.key === 'F5' || (input.control && input.key.toLowerCase() === 'r')) && !contents.getURL().startsWith('file:')) contents.reload();
  });
});

// The folder picker, attached to the window that asked (preload.js: ecobuildShell.pickFolder). Same answer as the
// server's pick-folder: {path}, empty when nothing was chosen.
ipcMain.handle('pick-folder', async (event, {title, initial} = {}) => {
  const options = {title: title || 'フォルダを選ぶ', properties: ['openDirectory', 'createDirectory']};
  if (initial && fs.existsSync(initial)) options.defaultPath = path.resolve(initial);
  const result = await dialog.showOpenDialog(BrowserWindow.fromWebContents(event.sender), options);
  return {path: result.canceled || !result.filePaths.length ? '' : result.filePaths[0].replaceAll('\\', '/')};
});

// Open a file or folder with its app, or show it in Explorer (reveal), from this process: one the server opens comes up
// behind the window (Windows does not bring a background process's window to the front). Same answer as the server's
// open: {} or {error}.
ipcMain.handle('open-path', async (event, {dir, path: relative = '', reveal = false} = {}) => {
  const root = path.resolve(dir || '.'), target = path.resolve(root, relative || '.');
  if (target !== root && !target.startsWith(root + path.sep)) return {error: 'この場所の外は指定できません。'};
  if (!fs.existsSync(target)) return {error: `見つかりません：${relative}`};
  if (reveal && fs.statSync(target).isFile()) { shell.showItemInFolder(target); return {}; }
  const error = await shell.openPath(target);
  return error ? {error} : {};
});

// The ecobuild the agents' terminals run (as the server's: ECOBUILD_GUI_ECOBUILD, the bundled one, or PATH's).
function ecobuildPath() {
  if (process.env.ECOBUILD_GUI_ECOBUILD) return process.env.ECOBUILD_GUI_ECOBUILD;
  if (app.isPackaged && fs.existsSync(BUNDLED_ECOBUILD)) return BUNDLED_ECOBUILD;
  const names = process.platform === 'win32' ? ['ecobuild.exe', 'ecobuild.cmd', 'ecobuild.bat'] : ['ecobuild'];
  for (const dir of (process.env.PATH || '').split(path.delimiter)) {
    for (const name of names) { const found = path.join(dir, name); if (dir && fs.existsSync(found)) return found; }
  }
  return 'ecobuild';
}

// Bring the asking window up: restored when minimized, shown, in front (the page's window.focus() does neither).
ipcMain.handle('focus-window', event => {
  const window = BrowserWindow.fromWebContents(event.sender);
  if (!window) return;
  if (window.isMinimized()) window.restore();
  window.show();
  window.focus();
});

function startServer() {
  const args = [path.join(GUI, 'app.py'), '--electron'];
  if (process.env.ECOBUILD_GUI_ECOBUILD) args.push('--ecobuild', process.env.ECOBUILD_GUI_ECOBUILD);
  else if (app.isPackaged && fs.existsSync(BUNDLED_ECOBUILD)) args.push('--ecobuild', BUNDLED_ECOBUILD);
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
      agents.connect(hubUrl, page => {   // 画面の窓がないときに頼まれた「開く」（ecobuild gui open 等）
        const url = new URL(page, hubUrl);
        if (url.pathname === '/module.html' && url.searchParams.get('path')) openModule(url.searchParams.get('path'));
        else openHub();
      });   // 外（ecobuild gui・オペレーター）からのエージェントの窓の操作を受ける
      if (pendingModule) openModule(pendingModule); else openHub();
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
  pendingModule = moduleArg(process.argv);
  app.on('second-instance', (event, argv) => {
    if (hubUrl) openRequested(argv);
    else pendingModule = moduleArg(argv) || pendingModule;
  });
  app.on('window-all-closed', () => app.quit());
  app.on('before-quit', stopServer);
  app.whenReady().then(() => {
    Menu.setApplicationMenu(null);
    agents.setup({ecobuild: ecobuildPath, python, group: asModuleApp, module: openModule});   // エージェントの窓はモジュールの窓の仲間
    startServer();
  });
}
