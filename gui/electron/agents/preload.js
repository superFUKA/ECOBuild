'use strict';
// エージェントの窓（window.html）・右下の表示（dock.html）と main（agents/index.js・dock.js）のやり取り。
const {contextBridge, ipcRenderer} = require('electron');

const on = channel => fn => ipcRenderer.on(channel, (event, ...args) => fn(...args));

contextBridge.exposeInMainWorld('agents', {
  ready: () => ipcRenderer.send('agents:ready'),
  input: (id, data) => ipcRenderer.send('agents:input', id, data),
  resize: (id, cols, rows) => ipcRenderer.send('agents:resize', id, cols, rows),
  select: id => ipcRenderer.send('agents:select', id),
  focusTab: id => ipcRenderer.send('agents:focus-tab', id),
  closeTab: id => ipcRenderer.send('agents:close-tab', id),
  restart: (id, resume = false) => ipcRenderer.send('agents:restart', id, resume),
  rename: (id, name) => ipcRenderer.send('agents:rename', id, name),
  reorder: ids => ipcRenderer.send('agents:reorder', ids),
  newWindow: id => ipcRenderer.send('agents:new-window', id),
  topmost: () => ipcRenderer.send('agents:topmost'),
  minimize: () => ipcRenderer.send('agents:minimize'),
  closeWindow: () => ipcRenderer.send('agents:close-window'),
  picker: () => ipcRenderer.invoke('agents:picker'),
  setNotify: patch => ipcRenderer.send('agents:notify', patch),
  testSound: () => ipcRenderer.send('agents:test-sound'),
  voice: id => ipcRenderer.send('agents:voice', id),

  onAdopt: on('agents:adopt'),
  onRelease: on('agents:release'),
  onReset: on('agents:reset'),
  onData: on('agents:data'),
  onExit: on('agents:exit'),
  onSelect: on('agents:select'),
  onTabs: on('agents:tabs'),
  onTopmost: on('agents:topmost'),
  onNotify: on('agents:notify'),
});

contextBridge.exposeInMainWorld('dock', {
  ready: () => ipcRenderer.send('dock:ready'),
  size: (width, height) => ipcRenderer.send('dock:size', width, height),
  dragStart: () => ipcRenderer.send('dock:drag-start'),
  dragMove: (dx, dy) => ipcRenderer.send('dock:drag-move', dx, dy),
  dragEnd: () => ipcRenderer.send('dock:drag-end'),
  action: (name, arg) => ipcRenderer.send('dock:action', name, arg),
  onView: on('dock:view'),
  onSound: on('dock:sound'),
});
