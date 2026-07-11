/**
 * Citizen Desktop — Preload Script
 *
 * Exposes a minimal API to the renderer process via contextBridge.
 * Currently mostly a stub — the frontend communicates with the backend
 * over HTTP on localhost, so IPC is needed only for native features
 * (file dialogs, app menu actions, etc.).
 *
 * Version: 1.0.0 | 2026-07-10
 */

import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  // Platform info
  platform: process.platform,

  // App version
  getVersion: (): Promise<string> => ipcRenderer.invoke('get-version'),

  // File dialogs
  openFileDialog: async (options?: { filters?: { name: string; extensions: string[] }[] }): Promise<string[] | null> => {
    return ipcRenderer.invoke('open-file-dialog', options);
  },

  // App menu events
  onMenuAction: (callback: (action: string) => void): void => {
    ipcRenderer.on('menu-action', (_event, action: string) => callback(action));
  },

  // Backend port (for reference)
  backendPort: 8512,

  // Write settings to .env file (e.g., API key)
  setApiKey: (key: string): Promise<void> => ipcRenderer.invoke('set-api-key', key),
});
