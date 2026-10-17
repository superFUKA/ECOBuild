'use strict';
// 画面に「Electron の窓の中にいる」ことを伝える（画面からは window.open で別の窓を開ける）。
// フォルダを選ぶ窓はこの窓に付けて出す（サーバーが別のプロセスで出すと、窓の裏に隠れる）。
// ファイル・フォルダを開くのも同じ（裏で動くサーバーが開いたエクスプローラーは、前に出ずに隠れる）。
const {contextBridge, ipcRenderer} = require('electron');

contextBridge.exposeInMainWorld('ecobuildShell', {
  electron: true,
  frameless: process.platform !== 'darwin',   // the page draws the window's top bar (main.js: titleBarStyle hidden)
  pickFolder: options => ipcRenderer.invoke('pick-folder', options),
  openPath: options => ipcRenderer.invoke('open-path', options),
});
