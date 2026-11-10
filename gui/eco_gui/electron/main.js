'use strict';
// 新しい GUI（eco_gui）のアプリの窓（Electron）。ここは窓を出すだけ。画面も処理も、中継地点（python -m eco_gui.app serve）が受け持つ。
//   electron <このフォルダー> --url=<窓の URL> --title=<題> --size=<幅>x<高さ>
// - 2つめの起動は、動いているアプリに窓を開かせる（タスクバーで1つのアプリにまとまる）。
// - 開くのは、この PC の中継地点（http://127.0.0.1:<ポート>/）の窓だけ。ほかの URL は開かない。
// - 窓をすべて閉じると、アプリも終わる（中継地点は別のプロセス。窓がなくなって少しすると、自分で終わる）。
// - --smoke：窓を見せずに読み込み、題を標準出力に出して終わる（試験用）。
const {app, BrowserWindow, Menu, shell} = require('electron');
const path = require('path');

const ICON = path.join(__dirname, '..', '..', 'icon.ico');
const LOCAL = /^http:\/\/127\.0\.0\.1:\d+\//;

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
    webPreferences: {contextIsolation: true, sandbox: true},
  });
  // 外へのリンクは、いつものブラウザーで。窓の中では、中継地点のページだけ
  window.webContents.setWindowOpenHandler(({url: target}) => {
    if (/^https?:\/\//.test(target) && !LOCAL.test(target)) shell.openExternal(target);
    return {action: 'deny'};
  });
  window.webContents.on('will-navigate', (event, target) => { if (!LOCAL.test(target)) event.preventDefault(); });
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
