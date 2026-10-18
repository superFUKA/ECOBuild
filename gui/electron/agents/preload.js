'use strict';
// エージェントの窓（window.html）と main（agents/index.js）のやり取り。
const {contextBridge, ipcRenderer} = require('electron');

const on = channel => fn => ipcRenderer.on(channel, (event, ...args) => fn(...args));

contextBridge.exposeInMainWorld('agents', {
  ready: () => ipcRenderer.send('agents:ready'),
  input: (id, data) => ipcRenderer.send('agents:input', id, data),
  resize: (id, cols, rows) => ipcRenderer.send('agents:resize', id, cols, rows),
  select: id => ipcRenderer.send('agents:select', id),
  closeTab: id => ipcRenderer.send('agents:close-tab', id),
  restart: id => ipcRenderer.send('agents:restart', id),
  rename: (id, name) => ipcRenderer.send('agents:rename', id, name),
  reorder: ids => ipcRenderer.send('agents:reorder', ids),
  newWindow: id => ipcRenderer.send('agents:new-window', id),
  topmost: () => ipcRenderer.send('agents:topmost'),
  minimize: () => ipcRenderer.send('agents:minimize'),
  closeWindow: () => ipcRenderer.send('agents:close-window'),

  onAdopt: on('agents:adopt'),
  onRelease: on('agents:release'),
  onReset: on('agents:reset'),
  onData: on('agents:data'),
  onExit: on('agents:exit'),
  onSelect: on('agents:select'),
  onTabs: on('agents:tabs'),
  onTopmost: on('agents:topmost'),
});
