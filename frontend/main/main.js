// main/main.js — MAYA Electron Main Process
const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage } = require('electron');
const path = require('path');
const Store = require('electron-store');

const store = new Store({
  defaults: {
    backendUrl: 'http://localhost:8000',
    ollamaModel: 'qwen2.5:7b',
    voiceEnabled: true,
    startOnBoot: false,
    accentColor: '#22d3ee',
    chatFontSize: 10,
    sessionId: null
  }
});

let mainWindow = null;
let tray = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 720,
    minWidth: 900,
    minHeight: 560,
    frame: false,
    backgroundColor: '#02060f',
    transparent: false,
    show: false,
    icon: path.join(__dirname, '..', 'assets', 'icon.png'),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'));

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // Dev mode: open DevTools
  if (process.env.NODE_ENV === 'development') {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }

  // Prevent default close — hide to tray instead
  mainWindow.on('close', (e) => {
    if (!app.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });
}

function createTray() {
  const iconPath = path.join(__dirname, '..', 'assets', 'icon.png');
  const icon = nativeImage.createFromPath(iconPath).resize({ width: 16, height: 16 });
  tray = new Tray(icon);

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Open MAYA',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      }
    },
    {
      label: 'Toggle Voice',
      click: () => {
        if (mainWindow) {
          mainWindow.webContents.send('tray:toggle-voice');
        }
      }
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        app.isQuitting = true;
        app.quit();
      }
    }
  ]);

  tray.setToolTip('MAYA AI Assistant');
  tray.setContextMenu(contextMenu);

  tray.on('click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        mainWindow.show();
        mainWindow.focus();
      }
    }
  });
}

// ─── IPC Handlers ───────────────────────────────────────────────

// Window controls
ipcMain.on('window:minimize', () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.on('window:maximize', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  }
});

ipcMain.on('window:close', () => {
  if (mainWindow) mainWindow.hide();
});

ipcMain.on('app:quit', () => {
  app.isQuitting = true;
  app.quit();
});

// Persistent settings store
ipcMain.handle('store:get', (event, key) => {
  return store.get(key);
});

ipcMain.handle('store:set', (event, key, value) => {
  store.set(key, value);
  // Handle start on boot setting
  if (key === 'startOnBoot') {
    app.setLoginItemSettings({
      openAtLogin: value,
      path: app.getPath('exe')
    });
  }
});

// System info
ipcMain.handle('system:info', () => {
  return {
    platform: process.platform,
    arch: process.arch,
    nodeVersion: process.version
  };
});

// ─── App Lifecycle ──────────────────────────────────────────────

app.whenReady().then(() => {
  createWindow();
  createTray();

  // Apply start on boot setting
  const startOnBoot = store.get('startOnBoot');
  if (startOnBoot) {
    app.setLoginItemSettings({
      openAtLogin: true,
      path: app.getPath('exe')
    });
  }
});

app.on('window-all-closed', () => {
  // Don't quit on window close — we hide to tray
  if (process.platform !== 'darwin') {
    // Keep running in tray
  }
});

app.on('activate', () => {
  if (mainWindow) {
    mainWindow.show();
  }
});

app.on('before-quit', () => {
  app.isQuitting = true;
});
