(() => {
    const updateForm = (form, passwordEnabled, googleLinked) => {
        if (!form) return;

        form.dataset.passwordEnabled = String(passwordEnabled);
        form.dataset.googleLinked = String(googleLinked);

        const currentPasswordGroup = document.getElementById(form.dataset.currentPasswordGroup);
        const currentPassword = currentPasswordGroup?.querySelector('input[name="current_password"]');
        if (currentPasswordGroup) currentPasswordGroup.hidden = passwordEnabled;
        if (currentPassword) currentPassword.required = passwordEnabled;

        const description = document.getElementById(form.dataset.description);
        if (description) {
            description.textContent = passwordEnabled
                ? 'Change your password. Your current password is required to protect your account.'
                : 'Your Google account is linked. Set a password so you can also sign in with your email or username.';
        }

        const submit = form.querySelector('button[type="submit"]');
        if (submit) submit.textContent = passwordEnabled ? 'Update Password' : 'Set Account Password';
    };

    const submitForm = async form => {
        const status = document.getElementById(form.dataset.status);
        const submit = form.querySelector('button[type="submit"]');
        const currentPassword = form.querySelector('[name="current_password"]');
        const newPassword = form.querySelector('[name="new_password"]');
        const confirmPassword = form.querySelector('[name="confirm_password"]');
        status.textContent = '';
        status.style.color = 'var(--rose)';

        if (newPassword.value !== confirmPassword.value) {
            status.textContent = 'The new passwords do not match.';
            confirmPassword.focus();
            return;
        }

        const token = localStorage.getItem(form.dataset.tokenKey);
        if (!token) {
            status.textContent = 'Your session has expired. Sign in again and retry.';
            return;
        }

        submit.disabled = true;
        submit.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch(`${window.API_BASE}/auth/password`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    current_password: currentPassword?.value || null,
                    new_password: newPassword.value
                })
            });
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.detail || 'Could not update your password.');
            }

            updateForm(form, true, form.dataset.googleLinked === 'true');
            form.reset();
            status.style.color = 'var(--emerald)';
            status.textContent = 'Password saved. You can now sign in with your account email and password.';
        } catch (error) {
            status.textContent = error.message || 'Could not update your password. Please try again.';
        } finally {
            submit.disabled = false;
            submit.removeAttribute('aria-busy');
        }
    };

    document.addEventListener('submit', event => {
        const form = event.target.closest('form[data-account-password-form]');
        if (!form) return;
        event.preventDefault();
        void submitForm(form);
    });

    window.KeepAIAccountPasswordSettings = {
        update(formId, user) {
            updateForm(
                document.getElementById(formId),
                user?.password_login_enabled !== false,
                user?.google_linked === true
            );
        }
    };
})();
