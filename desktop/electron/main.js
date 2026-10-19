const { app, BrowserWindow, ipcMain, dialog, shell, Menu } = require('electron')
const path = require('path')
const fs = require('fs')
const net = require('net')
const http = require('http')
const crypto = require('crypto')
const { spawn, execFile } = require('child_process')
const { autoUpdater } = require('electron-updater')

const isDev = process.env.VISION_DEV === '1'
const token = crypto.randomBytes(32).toString('hex') // per-launch secret shared with the backend only
let backend = null
let backendPort = 0
let win = null
let quitting = false

if (!app.requestSingleInstanceLock()) {
  app.quit()
}
app.on('second-instance', () => {
  if (win) {
    if (win.isMinimized()) win.restore()
    win.focus()
  }
})

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer()
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address()
      srv.close(() => resolve(port))
    })
    srv.on('error', reject)
  })
}

function backendCommand(port) {
  const exe = path.join(process.resourcesPath || '', 'backend', process.platform === 'win32' ? 'vision-server.exe' : 'vision-server')
  if (app.isPackaged && fs.existsSync(exe)) {
    return { cmd: exe, args: ['--port', String(port)], cwd: path.dirname(exe) }
  }
  const root = path.resolve(__dirname, '..', '..') // development: run the uv project in the repo root
  return { cmd: process.platform === 'win32' ? 'uv.exe' : 'uv', args: ['run', '--project', root, 'vision-server', '--port', String(port)], cwd: root }
}

function healthy(port) {
  return new Promise((resolve) => {
    const req = http.get({ host: '127.0.0.1', port, path: '/api/health', timeout: 1000 }, (res) => {
      res.resume()
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.on('timeout', () => { req.destroy(); resolve(false) })
  })
}

// The installer ships uv (for uvx servers) and Node (for npx servers); put them on PATH for the engine.
function withBundledTools(env) {
  const dirs = ['uv', 'node']
    .map((d) => path.join(process.resourcesPath || '', 'tools', d))
    .filter((d) => fs.existsSync(d))
  if (!dirs.length) return env
  const key = Object.keys(env).find((k) => k.toLowerCase() === 'path') || 'PATH'
  return { ...env, [key]: [...dirs, env[key] || ''].join(path.delimiter) }
}

async function startBackend() {
  backendPort = await freePort()
  const { cmd, args, cwd } = backendCommand(backendPort)
  const logDir = path.join(app.getPath('userData'), 'logs')
  fs.mkdirSync(logDir, { recursive: true })
  const logPath = path.join(logDir, 'backend.log')
  const log = fs.openSync(logPath, 'a')
  let spawnError = null
  backend = spawn(cmd, args, {
    cwd,
    windowsHide: true,
    stdio: ['ignore', log, log],
    env: withBundledTools({
      ...process.env,
      VISION_TOKEN: token,
      VISION_DATA_DIR: path.join(app.getPath('userData'), 'data'),
      PYTHONUNBUFFERED: '1',
      PYTHONUTF8: '1',
    }),
  })
  backend.on('error', (e) => { spawnError = e })
  backend.on('exit', (code) => {
    backend = null
    if (!quitting) {
      dialog.showErrorBox('Vision', `The assistant engine stopped unexpectedly (code ${code}).\nLog: ${logPath}`)
      app.quit()
    }
  })
  for (let i = 0; i < 240; i++) { // up to ~60s: the first start may be slow
    if (spawnError) break
    if (await healthy(backendPort)) return
    await new Promise((r) => setTimeout(r, 250))
  }
  const hint = spawnError
    ? `Could not start "${cmd}": ${spawnError.message}\nIn development, install uv: https://docs.astral.sh/uv/`
    : 'The engine did not become ready in time.'
  throw new Error(`${hint}\nLog: ${logPath}`)
}

function stopBackend() {
  if (!backend) return
  const pid = backend.pid
  backend.removeAllListeners('exit')
  if (process.platform === 'win32') {
    execFile('taskkill', ['/pid', String(pid), '/T', '/F'], () => {}) // also kills child MCP processes
  } else {
    try { process.kill(pid, 'SIGTERM') } catch (_) {}
  }
  backend = null
}

function createWindow() {
  win = new BrowserWindow({
    width: 1180,
    height: 780,
    minWidth: 820,
    minHeight: 560,
    backgroundColor: '#101417',
    title: 'Vision',
    icon: path.join(__dirname, '..', 'build', process.platform === 'win32' ? 'icon.ico' : 'icon.png'),
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  Menu.setApplicationMenu(null)
  const isInternal = (url) => url.startsWith('file://') || url.startsWith('http://localhost:5173')
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) shell.openExternal(url)
    return { action: 'deny' }
  })
  win.webContents.on('will-navigate', (e, url) => { if (!isInternal(url)) e.preventDefault() })
  if (isDev) win.loadURL('http://localhost:5173')
  else win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  win.on('closed', () => { win = null })
}

ipcMain.handle('backend:info', () => ({ baseUrl: `http://127.0.0.1:${backendPort}`, token }))
ipcMain.handle('dialog:folder', async () => {
  const r = await dialog.showOpenDialog(win, { properties: ['openDirectory', 'createDirectory'] })
  return r.canceled ? null : r.filePaths[0]
})
ipcMain.handle('dialog:file', async () => {
  const r = await dialog.showOpenDialog(win, { properties: ['openFile'] })
  return r.canceled ? null : r.filePaths[0]
})
ipcMain.handle('shell:open', (_e, url) => {
  if (typeof url === 'string' && /^https?:\/\//.test(url)) return shell.openExternal(url)
})

// ---- automatic updates (GitHub Releases) ---------------------------------------
let lastUpdate = null
function sendUpdate(patch) {
  lastUpdate = { ...(lastUpdate || {}), ...patch }
  if (win && !win.isDestroyed()) win.webContents.send('update:status', lastUpdate)
}
function updaterLog(msg) {
  try { fs.appendFileSync(path.join(app.getPath('userData'), 'logs', 'updater.log'), `${new Date().toISOString()} ${msg}\n`) } catch (_) {}
}
function setupUpdates() {
  if (!app.isPackaged) return // development builds never update themselves
  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true
  autoUpdater.on('update-available', (i) => { updaterLog('available ' + i.version); sendUpdate({ state: 'downloading', version: i.version, percent: 0 }) })
  autoUpdater.on('download-progress', (p) => sendUpdate({ state: 'downloading', percent: Math.round(p.percent) }))
  autoUpdater.on('update-downloaded', (i) => { updaterLog('downloaded ' + i.version); sendUpdate({ state: 'ready', version: i.version }) })
  autoUpdater.on('error', (e) => updaterLog('error ' + (e && e.message)))
  const check = () => autoUpdater.checkForUpdates().catch((e) => updaterLog('check failed ' + (e && e.message)))
  setTimeout(check, 10000)
  setInterval(check, 6 * 60 * 60 * 1000)
}
ipcMain.handle('update:get', () => lastUpdate)
ipcMain.handle('update:install', () => autoUpdater.quitAndInstall())

app.whenReady().then(async () => {
  try {
    await startBackend()
    createWindow()
    setupUpdates()
  } catch (e) {
    dialog.showErrorBox('Vision', String(e.message || e))
    quitting = true
    stopBackend()
    app.quit()
  }
})
app.on('before-quit', () => { quitting = true; stopBackend() })
app.on('window-all-closed', () => app.quit())
