'use strict';
// 新しい GUI（eco_gui）のアプリの窓（Electron）。ここは窓を出すだけ。画面も処理も、中継地点（python -m eco_gui.app serve）が受け持つ。
//   electron <このフォルダー> --url=<窓の URL> --title=<題> --size=<幅>x<高さ>
//            [--launch=<開き直す起動の JSON の並び>] [--type-icons=<型 → .ico の JSON>] [--module-icon=<型にアイコンがないときの .ico>]
// - 2つめの起動は、動いているアプリに窓を開かせる（タスクバーで1つのアプリにまとまる）。
// - モジュールの窓（画面の引数 module のある窓）は、タスクバーでハブとは別のアプリ：モジュールごとの AppUserModelID・型のアイコン。
//   ピン留めすると、そのモジュールを開くボタンになる（--launch に --module <場所> を足して開き直す。ショートカットと同じ ID：
//   gui/next_commands.py の module_app_id）。どのモジュールの窓かは、開く前に中継地点に窓の表示を聞いて知る（/api/view）。
// - 開くのは、この PC の中継地点（http://127.0.0.1:<ポート>/）の窓だけ。ほかの URL は開かない。
// - 窓をすべて閉じると、アプリも終わる（中継地点は別のプロセス。窓がなくなって少しすると、自分で終わる）。
// - 窓の上の帯は、アプリのもの（Windows・Linux）：OS の題の帯を隠し、閉じる・最大化・最小化のボタンだけをアプリの色で残す。
//   帯そのもの（アイコンと題・つかんで動かす所）はページが描く（theme.css の eco-frameless）。ここは、その印と題をページに付ける。
// - 窓の大きさの下限：これより小さいと、左のメニューと中身が崩れる（前の GUI と同じ）。
// - F5・Ctrl+R で読み直し、F12・Ctrl+Shift+I で開発の道具（メニューは出さないので、キーだけ残す）。
// - 窓のページを描くプロセスが落ちたら（メモリーが尽きた等）、理由を記録して読み直す（枠だけ残って中身が空にならない）。
//   記録は <アプリのデータ>/logs/windows.jsonl。続けて落ちるときは読み直さない（1分に3回まで）。
// - --smoke：窓を見せずに読み込み、題（モジュールの窓なら、そのモジュール・AppUserModelID・アイコンも）を標準出力に出して終わる（試験用）。
const {app, BrowserWindow, Menu, ipcMain, shell} = require('electron');
const crypto = require('crypto');
const fs = require('fs');
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
  const json = (name, fallback) => { try { return JSON.parse(value(name)) || fallback; } catch (e) { return fallback; } };
  const [width, height] = value('size').split('x').map(Number);
  return {url: value('url'), title: value('title') || 'ECOBuild', width: width || 900, height: height || 640,
          smoke: argv.includes('--smoke'), launch: json('launch', []), typeIcons: json('type-icons', {}), moduleIcon: value('module-icon')};
}

// モジュールの窓 ------------------------------------------------------------------------------------------------
// 作業空間（<モジュール>/.ecobuild/w/<名前>）の窓も、そのモジュールのもの
const moduleRoot = folder => String(folder || '').replaceAll('\\', '/').replace(/\/\.ecobuild\/w\/[^/]+\/?$/i, '').replace(/\/+$/, '');
const moduleKey = root => moduleRoot(root).toLowerCase();
// 今までの GUI（app.py の module_app_id）・ショートカット（next_commands.py の module_app_id）と同じ作り方
const moduleAppId = root => 'ECOBuild.Module.' + crypto.createHash('sha1').update(moduleKey(root), 'utf8').digest('hex').slice(0, 12);
function moduleTypeOf(root) {   // .ecobuild/ecobuild.toml の [module] type
  try {
    const text = fs.readFileSync(path.join(root, '.ecobuild', 'ecobuild.toml'), 'utf8');
    const table = text.split(/^\s*\[/m).find(t => t.startsWith('module]')) || '';
    return (table.match(/^\s*type\s*=\s*"([^"]*)"/m) || [])[1] || '';
  } catch (e) { return ''; }
}
function moduleIconOf(root, {typeIcons, moduleIcon}) {
  const found = typeIcons[moduleTypeOf(root)];
  return found && fs.existsSync(found) ? found : moduleIcon && fs.existsSync(moduleIcon) ? moduleIcon : ICON;
}
// 窓の画面の引数 module（中継地点に聞く。窓の URL の #<合言葉>.<窓の印>。読めなければ空：ハブと同じアプリのまま）
async function moduleOf(url) {
  try {
    const target = new URL(url);
    const token = target.hash.slice(1).split('.')[0];
    const id = target.pathname.split('/').pop();
    const response = await fetch(`${target.origin}/api/view/${encodeURIComponent(id)}?token=${encodeURIComponent(token)}`);
    const view = await response.json();
    return view && view.args && typeof view.args.module === 'string' && view.args.module !== '.' ? moduleRoot(view.args.module) : '';
  } catch (e) { return ''; }
}
function asModuleApp(window, root, request) {
  if (!root || process.platform !== 'win32') return;
  const icon = moduleIconOf(root, request);
  window.setIcon(icon);
  window.setAppDetails({
    appId: moduleAppId(root), appIconPath: icon, appIconIndex: 0,
    ...(request.launch.length ? {relaunchCommand: [...request.launch, '--module', root].map(a => `"${a}"`).join(' '),
                                 relaunchDisplayName: path.basename(root)} : {}),
  });
}

// 窓の見た目（題の帯・色・アイコン）とページの設定。最初の窓も、そこから開く子の窓も同じ
function look(icon) {
  return {
    icon, autoHideMenuBar: true, backgroundColor: '#14171b',
    ...(FRAMELESS ? {titleBarStyle: 'hidden', titleBarOverlay: TITLE_BAR} : {}),
    webPreferences: {preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true},
  };
}

// 窓の決まり：外へのリンクはいつものブラウザーで、窓の中は中継地点のページだけ。中継地点が「窓の中に重ねて開く画面」を
// 子の窓で開くとき（window.open。名前が gf- で始まる）は、親付き・モーダルの窓で開く（親が閉じれば閉じる・親を操作できない）。
function sameOrigin(target, page) {
  try { return new URL(target).origin === new URL(page).origin; } catch (e) { return false; }
}

// 窓のページを描くプロセスが落ちた -------------------------------------------------------------------------------
const RELOADS_PER_MINUTE = 3;
function note(record) {
  try {
    const folder = path.join(app.getPath('userData'), 'logs');
    fs.mkdirSync(folder, {recursive: true});
    fs.appendFileSync(path.join(folder, 'windows.jsonl'), JSON.stringify({time: new Date().toISOString(), ...record}) + '\n');
  } catch (e) { /* 書けなくても窓は続ける */ }
}
function recover(window) {
  const reloads = [];
  window.webContents.on('render-process-gone', (event, details) => {
    const now = Date.now();
    while (reloads.length && now - reloads[0] > 60000) reloads.shift();
    const again = details.reason !== 'clean-exit' && reloads.length < RELOADS_PER_MINUTE;
    note({event: 'render-process-gone', reason: details.reason, exit_code: details.exitCode,
          url: window.webContents.getURL().split('#')[0], title: window.getTitle(), reload: again});
    if (!again || window.isDestroyed()) return;
    reloads.push(now);
    window.webContents.reload();
  });
}

function guard(window, icon) {
  recover(window);
  window.webContents.setWindowOpenHandler(({url: target, frameName}) => {
    if (LOCAL.test(target) && sameOrigin(target, window.webContents.getURL()) && /^gf-/.test(frameName || '')) {
      // 子の窓は親が持つ（タスクバーに出ない）ので、最小化させない（戻せなくなる）
      return {action: 'allow', overrideBrowserWindowOptions: {parent: window, modal: true, minimizable: false,
                                                               minWidth: 320, minHeight: 160, ...look(icon)}};
    }
    if (/^https?:\/\//.test(target) && !LOCAL.test(target)) shell.openExternal(target);
    return {action: 'deny'};
  });
  window.webContents.on('did-create-window', (child) => {
    // 親が最小化していると、親が持つ子の窓も隠れる（CLI からの open・時間のかかる実行の後に開くとき）。親を戻して子を見せる
    if (window.isMinimized()) window.restore();
    // 高さは GUIFrameWork が中身（題の帯を含む）に合わせて変える（tellHeight）ので、ここでは変えない
    child.show();
    child.focus();
    child.once('closed', () => { if (!window.isDestroyed()) window.focus(); });   // 閉じたら親を前に（ほかのアプリの後ろに回らない）
    guard(child, icon);   // 子の窓から開く孫の窓も同じ決まりで
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
}

async function open(request) {
  const {url, title, width, height, smoke} = request;
  if (!LOCAL.test(url)) return null;
  const root = await moduleOf(url);
  const icon = root ? moduleIconOf(root, request) : ICON;
  const window = new BrowserWindow({
    width, height, minWidth: Math.min(MIN_WIDTH, width), minHeight: Math.min(MIN_HEIGHT, height),
    title, show: !smoke, ...look(icon),
  });
  asModuleApp(window, root, request);   // タスクバーで、モジュールごとのアプリに（読み込む前に：最初のアイコンが残るため）
  guard(window, icon);
  if (smoke) {
    window.webContents.once('did-finish-load', () => {
      console.log(`loaded: ${window.webContents.getTitle()}`);
      if (root) console.log(`module: ${root} ${moduleAppId(root)} ${moduleIconOf(root, request)}`);   // タスクバーのモジュールのアプリ
      app.quit();
    });
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
  app.whenReady().then(async () => {
    Menu.setApplicationMenu(null);
    if (!(await open(request(process.argv)))) app.quit();   // 開く窓がない（URL がない・この PC の中継地点でない）
  });
}
