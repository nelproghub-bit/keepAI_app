const API_URL = (window.VITE_API_URL || window.location.origin).replace(/\/+$/, '');

window.API_URL = API_URL;
window.API_BASE = `${API_URL}/api`;
