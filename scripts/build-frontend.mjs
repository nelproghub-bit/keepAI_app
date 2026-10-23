import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const outputDirectory = path.join(projectRoot, 'dist');
const isDeployment = process.env.VERCEL === '1' || process.env.NODE_ENV === 'production';
const appVersion = (process.env.VERCEL_GIT_COMMIT_SHA || process.env.GITHUB_SHA || 'local').slice(0, 12);

async function readLocalApiUrl() {
  for (const filename of ['.env.local', '.env']) {
    try {
      const contents = await readFile(path.join(projectRoot, filename), 'utf8');
      const match = contents.match(/^\s*VITE_API_URL\s*=\s*(.*?)\s*$/m);
      if (match) {
        return match[1].replace(/^(['"])(.*)\1$/, '$2');
      }
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }
  return '';
}

const configuredApiUrl = (process.env.VITE_API_URL || await readLocalApiUrl()).trim();
if (isDeployment && !configuredApiUrl) {
  throw new Error('Set VITE_API_URL to the deployed backend origin before building for deployment.');
}

const apiBaseUrl = (configuredApiUrl || 'http://localhost:8000').replace(/\/+$/, '');
let parsedApiUrl;
try {
  parsedApiUrl = new URL(apiBaseUrl);
} catch {
  throw new Error('VITE_API_URL must be an absolute HTTP or HTTPS backend origin.');
}
if (
  !['http:', 'https:'].includes(parsedApiUrl.protocol)
  || parsedApiUrl.pathname !== '/'
  || parsedApiUrl.search
  || parsedApiUrl.hash
) {
  throw new Error('VITE_API_URL must be the backend origin only, without a path, query, or fragment.');
}
if (isDeployment && parsedApiUrl.protocol !== 'https:') {
  throw new Error('VITE_API_URL must use HTTPS for deployment builds.');
}

await rm(outputDirectory, { recursive: true, force: true });
await mkdir(outputDirectory, { recursive: true });

for (const filename of [
  'index.html',
  'student_portal.html',
  'student_login.html',
  'student_dashboard.html',
  'admin_dashboard.html',
  'admin_panel.html',
  'manifest.json',
  'sw.js',
]) {
  await cp(path.join(projectRoot, filename), path.join(outputDirectory, filename));
}

for (const directory of ['assets', 'icons']) {
  await cp(path.join(projectRoot, directory), path.join(outputDirectory, directory), { recursive: true });
}

await mkdir(path.join(outputDirectory, 'assets', 'js'), { recursive: true });
const apiConfig = [
  `const API_BASE_URL = ${JSON.stringify(apiBaseUrl)};`,
  `window.APP_VERSION = ${JSON.stringify(appVersion)};`,
  'window.API_BASE_URL = API_BASE_URL;',
  'window.API_URL = API_BASE_URL;',
  'window.API_BASE = `${API_BASE_URL}/api`;',
  `window.API_IS_DEVELOPMENT = ${!isDeployment};`,
  `document.addEventListener('DOMContentLoaded', () => {`,
  `  if (!window.APP_VERSION || window.APP_VERSION === 'local') return;`,
  `  const toastContainer = document.getElementById('toast-container');`,
  `  if (!toastContainer) return;`,
  `  const versionKey = 'keepai-app-version';`,
  `  const previousVersion = localStorage.getItem(versionKey) || '9333d62';`,
  `  const updateWasRequested = sessionStorage.getItem('keepai-update-reload') === '1';`,
  `  if (updateWasRequested) sessionStorage.removeItem('keepai-update-reload');`,
  `  const showUpdateNotice = () => {`,
  `    if (document.getElementById('keepai-release-notice')) return;`,
  `    const notice = document.createElement('div');`,
  `    notice.id = 'keepai-release-notice';`,
  `    notice.className = 'toast';`,
  `    notice.setAttribute('role', 'status');`,
  `    notice.style.cssText = 'display:flex;flex-wrap:wrap;gap:10px;max-width:380px;padding:14px 18px;background:#fff;border:1px solid #e2e8f0;border-left:4px solid #7d1d1d;border-radius:12px;box-shadow:0 8px 24px rgba(10,15,30,.2);color:#0f172a;font:600 13px Inter,sans-serif;';`,
  `    const message = document.createElement('span');`,
  `    message.textContent = 'KeepAI has been updated. Reload to use the latest version.';`,
  `    message.style.flex = '1 1 100%';`,
  `    const updateButton = document.createElement('button');`,
  `    updateButton.type = 'button';`,
  `    updateButton.textContent = 'Update now';`,
  `    updateButton.style.cssText = 'padding:8px 14px;border:0;border-radius:8px;background:#7d1d1d;color:#fff;font:600 13px Inter,sans-serif;cursor:pointer;';`,
  `    updateButton.addEventListener('click', async () => {`,
  `      updateButton.disabled = true;`,
  `      updateButton.textContent = 'Updating…';`,
  `      try {`,
  `        if ('serviceWorker' in navigator) {`,
  `          const registration = await navigator.serviceWorker.getRegistration();`,
  `          if (registration) await registration.update();`,
  `        }`,
  `        sessionStorage.setItem('keepai-update-reload', '1');`,
  `        window.location.reload();`,
  `      } catch (error) {`,
  `        console.error('Could not refresh KeepAI after an update:', error);`,
  `        updateButton.disabled = false;`,
  `        updateButton.textContent = 'Try again';`,
  `      }`,
  `    });`,
  `    notice.append(message, updateButton);`,
  `    toastContainer.appendChild(notice);`,
  `  };`,
  `  if (updateWasRequested) localStorage.setItem(versionKey, window.APP_VERSION);`,
  `  else if (previousVersion !== window.APP_VERSION) {`,
  `    localStorage.setItem(versionKey, window.APP_VERSION);`,
  `    showUpdateNotice();`,
  `  }`,
  `  if ('serviceWorker' in navigator) {`,
  `    const alreadyControlled = Boolean(navigator.serviceWorker.controller);`,
  `    navigator.serviceWorker.addEventListener('controllerchange', () => {`,
  `      if (alreadyControlled) showUpdateNotice();`,
  `    });`,
  `  }`,
  `});`,
  '',
].join('\n');
await writeFile(path.join(outputDirectory, 'assets', 'js', 'config.js'), apiConfig);

const serviceWorkerPath = path.join(outputDirectory, 'sw.js');
const serviceWorker = await readFile(serviceWorkerPath, 'utf8');
if (!serviceWorker.includes('__APP_VERSION__')) {
  throw new Error('The service worker is missing its __APP_VERSION__ cache version placeholder.');
}
await writeFile(serviceWorkerPath, serviceWorker.replaceAll('__APP_VERSION__', appVersion));

console.log(`Frontend built to dist/ (${parsedApiUrl.origin}; ${isDeployment ? 'deployment' : 'development'} mode).`);
