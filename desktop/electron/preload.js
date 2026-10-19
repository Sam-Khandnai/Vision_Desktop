const { contextBridge, ipcRenderer } = require('electron')

// The renderer gets only these narrow capabilities - no Node, no arbitrary IPC.
contextBridge.exposeInMainWorld('vision', {
  getBackend: () => ipcRenderer.invoke('backend:info'),
  pickFolder: () => ipcRenderer.invoke('dialog:folder'),
  pickFile: () => ipcRenderer.invoke('dialog:file'),
  openExternal: (url) => ipcRenderer.invoke('shell:open', url),
  getUpdate: () => ipcRenderer.invoke('update:get'),
  installUpdate: () => ipcRenderer.invoke('update:install'),
  onUpdate: (cb) => {
    const handler = (_e, status) => cb(status)
    ipcRenderer.on('update:status', handler)
    return () => ipcRenderer.removeListener('update:status', handler)
  },
})
