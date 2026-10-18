'use strict';
// 右下の表示（Electron の main）：エージェントの窓を最小化したときの小さな表示と、返答のカード。1つの部品にまとめる。
// - 最小化中：「丸（タブの番号）＋タブ名」の小さな横長。丸の縁で状態（考え中・裏で実行中・選択肢・終了）、右上のバッジは
//   最小化中に返答が終わったタブの数。クリックでのぞき見（最後の出力・入力中の文字）、⤢ で元に戻す。
// - 返答のカード：最小化中の返答と、知らせ方が「ECOBuild のカード」のときの返答。決めた時間だけ出す（右クリックで消す）。
// - 置き場所は右下が起点（ドラッグで動かせる。覚える）。どの窓のフォーカスも奪わない。画面は dock.html・dock-view.js。
const {BrowserWindow, screen: display} = require('electron');
const path = require('path');

const MARGIN = 16;
let win = null, ready = false, view = null, anchor = null, saveAnchor = () => {}, handlers = {};
let size = {width: 240, height: 64};

function setup({initialAnchor, onAnchor, actions}) {
  anchor = initialAnchor || null; saveAnchor = onAnchor; handlers = actions;
}

function area() { return display.getPrimaryDisplay().workArea; }
function corner() {   // 表示の右下の位置
  const a = area();
  const x = anchor?.x ?? a.x + a.width - MARGIN, y = anchor?.y ?? a.y + a.height - MARGIN;
  return {x: Math.min(Math.max(x, a.x + 80), a.x + a.width), y: Math.min(Math.max(y, a.y + 64), a.y + a.height)};
}

function ensure() {
  if (win && !win.isDestroyed()) return win;
  ready = false;
  win = new BrowserWindow({
    width: size.width, height: size.height, frame: false, transparent: true, resizable: false, skipTaskbar: true,
    focusable: false, show: false, alwaysOnTop: true, hasShadow: false,
    webPreferences: {preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true},
  });
  win.setAlwaysOnTop(true, 'screen-saver');
  win.loadFile(path.join(__dirname, 'dock.html'));
  win.on('closed', () => { win = null; ready = false; });
  return win;
}

function place() {
  if (!win || win.isDestroyed()) return;
  const {x, y} = corner();
  win.setBounds({x: Math.round(x - size.width), y: Math.round(y - size.height), width: size.width, height: size.height});
}

// 出すもの：{chip, cards, peek}。chip も cards もなければ隠す
function update(next) {
  view = next;
  if (!(next.chip || next.cards.length)) { if (win && !win.isDestroyed()) win.hide(); return; }
  ensure();
  if (ready) win.webContents.send('dock:view', view);
  place();
  if (!win.isVisible()) win.showInactive();
}

function play(sound) {
  ensure();
  const send = () => win.webContents.send('dock:sound', sound);
  if (ready) send(); else win.webContents.once('did-finish-load', send);
}

const isDock = event => win && !win.isDestroyed() && event.sender === win.webContents;

function wire(ipcMain) {
  ipcMain.on('dock:ready', event => { if (!isDock(event)) return; ready = true; if (view) win.webContents.send('dock:view', view); });
  ipcMain.on('dock:size', (event, width, height) => {
    if (!isDock(event)) return;
    size = {width: Math.max(64, Math.min(440, Math.ceil(width))), height: Math.max(48, Math.min(600, Math.ceil(height)))};
    place();
  });
  let dragFrom = null;
  ipcMain.on('dock:drag-start', event => { if (isDock(event)) dragFrom = corner(); });
  ipcMain.on('dock:drag-move', (event, dx, dy) => {
    if (!isDock(event) || !dragFrom) return;
    anchor = {x: dragFrom.x + dx, y: dragFrom.y + dy}; place();
  });
  ipcMain.on('dock:drag-end', event => { if (isDock(event) && dragFrom) { dragFrom = null; saveAnchor(anchor); } });
  ipcMain.on('dock:action', (event, name, arg) => { if (isDock(event)) handlers[name]?.(arg); });
}

module.exports = {setup, update, play, wire};
