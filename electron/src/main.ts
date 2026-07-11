/**
 * Citizen Desktop — Electron Main Process
 *
 * Spawns the Python backend (PyInstaller binary or dev CLI), waits for
 * /health, then creates the BrowserWindow. Manages lifecycle with crash
 * detection and automatic restart backoff.
 *
 * Version: 1.0.0 | 2026-07-10
 */

import { app, BrowserWindow, dialog, ipcMain, Menu } from 'electron';
import { spawn, ChildProcess } from 'child_process';
import path from 'path';
import fs from 'fs';
import http from 'http';

// ---------------------------------------------------------------------------
// App Menu
// ---------------------------------------------------------------------------

function buildAppMenu(): void {
  const isMac = process.platform === 'darwin';

  const template: Electron.MenuItemConstructorOptions[] = [
    ...(isMac ? [{
      label: app.name,
      submenu: [
        { role: 'about' as const },
        { type: 'separator' as const },
        { role: 'quit' as const },
      ],
    }] : []),
    {
      label: 'File',
      submenu: [
        {
          label: 'Open Document...',
          accelerator: 'CmdOrCtrl+O',
          click: async () => {
            if (!mainWindow) return;
            const result = await dialog.showOpenDialog(mainWindow, {
              title: 'Open Legal Document',
              filters: [
                { name: 'Documents', extensions: ['pdf', 'txt', 'html', 'eml', 'jpg', 'png'] },
                { name: 'All Files', extensions: ['*'] },
              ],
              properties: ['openFile'],
            });
            if (!result.canceled && result.filePaths.length > 0) {
              mainWindow.webContents.send('menu-action', 'open-file:' + result.filePaths[0]);
            }
          },
        },
        { type: 'separator' },
        ...(isMac
          ? [{ role: 'close' as const }]
          : [{ role: 'quit' as const }]),
      ],
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'About Citizen',
          click: () => {
            dialog.showMessageBox(mainWindow!, {
              type: 'info',
              title: 'About Citizen',
              message: 'Citizen Desktop',
              detail: `Version ${app.getVersion()}\nLocal-first legal reasoning for German law.\n\nUses OpenRouter for LLM inference.`,
            });
          },
        },
      ],
    },
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const PORT = 8512;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const BACKEND_STARTUP_TIMEOUT_MS = 30_000;
const HEALTH_CHECK_INTERVAL_MS = 200;
const GRACEFUL_SHUTDOWN_MS = 5_000;
const CRASH_DEBOUNCE_MS = 3_000;
const MAX_RESTART_BACKOFF_MS = 30_000;

let pythonProcess: ChildProcess | null = null;
let mainWindow: BrowserWindow | null = null;
let crashCount = 0;
let lastCrashTime = 0;

// ---------------------------------------------------------------------------
// Backend Lifecycle
// ---------------------------------------------------------------------------

function getDataDir(): string {
  const dataDir = path.join(app.getPath('userData'), 'data');
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }
  return dataDir;
}

function getBackendCommand(): [string, string[]] {
  const isDev = !app.isPackaged;

  if (isDev) {
    // Development: run Python directly via uv
    return [
      'uv',
      [
        'run',
        'python',
        '-m',
        'app.main',
        '--port',
        String(PORT),
        '--data-dir',
        getDataDir(),
      ],
    ];
  }

  // Production: PyInstaller binary from extraResources
  const binaryPath = path.join(process.resourcesPath, 'backend', 'citizen-backend');
  return [binaryPath, ['--port', String(PORT), '--data-dir', getDataDir()]];
}

async function startBackend(): Promise<void> {
  const [command, args] = getBackendCommand();

  console.log(
    `[${new Date().toISOString()}] Starting backend: ${command} ${args.join(' ')}`
  );

  pythonProcess = spawn(command, args, {
    cwd: app.isPackaged
      ? process.resourcesPath
      : path.join(__dirname, '..', '..'),
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      // Ensure the backend knows to use SQLite for desktop
      DATABASE_URL: `sqlite+aiosqlite:///${path.join(getDataDir(), 'citizen.db')}`,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  pythonProcess.stdout?.on('data', (data: Buffer) => {
    console.log(`[backend:out] ${data.toString().trim()}`);
  });

  pythonProcess.stderr?.on('data', (data: Buffer) => {
    console.error(`[backend:err] ${data.toString().trim()}`);
  });

  pythonProcess.on('exit', (code: number | null, signal: string | null) => {
    console.error(
      `[${new Date().toISOString()}] Backend exited: code=${code} signal=${signal}`
    );
    handleBackendCrash();
  });

  await waitForServer(BASE_URL, BACKEND_STARTUP_TIMEOUT_MS);
  console.log(`[${new Date().toISOString()}] Backend healthy at ${BASE_URL}`);
}

async function waitForServer(url: string, timeoutMs: number): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const ok = await healthCheck(url);
      if (ok) return;
    } catch {
      // Server not ready yet — retry
    }
    await sleep(HEALTH_CHECK_INTERVAL_MS);
  }
  throw new Error(`Backend failed to start within ${timeoutMs}ms`);
}

function healthCheck(url: string): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(`${url}/health`, (res) => {
      resolve(res.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(2_000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function stopBackend(): Promise<void> {
  if (!pythonProcess || pythonProcess.killed) return;

  console.log(`[${new Date().toISOString()}] Stopping backend...`);
  pythonProcess.kill('SIGTERM');

  await new Promise<void>((resolve) => {
    const forceKill = setTimeout(() => {
      if (pythonProcess && !pythonProcess.killed) {
        console.warn(
          `[${new Date().toISOString()}] Backend did not exit gracefully, sending SIGKILL`
        );
        pythonProcess.kill('SIGKILL');
      }
      resolve();
    }, GRACEFUL_SHUTDOWN_MS);

    pythonProcess!.on('exit', () => {
      clearTimeout(forceKill);
      resolve();
    });
  });

  pythonProcess = null;
}

async function handleBackendCrash(): Promise<void> {
  const now = Date.now();
  if (now - lastCrashTime < CRASH_DEBOUNCE_MS) return;

  crashCount++;
  lastCrashTime = now;

  const backoff = Math.min(1_000 * Math.pow(2, crashCount), MAX_RESTART_BACKOFF_MS);
  console.error(
    `[${new Date().toISOString()}] Backend crashed (x${crashCount}), restarting in ${backoff}ms`
  );

  await sleep(backoff);
  try {
    await startBackend();
    crashCount = 0; // Reset on successful restart
  } catch (err) {
    console.error(
      `[${new Date().toISOString()}] Backend restart failed:`,
      err
    );
    if (mainWindow) {
      dialog.showErrorBox(
        'Backend Error',
        'The analysis engine could not start. Please restart the application.'
      );
    }
  }
}

// ---------------------------------------------------------------------------
// Window Management
// ---------------------------------------------------------------------------

async function createWindow(): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    title: 'Citizen',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadURL(BASE_URL);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ---------------------------------------------------------------------------
// IPC Handlers
// ---------------------------------------------------------------------------

// IPC handler: save API key to .env file
ipcMain.handle('set-api-key', async (_event, apiKey: string) => {
  const envPath = path.join(getDataDir(), '.env');
  const existingEnv = fs.existsSync(envPath)
    ? fs.readFileSync(envPath, 'utf-8').split('\n').filter(line => !line.startsWith('OPENROUTER_API_KEY='))
    : [];
  existingEnv.push(`OPENROUTER_API_KEY=${apiKey}`);
  fs.writeFileSync(envPath, existingEnv.join('\n'), 'utf-8');
  // Set in current process env for the backend subprocess
  process.env.OPENROUTER_API_KEY = apiKey;
});

ipcMain.handle('get-version', () => app.getVersion());

ipcMain.handle('open-file-dialog', async () => {
  if (!mainWindow) return null;
  const result = await dialog.showOpenDialog(mainWindow, {
    title: 'Open Legal Document',
    filters: [
      { name: 'Documents', extensions: ['pdf', 'txt', 'html', 'eml', 'jpg', 'png'] },
      { name: 'All Files', extensions: ['*'] },
    ],
    properties: ['openFile'],
  });
  if (result.canceled) return null;
  return result.filePaths;
});

// ---------------------------------------------------------------------------
// First-Run API Key Check
// ---------------------------------------------------------------------------

async function ensureApiKey(): Promise<boolean> {
  // Check if OPENROUTER_API_KEY is set in the environment
  if (process.env.OPENROUTER_API_KEY) return true;

  // Check .env file in data directory
  const envPath = path.join(getDataDir(), '.env');
  if (fs.existsSync(envPath)) {
    try {
      const envContent = fs.readFileSync(envPath, 'utf-8');
      if (envContent.includes('OPENROUTER_API_KEY=')) return true;
    } catch {
      // File read failed — will prompt user
    }
  }

  // No API key found — prompt user
  const { response } = await dialog.showMessageBox({
    type: 'question',
    title: 'OpenRouter API Key Required',
    message: 'Citizen needs an OpenRouter API key to function.',
    detail: 'You can get a free key at https://openrouter.ai/keys.\n\nPlease enter your API key below.',
    buttons: ['OK', 'Quit'],
    defaultId: 0,
  });

  if (response === 1) return false;  // User chose Quit

  return true;  // For now, continue — user will see the disclaimer which mentions API key
}

// ---------------------------------------------------------------------------
// App Lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(async () => {
  buildAppMenu();
  const hasKey = await ensureApiKey();
  if (!hasKey) {
    app.quit();
    return;
  }
  try {
    await startBackend();
    await createWindow();
  } catch (err) {
    console.error('Failed to start:', err);
    dialog.showErrorBox(
      'Startup Error',
      'Citizen could not start. Please check the logs and try again.'
    );
    app.quit();
  }
});

app.on('window-all-closed', async () => {
  await stopBackend();
  app.quit();
});

app.on('before-quit', async () => {
  await stopBackend();
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
