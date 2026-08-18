const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('demoApi', {
  accountStatus: (slot) => ipcRenderer.invoke('account:status', slot),
  openLogin: (slot) => ipcRenderer.invoke('account:open-login', slot),
  submitOriginal: (payload) => ipcRenderer.invoke('original:submit', payload),
  refreshTask: (task) => ipcRenderer.invoke('task:refresh', task),
  openSong: (url) => ipcRenderer.invoke('song:open', url),
});
