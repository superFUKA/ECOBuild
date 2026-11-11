'use strict';
// 新しい GUI（eco_gui）のアプリの窓（Electron）。ここは窓を出すだけ。画面も処理も、中継地点（python -m eco_gui.app serve）が受け持つ。
//   electron <このフォルダー> --url=<窓の URL> --title=<題> --size=<幅>x<高さ>
// - 2つめの起動は、動いているアプリに窓を開かせる（タスクバーで1つのアプリにまとまる）。
// - 開くのは、この PC の中継地点（http://127.0.0.1:<ポート>/）の窓だけ。ほかの URL は開かない。
// - 窓をすべて閉じると、アプリも終わる（中継地点は別のプロセス。窓がなくなって少しすると、自分で終わる）。
// - 窓の上の帯は、アプリのもの（Windows・Linux）：OS の題の帯を隠し、閉じる・最大化・最小化のボタンだけをアプリの色で残す。
//   帯そのもの（アイコンと題・つかんで動かす所）はページが描く（theme.css の eco-frameless）。ここは、その印と題をページに付ける。
// - --smoke：窓を見せずに読み込み、題を標準出力に出して終わる（試験用）。
const {app, BrowserWindow, Menu, shell} = require('electron');
const path = require('path');

const ICON = path.join(__dirname, '..', '..', 'icon.ico');
const LOCAL = /^http:\/\/127\.0\.0\.1:\d+\//;
const FRAMELESS = process.platform !== 'darwin';
// 39px：ページの帯は 40px で、下に線が1本ある。ボタンの下にも線が見えるように
const TITLE_BAR = {color: '#14171b', symbolColor: '#a5aeba', height: 39};
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
    width, height, title, icon: ICON, show: !smoke, autoHideMenuBar: true, backgroundColor: '#14171b',
    ...(FRAMELESS ? {titleBarStyle: 'hidden', titleBarOverlay: TITLE_BAR} : {}),
    webPreferences: {contextIsolation: true, sandbox: true},
  });
  // 外へのリンクは、いつものブラウザーで。窓の中では、中継地点のページだけ
  window.webContents.setWindowOpenHandler(({url: target}) => {
    if (/^https?:\/\//.test(target) && !LOCAL.test(target)) shell.openExternal(target);
    return {action: 'deny'};
  });
  window.webContents.on('will-navigate', (event, target) => { if (!LOCAL.test(target)) event.preventDefault(); });
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
  app.whenReady().then(() => {
    Menu.setApplicationMenu(null);
    if (!open(request(process.argv))) app.quit();   // 開く窓がない（URL がない・この PC の中継地点でない）
  });
}
