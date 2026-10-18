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
  focusWindow: () => ipcRenderer.invoke('focus-window'),   // bring this window up (restore when minimized, to the front)
  // エージェントをこのアプリの窓のタブで開く（agents/index.js。同じ作業空間のものがあれば前に出す）
  agents: {
    open: options => ipcRenderer.invoke('agents:open', options), list: () => ipcRenderer.invoke('agents:list'),
    // オペレーター（裏で動いている ECOBuild の操作係）との会話：watch で表示を始め（起動もする）、onUpdate で様子が届く
    operator: {
      watch: on => ipcRenderer.invoke('operator:watch', on),
      send: text => ipcRenderer.send('operator:send', text),
      key: name => ipcRenderer.send('operator:key', name),          // up・down・enter・esc（選択肢に答える）
      show: on => ipcRenderer.send('operator:show', on),            // タブで開く・裏に戻す
      restart: () => ipcRenderer.send('operator:restart'),
      clear: () => ipcRenderer.send('operator:clear'),
      onUpdate: fn => ipcRenderer.on('operator:update', (event, view) => fn(view)),
    },
  },
});
