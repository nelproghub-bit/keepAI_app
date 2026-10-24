document.addEventListener('DOMContentLoaded', () => {
    if (!window.APP_VERSION || window.APP_VERSION === 'local') return;

    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) return;

    const versionKey = 'keepai-app-version';
    let previousVersion;
    let updateWasRequested;
    try {
        previousVersion = localStorage.getItem(versionKey) || '9333d62';
        updateWasRequested = sessionStorage.getItem('keepai-update-reload') === '1';
        if (updateWasRequested) sessionStorage.removeItem('keepai-update-reload');
    } catch (error) {
        console.error('Could not check the KeepAI release version:', error);
        return;
    }

    const showUpdateNotice = () => {
        if (document.getElementById('keepai-release-notice')) return;

        const notice = document.createElement('div');
        notice.id = 'keepai-release-notice';
        notice.className = 'toast';
        notice.setAttribute('role', 'status');
        notice.style.cssText = 'display:flex;flex-wrap:wrap;gap:10px;max-width:380px;padding:14px 18px;background:#fff;border:1px solid #e2e8f0;border-left:4px solid #7d1d1d;border-radius:12px;box-shadow:0 8px 24px rgba(10,15,30,.2);color:#0f172a;font:600 13px Inter,sans-serif;';

        const message = document.createElement('span');
        message.textContent = 'KeepAI has been updated. Reload to use the latest version.';
        message.style.flex = '1 1 100%';

        const updateButton = document.createElement('button');
        updateButton.type = 'button';
        updateButton.textContent = 'Update now';
        updateButton.style.cssText = 'padding:8px 14px;border:0;border-radius:8px;background:#7d1d1d;color:#fff;font:600 13px Inter,sans-serif;cursor:pointer;';
        updateButton.addEventListener('click', async () => {
            updateButton.disabled = true;
            updateButton.textContent = 'Updating…';
            try {
                if ('serviceWorker' in navigator) {
                    const registration = await navigator.serviceWorker.getRegistration();
                    if (registration) await registration.update();
                }
                try {
                    sessionStorage.setItem('keepai-update-reload', '1');
                } catch (error) {
                    console.error('Could not save the KeepAI update confirmation:', error);
                }
                const latestUrl = new URL(window.location.href);
                latestUrl.searchParams.set('__keepai_refresh', String(Date.now()));
                window.location.replace(latestUrl.href);
            } catch (error) {
                console.error('Could not refresh KeepAI after an update:', error);
                updateButton.disabled = false;
                updateButton.textContent = 'Try again';
            }
        });

        notice.append(message, updateButton);
        toastContainer.appendChild(notice);
    };

    if (updateWasRequested) {
        localStorage.setItem(versionKey, window.APP_VERSION);
    } else if (previousVersion !== window.APP_VERSION) {
        showUpdateNotice();
    }

    if ('serviceWorker' in navigator) {
        const alreadyControlled = Boolean(navigator.serviceWorker.controller);
        navigator.serviceWorker.addEventListener('controllerchange', () => {
            if (alreadyControlled) showUpdateNotice();
        });
    }
});
