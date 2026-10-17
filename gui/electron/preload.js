'use strict';
// 画面に「Electron の窓の中にいる」ことを伝える（画面からは window.open で別の窓を開ける）。
// フォルダを選ぶ窓はこの窓に付けて出す（サーバーが別のプロセスで出すと、窓の裏に隠れる）。
const {contextBridge, ipcRenderer} = require('electron');

contextBridge.exposeInMainWorld('ecobuildShell', {
  electron: true,
  pickFolder: options => ipcRenderer.invoke('pick-folder', options),
});
