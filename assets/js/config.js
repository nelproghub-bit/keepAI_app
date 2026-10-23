const IS_LOCAL_DEVELOPMENT = ['localhost', '127.0.0.1'].includes(window.location.hostname);
const API_BASE_URL = (
    window.VITE_API_URL
    || (IS_LOCAL_DEVELOPMENT ? 'http://localhost:8000' : window.location.origin)
).replace(/\/+$/, '');

window.API_BASE_URL = API_BASE_URL;
window.API_URL = API_BASE_URL;
window.API_BASE = `${API_BASE_URL}/api`;
window.API_IS_DEVELOPMENT = IS_LOCAL_DEVELOPMENT;
