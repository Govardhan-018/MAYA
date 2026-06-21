// main/preload.js — Context Bridge for MAYA renderer
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('maya', {
  // Window controls
  minimize: () => ipcRenderer.send('window:minimize'),
  maximize: () => ipcRenderer.send('window:maximize'),
  close:    () => ipcRenderer.send('window:close'),
  quit:     () => ipcRenderer.send('app:quit'),

  // Persistent settings
  getStore: (key) => ipcRenderer.invoke('store:get', key),
  setStore: (key, value) => ipcRenderer.invoke('store:set', key, value),

  // System info
  systemInfo: () => ipcRenderer.invoke('system:info'),

  // Event listeners from main process
  onTrayToggleVoice: (cb) => ipcRenderer.on('tray:toggle-voice', (_event) => cb()),
});
