(() => {
  const maintenancePage = '/maintenance.html';
  document.documentElement.classList.add('keepai-maintenance-check');

  fetch(`${window.API_BASE}/maintenance-status`, { cache: 'no-store' })
    .then(response => {
      if (!response.ok) throw new Error(`Maintenance status check failed (${response.status}).`);
      return response.json();
    })
    .then(status => {
      if (status.maintenance && window.location.pathname !== maintenancePage) {
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
