'use strict';
// 新しい GUI（eco_gui）のアプリの窓（Electron）。ここは窓を出すだけ。画面も処理も、中継地点（python -m eco_gui.app serve）が受け持つ。
//   electron <このフォルダー> --url=<窓の URL> --title=<題> --size=<幅>x<高さ>
// - 2つめの起動は、動いているアプリに窓を開かせる（タスクバーで1つのアプリにまとまる）。
// - 開くのは、この PC の中継地点（http://127.0.0.1:<ポート>/）の窓だけ。ほかの URL は開かない。
// - 窓をすべて閉じると、アプリも終わる（中継地点は別のプロセス。窓がなくなって少しすると、自分で終わる）。
// - 窓の上の帯は、アプリのもの（Windows・Linux）：OS の題の帯を隠し、閉じる・最大化・最小化のボタンだけをアプリの色で残す。
//   帯そのもの（アイコンと題・つかんで動かす所）はページが描く（theme.css の eco-frameless）。ここは、その印と題をページに付ける。
// - 窓の大きさの下限：これより小さいと、左のメニューと中身が崩れる（前の GUI と同じ）。
// - F5・Ctrl+R で読み直し、F12・Ctrl+Shift+I で開発の道具（メニューは出さないので、キーだけ残す）。
// - --smoke：窓を見せずに読み込み、題を標準出力に出して終わる（試験用）。
const {app, BrowserWindow, Menu, ipcMain, shell} = require('electron');
const path = require('path');

const ICON = path.join(__dirname, '..', '..', 'icon.ico');
const LOCAL = /^http:\/\/127\.0\.0\.1:\d+\//;
const FRAMELESS = process.platform !== 'darwin';
// 39px：ページの帯は 40px で、下に線が1本ある。ボタンの下にも線が見えるように
const TITLE_BAR = {color: '#14171b', symbolColor: '#a5aeba', height: 39};
const MIN_WIDTH = 760, MIN_HEIGHT = 480;
const MARK = `document.documentElement.classList.add('eco-frameless'); document.body.dataset.ecoTitle = document.title.replace(/ — ECOBuild$/, '');`;

function request(argv) {
  const value = name => (argv.find(a => a.startsWith(`--${name}=`)) || '').slice(name.length + 3);
  const [width, height] = value('size').split('x').map(Number);
  return {url: value('url'), title: value('title') || 'ECOBuild', width: width || 900, height: height || 640,
          smoke: argv.includes('--smoke')};
}

function open({url, title, width, height, smoke}) {
  if (!LOCAL.test(url)) return null;
  const window = new BrowserWindow({
    width, height, minWidth: Math.min(MIN_WIDTH, width), minHeight: Math.min(MIN_HEIGHT, height),
    title, icon: ICON, show: !smoke, autoHideMenuBar: true, backgroundColor: '#14171b',
    ...(FRAMELESS ? {titleBarStyle: 'hidden', titleBarOverlay: TITLE_BAR} : {}),
    webPreferences: {preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true},
  });
  // 外へのリンクは、いつものブラウザーで。窓の中では、中継地点のページだけ
  window.webContents.setWindowOpenHandler(({url: target}) => {
    if (/^https?:\/\//.test(target) && !LOCAL.test(target)) shell.openExternal(target);
    return {action: 'deny'};
  });
  window.webContents.on('will-navigate', (event, target) => { if (!LOCAL.test(target)) event.preventDefault(); });
  window.webContents.on('before-input-event', (event, input) => {
    if (input.type !== 'keyDown') return;
    const key = input.key.toLowerCase();
    if (input.key === 'F12' || (input.control && input.shift && key === 'i')) window.webContents.toggleDevTools();
    else if (input.key === 'F5' || (input.control && !input.shift && key === 'r')) window.webContents.reload();
  });
  if (FRAMELESS) {
    const mark = () => { window.webContents.executeJavaScript(MARK).catch(() => {}); };  // 読み込むたび・題が変わるたび
    window.webContents.on('dom-ready', mark);
    window.on('page-title-updated', () => setTimeout(mark, 0));
  }
  if (smoke) {
    window.webContents.once('did-finish-load', () => { console.log(`loaded: ${window.webContents.getTitle()}`); app.quit(); });
    window.webContents.once('did-fail-load', (event, code, text) => { console.log(`failed: ${text}`); app.exit(1); });
  }
  window.loadURL(url);
  return window;
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.setAppUserModelId('ECOBuild.GUI.Next');
  app.on('second-instance', (event, argv) => { open(request(argv)); });
  app.on('window-all-closed', () => app.quit());
  // 開いている画面をもう一度開くよう頼まれた（preload.js の gf-raise）：その窓を前に出す
  ipcMain.on('raise', (event) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    if (!window) return;
    if (window.isMinimized()) window.restore();
    window.show();
    window.focus();
  });
  app.whenReady().then(() => {
    Menu.setApplicationMenu(null);
    if (!open(request(process.argv))) app.quit();   // 開く窓がない（URL がない・この PC の中継地点でない）
  });
}
