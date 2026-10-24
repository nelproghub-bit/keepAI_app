(() => {
  function decodeApplicationServerKey(encodedKey) {
    const padding = '='.repeat((4 - (encodedKey.length % 4)) % 4);
    const base64 = (encodedKey + padding).replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(base64);
    return Uint8Array.from(raw, character => character.charCodeAt(0));
  }

  async function pushRequest(path, token, options = {}) {
    const response = await fetch(`${window.API_BASE}${path}`, {
      ...options,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {})
      }
    });
    let data;
    try {
      data = await response.json();
    } catch (error) {
      throw new Error(`Push notification request returned an invalid response (${response.status}).`);
    }
    if (!response.ok) {
      throw new Error(data.detail || `Push notification request failed (${response.status}).`);
    }
    return data;
  }

  const pushInitializations = new WeakMap();

  async function initializePushControls() {
    const button = document.getElementById('push-notifications-toggle');
    const status = document.getElementById('push-notifications-status');
    if (!button || !status) return;

    const existingInitialization = pushInitializations.get(button);
    if (existingInitialization) return existingInitialization;
    const initialization = loadPushControls(button, status);
    pushInitializations.set(button, initialization);
    try {
      await initialization;
    } finally {
      pushInitializations.delete(button);
    }
  }

  async function loadPushControls(button, status) {
    const updateStatus = (message, state = 'info') => {
      status.textContent = message;
      status.dataset.state = state;
    };
    const tokenKey = button.dataset.tokenKey;
    const token = localStorage.getItem(tokenKey);
    if (!token) {
      button.disabled = true;
      updateStatus('Sign in to manage push notifications for this device.');
      return;
    }
    if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
      button.disabled = true;
      updateStatus('This browser does not support web push notifications.', 'error');
      return;
    }

    let registration;
    let subscription;
    let configuration = { enabled: false, public_key: null };
    let configurationError = null;
    try {
      registration = await navigator.serviceWorker.ready;
      subscription = await registration.pushManager.getSubscription();
    } catch (error) {
      console.error('Could not initialize push notifications:', error);
      button.disabled = true;
      updateStatus(error.message || 'Push notification settings could not be loaded.', 'error');
      return;
    }
    try {
      const response = await fetch(`${window.API_BASE}/push/public-key`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || `Push settings could not be loaded (${response.status}).`);
      }
      configuration = data;
    } catch (error) {
      console.error('Could not load push notification configuration:', error);
      configurationError = error;
    }

    if (button.dataset.pushHandlerReady !== 'true') {
      button.addEventListener('click', async () => {
        button.disabled = true;
        try {
          const activeToken = localStorage.getItem(tokenKey);
          if (!activeToken) throw new Error('Sign in again to manage push notifications.');
          const currentSubscription = await registration.pushManager.getSubscription();
          if (currentSubscription) {
            const unsubscribed = await currentSubscription.unsubscribe();
            if (!unsubscribed) {
              throw new Error('The browser could not disable this device subscription.');
            }
            button.textContent = 'Enable push notifications';
            button.setAttribute('aria-pressed', 'false');
            button.classList.remove('is-enabled');
            updateStatus('Push notifications are disabled on this device.');
            try {
              await pushRequest('/push/subscription', activeToken, {
                method: 'DELETE',
                body: JSON.stringify(currentSubscription.toJSON())
              });
            } catch (error) {
              console.error('Could not remove the disabled device subscription from the server:', error);
              updateStatus(`Disabled on this device. Server cleanup is pending: ${error.message}`, 'error');
            }
            return;
          }

          if (!configuration.enabled || !configuration.public_key) {
            throw new Error('Push notifications are not configured on this server yet.');
          }

          const permission = Notification.permission === 'default'
            ? await Notification.requestPermission()
            : Notification.permission;
          if (permission !== 'granted') {
            updateStatus(permission === 'denied'
              ? 'Notifications are blocked. Allow them in your browser or device settings.'
              : 'Notification permission was not granted.', 'error');
            return;
          }

          const pushSubscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: decodeApplicationServerKey(configuration.public_key)
          });
          try {
            await pushRequest('/push/subscription', activeToken, {
              method: 'POST',
              body: JSON.stringify(pushSubscription.toJSON())
            });
          } catch (error) {
            await pushSubscription.unsubscribe();
            throw error;
          }

          button.textContent = 'Disable on this device';
          button.setAttribute('aria-pressed', 'true');
          button.classList.add('is-enabled');
          updateStatus('Push notifications are enabled on this device.', 'enabled');
        } catch (error) {
          console.error('Could not update push notification settings:', error);
          updateStatus(error.message || 'Push notification settings could not be updated.', 'error');
        } finally {
          button.disabled = false;
        }
      });
      button.dataset.pushHandlerReady = 'true';
    }

    if (subscription) {
      button.disabled = false;
      button.textContent = 'Disable on this device';
      button.setAttribute('aria-pressed', 'true');
      button.classList.add('is-enabled');
      updateStatus('Push notifications are enabled on this device.', 'enabled');
      if (configuration.enabled) {
        try {
          await pushRequest('/push/subscription', token, {
            method: 'POST',
            body: JSON.stringify(subscription.toJSON())
          });
        } catch (error) {
          console.error('Could not synchronize this device push subscription:', error);
          updateStatus(`This device subscription could not be synchronized: ${error.message}`, 'error');
        }
      }
      return;
    }

    button.textContent = 'Enable push notifications';
    button.setAttribute('aria-pressed', 'false');
    button.classList.remove('is-enabled');
    button.disabled = !configuration.enabled;
    if (!configuration.enabled) {
      updateStatus(configurationError
        ? `Push settings could not be loaded: ${configurationError.message}`
        : 'Push notifications are not configured on this server yet.', 'error');
    } else if (Notification.permission === 'denied') {
      updateStatus('Notifications are blocked. Allow them in your browser or device settings.', 'error');
    } else {
      updateStatus('Ready to receive KeepAI announcements on this device.');
    }
  }

  window.KeepAIPushNotifications = { refresh: initializePushControls };
  document.addEventListener('DOMContentLoaded', initializePushControls);
})();
