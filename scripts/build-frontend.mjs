import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const outputDirectory = path.join(projectRoot, 'dist');
const isDeployment = process.env.VERCEL === '1' || process.env.NODE_ENV === 'production';

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
  'window.API_BASE_URL = API_BASE_URL;',
  'window.API_URL = API_BASE_URL;',
  'window.API_BASE = `${API_BASE_URL}/api`;',
  `window.API_IS_DEVELOPMENT = ${!isDeployment};`,
  '',
].join('\n');
await writeFile(path.join(outputDirectory, 'assets', 'js', 'config.js'), apiConfig);

console.log(`Frontend built to dist/ (${parsedApiUrl.origin}; ${isDeployment ? 'deployment' : 'development'} mode).`);
