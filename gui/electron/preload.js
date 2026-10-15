'use strict';
// 画面に「Electron の窓の中にいる」ことだけを伝える（画面からは window.open で別の窓を開ける）。
const {contextBridge} = require('electron');

contextBridge.exposeInMainWorld('ecobuildShell', {electron: true});
