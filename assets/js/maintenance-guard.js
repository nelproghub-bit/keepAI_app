(() => {
  const maintenancePage = '/maintenance.html';
  if (window.location.pathname === maintenancePage) return;

  document.documentElement.classList.add('keepai-maintenance-check');
  const apiBase = (typeof window.API_BASE === 'string' && window.API_BASE)
    ? window.API_BASE.replace(/\/$/, '')
    : '/api';

  fetch(`${apiBase}/maintenance-status`, { cache: 'no-store' })
    .then(response => {
      if (!response.ok) throw new Error(`Maintenance status check failed (${response.status}).`);
      return response.json();
    })
    .then(status => {
      if (status && status.maintenance) {
        const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
        window.location.replace(`${maintenancePage}?returnTo=${encodeURIComponent(returnTo)}`);
        return;
      }
      document.documentElement.classList.remove('keepai-maintenance-check');
    })
    .catch(error => {
      console.warn('Could not check KeepAI maintenance status:', error);
      document.documentElement.classList.remove('keepai-maintenance-check');
    });
})();
