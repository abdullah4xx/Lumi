const { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, shell, Tray } = require('electron');
const { autoUpdater } = require('electron-updater');
const { spawn } = require('node:child_process');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');

let backend;
let window;
let serverUrl;
let tray;
let isQuitting = false;

function dataDirectories() {
  const home = os.homedir();
  const xdg = (name, fallback) => process.env[name] || path.join(home, fallback);
  return {
    config: path.join(xdg('XDG_CONFIG_HOME', '.config'), 'lumi'),
    data: path.join(xdg('XDG_DATA_HOME', '.local/share'), 'lumi'),
    cache: path.join(xdg('XDG_CACHE_HOME', '.cache'), 'lumi'),
    downloads: path.join(app.getPath('pictures'), 'Lumi'),
  };
}

function pythonPaths() {
  if (app.isPackaged) {
    return {
      source: path.join(process.resourcesPath, 'python'),
      ui: path.join(process.resourcesPath, 'ui'),
    };
  }
  const root = path.resolve(__dirname, '..');
  return { source: path.join(root, 'src'), ui: path.join(root, 'ui') };
}

function startBackend() {
  const paths = pythonPaths();
  const python = process.env.LUMI_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  const port = '0';
  return new Promise((resolve, reject) => {
    backend = spawn(python, ['-m', 'lumi', '--web-server', '--no-browser', '--port', port], {
      env: {
        ...process.env,
        PYTHONPATH: [paths.source, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
        LUMI_UI_DIR: paths.ui,
        PYTHONUNBUFFERED: '1',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let output = '';
    let settled = false;
    const timeout = setTimeout(() => {
      if (!settled) {
        settled = true;
        reject(new Error(`Timed out while starting the Lumi service.\n${output}`));
        backend.kill();
      }
    }, 30000);
    const fail = error => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      reject(error);
    };
    backend.stdout.setEncoding('utf8');
    backend.stderr.setEncoding('utf8');
    backend.stdout.on('data', chunk => {
      output += chunk;
      const match = output.match(/Lumi is running at (http:\/\/127\.0\.0\.1:\d+)/);
      if (match && !settled) {
        settled = true;
        clearTimeout(timeout);
        serverUrl = match[1];
        resolve(serverUrl);
      }
    });
    backend.stderr.on('data', chunk => {
      output += chunk;
      if (output.length > 12000) output = output.slice(-12000);
    });
    backend.once('error', fail);
    backend.once('exit', (code, signal) => {
      if (!settled) fail(new Error(`Lumi service exited before starting (code ${code}, signal ${signal}).\n${output}`));
      if (app.isReady() && window && !window.isDestroyed()) {
        dialog.showErrorBox('Lumi service stopped', `The wallpaper service exited (code ${code}).`);
      }
    });
  });
}

function isTrustedUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:';
  } catch {
    return false;
  }
}

function registerNativeActions() {
  ipcMain.handle('lumi:hide-window', () => {
    if (window && !window.isDestroyed()) {
      if (tray) window.hide();
      else window.close();
    }
  });
  ipcMain.handle('lumi:choose-folder', async () => {
    const result = await dialog.showOpenDialog(window, { properties: ['openDirectory'] });
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle('lumi:choose-images', async () => {
    const result = await dialog.showOpenDialog(window, {
      properties: ['openFile', 'multiSelections'],
      filters: [{ name: 'Images', extensions: ['jpg', 'jpeg', 'png', 'webp', 'bmp', 'tif', 'tiff', 'avif', 'jxl'] }],
    });
    return result.canceled ? [] : result.filePaths;
  });
  ipcMain.handle('lumi:open-folder', async (_event, key) => {
    const directory = dataDirectories()[key];
    if (!directory) throw new Error('Unsupported folder');
    await fs.mkdir(directory, { recursive: true });
    return shell.openPath(directory);
  });
  ipcMain.handle('lumi:export-backup', async (_event, backup) => {
    const result = await dialog.showSaveDialog(window, {
      defaultPath: path.join(app.getPath('documents'), 'lumi-backup.json'),
      filters: [{ name: 'Lumi backup', extensions: ['json'] }],
    });
    if (result.canceled || !result.filePath) return false;
    await fs.writeFile(result.filePath, JSON.stringify(backup, null, 2), { mode: 0o600 });
    return true;
  });
  ipcMain.handle('lumi:import-backup', async () => {
    const result = await dialog.showOpenDialog(window, {
      properties: ['openFile'],
      filters: [{ name: 'Lumi backup', extensions: ['json'] }],
    });
    if (result.canceled || !result.filePaths[0]) return null;
    return JSON.parse(await fs.readFile(result.filePaths[0], 'utf8'));
  });
  ipcMain.handle('lumi:open-external', async (_event, value) => {
    if (!isTrustedUrl(value)) throw new Error('Only HTTPS links can be opened');
    await shell.openExternal(value);
  });
  ipcMain.handle('lumi:check-for-updates', async () => {
    if (!app.isPackaged) return { supported: false, reason: 'Updates are available in packaged builds.' };
    if (process.platform !== 'linux' || !process.env.APPIMAGE) {
      return { supported: false, reason: 'Automatic updates are supported by the AppImage build. Download the latest release for other packages.' };
    }
    await autoUpdater.checkForUpdates();
    return { supported: true };
  });
  ipcMain.handle('lumi:download-update', async () => {
    if (!app.isPackaged || process.platform !== 'linux' || !process.env.APPIMAGE) {
      throw new Error('Automatic updates are supported by the AppImage build.');
    }
    await autoUpdater.downloadUpdate();
  });
  ipcMain.handle('lumi:install-update', () => {
    if (process.platform !== 'linux' || !process.env.APPIMAGE) {
      throw new Error('Automatic updates are supported by the AppImage build.');
    }
    autoUpdater.quitAndInstall();
  });
}

function configureUpdates() {
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = false;
  const notify = (status, details = {}) => {
    if (window && !window.isDestroyed()) {
      window.webContents.send('lumi:update-status', { status, ...details });
    }
  };
  autoUpdater.on('checking-for-update', () => notify('checking'));
  autoUpdater.on('update-available', info => notify('available', { version: info.version }));
  autoUpdater.on('update-not-available', info => notify('up-to-date', { version: info.version }));
  autoUpdater.on('download-progress', progress => notify('downloading', { percent: Math.round(progress.percent) }));
  autoUpdater.on('update-downloaded', info => notify('downloaded', { version: info.version }));
  autoUpdater.on('error', error => notify('error', { message: error.message }));
}

function showWindow() {
  if (!window || window.isDestroyed()) return;
  if (window.isMinimized()) window.restore();
  window.show();
  window.focus();
}

function openSettings() {
  showWindow();
  window?.webContents.send('lumi:open-settings');
}

async function changeWallpaper() {
  const response = await fetch(new URL('/api/shuffle', serverUrl), { method: 'POST' });
  const result = await response.json();
  if (!response.ok || !result.ok) {
    throw new Error(result.message || `Wallpaper change failed (${response.status})`);
  }
  tray?.setToolTip(`lumi — ${result.title || 'Wallpaper changed'}`);
}

function createTray() {
  const icon = nativeImage.createFromPath(
    path.join(pythonPaths().ui, 'img', 'icons8-settings-48.png'),
  ).resize({ width: 24, height: 24 });
  if (icon.isEmpty()) throw new Error('Could not create the lumi tray icon');

  tray = new Tray(icon);
  tray.setToolTip('lumi');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Open lumi', click: showWindow },
    {
      label: 'Change wallpaper',
      click: () => changeWallpaper().catch(error => {
        dialog.showErrorBox('Could not change wallpaper', error.message);
      }),
    },
    { type: 'separator' },
    { label: 'Settings', click: openSettings },
    { type: 'separator' },
    { label: 'Exit lumi', click: () => app.quit() },
  ]));
  tray.on('click', showWindow);
  tray.on('double-click', showWindow);
}

function createWindow() {
  window = new BrowserWindow({
    title: 'lumi',
    width: 1280,
    height: 820,
    minWidth: 720,
    minHeight: 540,
    backgroundColor: '#111318',
    frame: false,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  window.once('ready-to-show', () => {
    window.maximize();
    window.show();
  });
  window.on('close', event => {
    if (tray && !isQuitting) {
      event.preventDefault();
      window.hide();
    }
  });
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (isTrustedUrl(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  window.webContents.on('will-navigate', (event, url) => {
    if (!serverUrl || !url.startsWith(`${serverUrl}/`)) event.preventDefault();
  });
  window.loadURL(serverUrl);
  window.on('closed', () => { window = null; });
}

app.whenReady().then(async () => {
  registerNativeActions();
  configureUpdates();
  try {
    await startBackend();
    try {
      createTray();
    } catch (error) {
      console.warn(`System tray unavailable; closing Lumi will exit the app: ${error.message}`);
    }
    createWindow();
  } catch (error) {
    dialog.showErrorBox('Unable to start Lumi', `${error.message}\n\nInstall Python 3, aiohttp and Pillow, or set LUMI_PYTHON to the correct Python executable.`);
    app.quit();
  }
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0 && serverUrl) createWindow();
  });
});

app.on('before-quit', () => {
  isQuitting = true;
  if (backend && !backend.killed) backend.kill();
});

app.on('window-all-closed', () => {
  if (!tray && process.platform !== 'darwin') app.quit();
});
