const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('lumiDesktop', Object.freeze({
  chooseFolder: () => ipcRenderer.invoke('lumi:choose-folder'),
  chooseImages: () => ipcRenderer.invoke('lumi:choose-images'),
  hideWindow: () => ipcRenderer.invoke('lumi:hide-window'),
  onOpenSettings: callback => {
    if (typeof callback !== 'function') throw new TypeError('Expected a settings callback');
    const listener = () => callback();
    ipcRenderer.on('lumi:open-settings', listener);
    return () => ipcRenderer.removeListener('lumi:open-settings', listener);
  },
  openFolder: key => ipcRenderer.invoke('lumi:open-folder', key),
  exportBackup: backup => ipcRenderer.invoke('lumi:export-backup', backup),
  importBackup: () => ipcRenderer.invoke('lumi:import-backup'),
  openExternal: url => ipcRenderer.invoke('lumi:open-external', url),
  getAppVersion: () => ipcRenderer.invoke('lumi:app-version'),
  checkForUpdates: () => ipcRenderer.invoke('lumi:check-for-updates'),
  downloadUpdate: () => ipcRenderer.invoke('lumi:download-update'),
  installUpdate: () => ipcRenderer.invoke('lumi:install-update'),
  onUpdateStatus: callback => {
    if (typeof callback !== 'function') throw new TypeError('Expected an update callback');
    const listener = (_event, status) => callback(status);
    ipcRenderer.on('lumi:update-status', listener);
    return () => ipcRenderer.removeListener('lumi:update-status', listener);
  },
}));
