(() => {
  const eyeIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>';
  const eyeOffIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m3 3 18 18"/><path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"/><path d="M9.9 5.2A10.8 10.8 0 0 1 12 5c6.4 0 10 7 10 7a15.8 15.8 0 0 1-3.1 3.9"/><path d="M6.2 6.2C3.5 8 2 12 2 12s3.6 7 10 7a10.8 10.8 0 0 0 3.1-.5"/></svg>';

  function updateToggle(button, input) {
    const isVisible = input.type === 'text';
    button.innerHTML = isVisible ? eyeOffIcon : eyeIcon;
    button.setAttribute('aria-label', isVisible ? 'Hide password' : 'Show password');
    button.setAttribute('aria-pressed', String(isVisible));
    button.title = isVisible ? 'Hide password' : 'Show password';
  }

  function addPasswordToggle(input) {
    if (input.closest('.password-input-wrap')) return;

    const wrapper = document.createElement('span');
    wrapper.className = 'password-input-wrap';
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'password-visibility-toggle';
    button.setAttribute('aria-pressed', 'false');
    button.innerHTML = eyeIcon;
    button.setAttribute('aria-label', 'Show password');
    button.title = 'Show password';
    button.addEventListener('click', () => {
      const wasFocused = document.activeElement === input;
      input.type = input.type === 'password' ? 'text' : 'password';
      updateToggle(button, input);
      if (wasFocused) input.focus({ preventScroll: true });
    });
    wrapper.appendChild(button);

    const form = input.form;
    if (form) {
      form.addEventListener('reset', () => {
        input.type = 'password';
        updateToggle(button, input);
      });
    }
  }

  function initializePasswordToggles() {
    document.querySelectorAll('input[type="password"]').forEach(addPasswordToggle);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializePasswordToggles, { once: true });
  } else {
    initializePasswordToggles();
  }
})();
