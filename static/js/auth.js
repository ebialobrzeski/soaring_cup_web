/**
 * AuthManager — handles login, registration, logout and auth-aware UI.
 *
 * Usage: instantiated in app.js as window.authManager
 */
class AuthManager {
    constructor() {
        this.currentUser = null;
        this.limits = null;
        this._init();
    }

    get isAuthenticated() {
        return this.currentUser !== null;
    }

    isPremium() {
        return this.currentUser && ['premium', 'admin'].includes(this.currentUser.tier);
    }

    canSetPrivate() {
        return this.limits && this.limits.can_set_private === true;
    }

    // ── bootstrap ────────────────────────────────────────────────────────────

    async _init() {
        this._bindDialogButtons();
        await this.fetchCurrentUser();
        this.updateHeaderUI();
        this._notifyAuthChange();
    }

    _bindDialogButtons() {
        // Open dialogs
        const loginTrigger = document.getElementById('auth-login-btn');
        const registerTrigger = document.getElementById('auth-register-btn');
        const logoutBtn = document.getElementById('auth-logout-btn');
        const switchToRegister = document.getElementById('switch-to-register');
        const switchToLogin = document.getElementById('switch-to-login');

        if (loginTrigger) loginTrigger.addEventListener('click', () => this.showLoginDialog());
        if (registerTrigger) registerTrigger.addEventListener('click', () => this.showRegisterDialog());
        if (logoutBtn) logoutBtn.addEventListener('click', () => this.logout());
        if (switchToRegister) switchToRegister.addEventListener('click', (e) => {
            e.preventDefault();
            this.hideLoginDialog();
            this.showRegisterDialog();
        });
        if (switchToLogin) switchToLogin.addEventListener('click', (e) => {
            e.preventDefault();
            this.hideRegisterDialog();
            this.showLoginDialog();
        });

        // Login form submit
        const loginForm = document.getElementById('login-form');
        if (loginForm) loginForm.addEventListener('submit', (e) => this._handleLoginSubmit(e));

        // Register form submit
        const registerForm = document.getElementById('register-form');
        if (registerForm) registerForm.addEventListener('submit', (e) => this._handleRegisterSubmit(e));
    }

    // ── API calls ─────────────────────────────────────────────────────────────

    async fetchCurrentUser() {
        try {
            const resp = await fetch('/auth/me');
            if (resp.ok) {
                const data = await resp.json();
                this.currentUser = data.user;
                this.limits = data.limits;
            } else {
                this.currentUser = null;
                this.limits = null;
            }
        } catch (_) {
            this.currentUser = null;
            this.limits = null;
        }
    }

    async login(email, password) {
        const resp = await fetch('/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Login failed.');
        this.currentUser = data.user;
        this.limits = data.limits;
        return data;
    }

    async register(email, displayName, password) {
        const resp = await fetch('/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, display_name: displayName, password }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Registration failed.');
        this.currentUser = data.user;
        this.limits = data.limits;
        return data;
    }

    async logout() {
        await fetch('/auth/logout', { method: 'POST' });
        this.currentUser = null;
        this.limits = null;
        this.updateHeaderUI();
        // Refresh auth-gated UI elements
        this._notifyAuthChange();
    }

    // ── UI update ─────────────────────────────────────────────────────────────

    updateHeaderUI() {
        const loggedOutArea = document.getElementById('auth-logged-out');
        const loggedInArea = document.getElementById('auth-logged-in');
        const userNameEl = document.getElementById('auth-user-name');
        const tierBadgeEl = document.getElementById('auth-tier-badge');

        if (this.isAuthenticated) {
            if (loggedOutArea) loggedOutArea.style.display = 'none';
            if (loggedInArea) loggedInArea.style.display = 'flex';
            if (userNameEl) userNameEl.textContent = this.currentUser.display_name;
            if (tierBadgeEl) {
                const tier = this.currentUser.tier;
                tierBadgeEl.textContent = tier.toUpperCase();
                tierBadgeEl.variant = tier === 'free' ? 'neutral' : tier === 'premium' ? 'primary' : 'success';
            }
        } else {
            if (loggedOutArea) loggedOutArea.style.display = 'flex';
            if (loggedInArea) loggedInArea.style.display = 'none';
        }

        // Show/hide auth-gated buttons
        document.querySelectorAll('[data-auth-required]').forEach(el => {
            el.style.display = this.isAuthenticated ? '' : 'none';
        });
        document.querySelectorAll('[data-premium-required]').forEach(el => {
            el.style.display = this.isPremium() ? '' : 'none';
        });
        document.querySelectorAll('[data-anon-only]').forEach(el => {
            el.style.display = this.isAuthenticated ? 'none' : '';
        });
    }

    showLoginDialog() {
        const dlg = document.getElementById('login-dialog');
        if (dlg) {
            document.getElementById('login-error')?.style.setProperty('display', 'none');
            document.getElementById('login-form')?.reset();
            dlg.show();
        }
    }

    hideLoginDialog() {
        const dlg = document.getElementById('login-dialog');
        if (dlg) dlg.hide();
    }

    showRegisterDialog() {
        const dlg = document.getElementById('register-dialog');
        if (dlg) {
            document.getElementById('register-error')?.style.setProperty('display', 'none');
            document.getElementById('register-form')?.reset();
            dlg.show();
        }
    }

    hideRegisterDialog() {
        const dlg = document.getElementById('register-dialog');
        if (dlg) dlg.hide();
    }

    // ── form handlers ─────────────────────────────────────────────────────────

    async _handleLoginSubmit(e) {
        e.preventDefault();
        const email = document.getElementById('login-email').value.trim();
        const password = document.getElementById('login-password').value;
        const errorEl = document.getElementById('login-error');
        const submitBtn = document.getElementById('login-submit-btn');

        this._setButtonLoading(submitBtn, true);
        try {
            await this.login(email, password);
            this.hideLoginDialog();
            this.updateHeaderUI();
            this._notifyAuthChange();
            this._promptSessionMigration();
        } catch (err) {
            if (errorEl) { errorEl.textContent = err.message; errorEl.style.display = ''; }
        } finally {
            this._setButtonLoading(submitBtn, false);
        }
    }

    async _handleRegisterSubmit(e) {
        e.preventDefault();
        const email = document.getElementById('register-email').value.trim();
        const displayName = document.getElementById('register-display-name').value.trim();
        const password = document.getElementById('register-password').value;
        const confirm = document.getElementById('register-confirm-password').value;
        const errorEl = document.getElementById('register-error');
        const submitBtn = document.getElementById('register-submit-btn');

        if (password !== confirm) {
            if (errorEl) { errorEl.textContent = 'Passwords do not match.'; errorEl.style.display = ''; }
            return;
        }

        this._setButtonLoading(submitBtn, true);
        try {
            await this.register(email, displayName, password);
            this.hideRegisterDialog();
            this.updateHeaderUI();
            this._notifyAuthChange();
            this._promptSessionMigration();
        } catch (err) {
            if (errorEl) { errorEl.textContent = err.message; errorEl.style.display = ''; }
        } finally {
            this._setButtonLoading(submitBtn, false);
        }
    }

    // ── session migration ─────────────────────────────────────────────────────

    async _promptSessionMigration() {
        if (!window.app || !window.app.waypoints || window.app.waypoints.length === 0) return;
        const confirmed = await window.showConfirmModal(
            `You have ${window.app.waypoints.length} unsaved waypoint(s) in your session. Save them to your account?`
        );
        if (!confirmed) return;

        const name = `My waypoints ${new Date().toLocaleDateString()}`;
        try {
            const resp = await fetch('/api/waypoints/files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, waypoints: window.app.waypoints }),
            });
            if (resp.ok) {
                window.app?.showStatus('Waypoints saved to your account.', 'success');
            }
        } catch (_) {
            // Non-fatal — ignore
        }
    }

    // ── helpers ───────────────────────────────────────────────────────────────

    _setButtonLoading(btn, loading) {
        if (!btn) return;
        btn.loading = loading;
        btn.disabled = loading;
    }

    _notifyAuthChange() {
        document.dispatchEvent(new CustomEvent('auth-changed', { detail: { user: this.currentUser } }));
    }

    getRemainingQuota(type) {
        if (!this.limits || !this.currentUser) return null;
        // Remaining calls must be computed after we know the actual counts
        // Use the limits object to compute a hint string
        const max = type === 'files' ? this.limits.max_waypoint_files : this.limits.max_saved_tasks;
        return max === null ? null : max;
    }
}

window.authManager = new AuthManager();
