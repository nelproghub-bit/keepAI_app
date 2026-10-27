const currentUrl = new URL(window.location.href);
if (currentUrl.searchParams.has('__keepai_refresh')) {
    currentUrl.searchParams.delete('__keepai_refresh');
    window.history.replaceState(
        window.history.state,
        '',
        `${currentUrl.pathname}${currentUrl.search}${currentUrl.hash}`
    );
}

document.addEventListener('DOMContentLoaded', () => {
    if (!window.APP_VERSION || window.APP_VERSION === 'local') return;

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

        const notice = document.createElement('dialog');
        notice.id = 'keepai-release-notice';
        notice.setAttribute('aria-labelledby', 'keepai-update-title');
        notice.setAttribute('aria-describedby', 'keepai-update-description');

        const badge = document.createElement('div');
        badge.className = 'keepai-update-badge';
        badge.textContent = 'KEEP AI · APP UPDATE';

        const heading = document.createElement('h2');
        heading.id = 'keepai-update-title';
        heading.textContent = 'App update ready';

        const message = document.createElement('p');
        message.id = 'keepai-update-description';
        message.textContent = 'KeepAI has been updated. Reload to use the latest version.';

        const actions = document.createElement('div');
        actions.className = 'keepai-update-actions';

        const laterButton = document.createElement('button');
        laterButton.type = 'button';
        laterButton.textContent = 'Not now';
        laterButton.addEventListener('click', () => notice.close());
        notice.addEventListener('close', () => notice.remove());

        const errorMessage = document.createElement('p');
        errorMessage.className = 'keepai-update-error';
        errorMessage.setAttribute('role', 'alert');
        errorMessage.hidden = true;

        const updateButton = document.createElement('button');
        updateButton.type = 'button';
        updateButton.textContent = 'Update now';
        updateButton.className = 'keepai-update-primary';
        updateButton.autofocus = true;
        updateButton.addEventListener('click', async () => {
            updateButton.disabled = true;
            updateButton.textContent = 'Updating…';
            errorMessage.hidden = true;
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
                errorMessage.textContent = 'The update could not be loaded. Check your connection and try again.';
                errorMessage.hidden = false;
            }
        });

        actions.append(laterButton, updateButton);
        notice.append(badge, heading, message, errorMessage, actions);
        document.body.appendChild(notice);
        notice.showModal();
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
