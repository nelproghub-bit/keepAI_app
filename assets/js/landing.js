if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js')
      .catch(error => console.warn('[KeepAI PWA] Service worker registration failed:', error));
  });
}
