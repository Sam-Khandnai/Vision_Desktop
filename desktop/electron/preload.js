const { contextBridge, ipcRenderer } = require('electron')

// The renderer gets only these narrow capabilities - no Node, no arbitrary IPC.
contextBridge.exposeInMainWorld('vision', {
  getBackend: () => ipcRenderer.invoke('backend:info'),
  pickFolder: () => ipcRenderer.invoke('dialog:folder'),
  pickFile: () => ipcRenderer.invoke('dialog:file'),
  openExternal: (url) => ipcRenderer.invoke('shell:open', url),
})
