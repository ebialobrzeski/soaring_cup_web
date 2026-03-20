/**
 * MyContentPanel — manages the "My Content" tab.
 * Shows the logged-in user their waypoint files, saved tasks, and custom gliders.
 */
class MyContentPanel {
    constructor() {
        this._filesLoaded = false;
        this._tasksLoaded = false;
        this._glidersLoaded = false;
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this._init());
        } else {
            this._init();
        }
    }

    _init() {
        this._bindListeners();
        document.addEventListener('auth-changed', () => this._onAuthChanged());
    }

    _onAuthChanged() {
        const isLoggedIn = !!window.authManager?.currentUser;
        const tab = document.getElementById('my-content-tab');
        if (tab) tab.style.display = isLoggedIn ? '' : 'none';
        if (!isLoggedIn) {
            this._filesLoaded = false;
            this._tasksLoaded = false;
            this._glidersLoaded = false;
        }
    }

    _bindListeners() {
        // Load files when the My Content main tab becomes active
        document.getElementById('main-tabs')?.addEventListener('sl-tab-show', (e) => {
            if (e.detail.name === 'my-content' && !this._filesLoaded) {
                this._loadFiles();
            }
        });

        // Lazy-load other sub-tabs on first activation
        document.getElementById('my-content-tabs')?.addEventListener('sl-tab-show', (e) => {
            if (e.detail.name === 'mc-files' && !this._filesLoaded) this._loadFiles();
            if (e.detail.name === 'mc-tasks' && !this._tasksLoaded) this._loadTasks();
            if (e.detail.name === 'mc-gliders' && !this._glidersLoaded) this._loadGliders();
            if (e.detail.name === 'mc-settings') this._loadSettings();
        });

        document.getElementById('mc-files-refresh-btn')?.addEventListener('click', () => {
            this._filesLoaded = false;
            this._loadFiles();
        });
        document.getElementById('mc-tasks-refresh-btn')?.addEventListener('click', () => {
            this._tasksLoaded = false;
            this._loadTasks();
        });
        document.getElementById('mc-gliders-refresh-btn')?.addEventListener('click', () => {
            this._glidersLoaded = false;
            this._loadGliders();
        });

        // Add Glider button re-uses the AI Planner dialog
        document.getElementById('mc-gliders-add-btn')?.addEventListener('click', () => {
            window.aiPlanner?._openManageGlidersDialog();
        });

        document.getElementById('mc-settings-save-btn')?.addEventListener('click', () => {
            this._saveLanguagePreference();
        });

        // API key management
        document.getElementById('mc-apikey-save-btn')?.addEventListener('click', () => {
            this._saveApiKey();
        });
        document.getElementById('mc-apikey-remove-btn')?.addEventListener('click', () => {
            this._removeApiKey();
        });
    }

    // ── Settings ─────────────────────────────────────────────────────────────

    _loadSettings() {
        const sel = document.getElementById('mc-lang-pref');
        if (!sel) return;
        const populate = async (languages) => {
            sel.innerHTML = '';
            // Add a 'use browser default' option
            const defaultOpt = document.createElement('sl-option');
            defaultOpt.value = '';
            defaultOpt.textContent = '— ' + (window.i18n?.t('mc.language_pref_default', 'Browser default') || 'Browser default') + ' —';
            sel.appendChild(defaultOpt);
            languages.forEach(lang => {
                const opt = document.createElement('sl-option');
                opt.value = lang.code;
                opt.textContent = `${lang.flag_emoji || ''} ${lang.native_name}`.trim();
                sel.appendChild(opt);
            });
            const preferred = window.authManager?.currentUser?.preferred_language || '';
            // Wait for sl-select to process its new children before setting value
            try { await sel.updateComplete; } catch (_) { /* not a Lit component */ }
            sel.value = preferred;
        };

        // Try to get language list from i18n module internals, fall back to fetch
        fetch('/api/i18n/languages')
            .then(r => r.json())
            .then(data => { if (data.success) populate(data.languages); })
            .catch(() => {});

        // Load API key status
        this._loadApiKeyStatus();
    }

    async _saveLanguagePreference() {
        const sel = document.getElementById('mc-lang-pref');
        const statusEl = document.getElementById('mc-settings-msg');
        if (!sel) return;
        const langCode = sel.value || null;
        try {
            const resp = await fetch('/auth/me/language', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lang_code: langCode }),
            });
            if (!resp.ok) {
                const d = await resp.json();
                window.app?.showStatus(d.error || 'Failed to save language preference.', 'error');
                return;
            }
            // Update the in-memory user object
            if (window.authManager?.currentUser) {
                window.authManager.currentUser.preferred_language = langCode;
            }
            // Apply the language immediately
            const applyLang = langCode || window.i18n?.currentLang || 'en';
            await window.i18n?.setLanguage(applyLang);
            if (statusEl) {
                statusEl.textContent = window.i18n?.t('mc.settings_saved', 'Settings saved!');
                statusEl.style.display = '';
                setTimeout(() => { statusEl.style.display = 'none'; }, 3000);
            }
        } catch {
            window.app?.showStatus('Network error saving language preference.', 'error');
        }
    }

    // ── API Key Management ──────────────────────────────────────────────────

    async _loadApiKeyStatus() {
        const statusEl = document.getElementById('mc-apikey-status');
        const removeBtn = document.getElementById('mc-apikey-remove-btn');
        if (!statusEl) return;
        try {
            const resp = await fetch('/auth/me/api-key');
            if (!resp.ok) return;
            const data = await resp.json();
            if (data.has_key) {
                const mask = window.i18n?.t('settings.key_mask', 'Key configured (ending …{0})').replace('{0}', data.last4) ||
                             `Key configured (ending …${data.last4})`;
                statusEl.innerHTML = `<i class="fas fa-check-circle" style="color:var(--sl-color-success-600);"></i> ${this._escapeHtml(mask)}`;
                if (removeBtn) removeBtn.style.display = '';
            } else {
                statusEl.innerHTML = `<i class="fas fa-info-circle" style="color:var(--sl-color-neutral-500);"></i> ${window.i18n?.t('settings.key_status_unset', 'No API key configured.') || 'No API key configured.'}`;
                if (removeBtn) removeBtn.style.display = 'none';
            }
        } catch { /* ignore */ }
    }

    async _saveApiKey() {
        const input = document.getElementById('mc-apikey-input');
        if (!input) return;
        const key = (input.value || '').trim();
        if (!key) {
            window.app?.showStatus(window.i18n?.t('settings.key_invalid', 'Invalid API key format.') || 'Invalid API key format.', 'error');
            return;
        }
        try {
            const resp = await fetch('/auth/me/api-key', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ api_key: key }),
            });
            const data = await resp.json();
            if (!resp.ok) {
                window.app?.showStatus(data.error || 'Failed to save API key.', 'error');
                return;
            }
            input.value = '';
            if (window.authManager?.currentUser) {
                window.authManager.currentUser.has_openrouter_key = true;
            }
            window.app?.showStatus(window.i18n?.t('settings.key_saved', 'API key saved successfully.') || 'API key saved successfully.', 'success');
            this._loadApiKeyStatus();
            // Refresh AI planner panel visibility
            window.app?._updateAiPlannerPanel();
        } catch {
            window.app?.showStatus('Network error saving API key.', 'error');
        }
    }

    async _removeApiKey() {
        try {
            const resp = await fetch('/auth/me/api-key', { method: 'DELETE' });
            const data = await resp.json();
            if (!resp.ok) {
                window.app?.showStatus(data.error || 'Failed to remove API key.', 'error');
                return;
            }
            if (window.authManager?.currentUser) {
                window.authManager.currentUser.has_openrouter_key = false;
            }
            window.app?.showStatus(window.i18n?.t('settings.key_removed', 'API key removed.') || 'API key removed.', 'success');
            this._loadApiKeyStatus();
            // Refresh AI planner panel visibility
            window.app?._updateAiPlannerPanel();
        } catch {
            window.app?.showStatus('Network error removing API key.', 'error');
        }
    }

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ── Waypoint Files ──────────────────────────────────────────────────────

    async _loadFiles() {
        this._filesLoaded = true;
        const tbody = document.getElementById('mc-files-tbody');
        const loading = document.getElementById('mc-files-loading');
        const errorEl = document.getElementById('mc-files-error');
        if (!tbody) return;

        loading.style.display = '';
        errorEl.style.display = 'none';
        tbody.innerHTML = '';

        try {
            const resp = await fetch('/api/waypoints/files');
            if (!resp.ok) throw new Error((await resp.json()).error || 'Failed to load files.');
            const files = await resp.json();
            const countEl = document.getElementById('mc-files-count');
            if (countEl) countEl.textContent = files.length;
            this._renderFilesTable(files, tbody);
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.style.display = '';
        } finally {
            loading.style.display = 'none';
        }
    }

    _renderFilesTable(files, tbody) {
        if (!files.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--text-secondary);">No saved waypoint files. Use the toolbar to save your current waypoints.</td></tr>';
            return;
        }

        tbody.innerHTML = files.map(f => {
            const visBadge = f.is_public
                ? '<sl-badge variant="neutral" pill>Public</sl-badge>'
                : '<sl-badge variant="warning" pill>Private</sl-badge>';
            const countries = f.country_codes
                ? f.country_codes.split(',').slice(0, 5)
                    .map(c => `<sl-badge variant="neutral" pill size="small">${escapeHtml(c.trim())}</sl-badge>`)
                    .join(' ')
                : '—';
            const date = f.created_at ? new Date(f.created_at).toLocaleDateString() : '—';
            return `<tr data-id="${escapeHtml(f.id)}">
                <td class="admin-cell-email" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</td>
                <td>${f.waypoint_count}</td>
                <td>${countries}</td>
                <td>${visBadge}</td>
                <td>${date}</td>
                <td class="admin-actions-cell">
                    <sl-button size="small" variant="neutral" class="mc-dl-btn" title="Download as CUP">
                        <i class="fas fa-download"></i>
                    </sl-button>
                    <sl-button size="small" variant="primary" class="mc-load-btn" title="Load into editor">
                        <i class="fas fa-upload"></i>
                    </sl-button>
                    <sl-button size="small" variant="neutral" class="mc-vis-btn" title="${f.is_public ? 'Make private' : 'Make public'}">
                        <i class="fas fa-${f.is_public ? 'lock' : 'globe'}"></i>
                    </sl-button>
                    <sl-button size="small" variant="danger" class="mc-del-btn" title="Delete">
                        <i class="fas fa-trash"></i>
                    </sl-button>
                </td>
            </tr>`;
        }).join('');

        tbody.querySelectorAll('tr[data-id]').forEach(row => {
            const id = row.dataset.id;
            const file = files.find(f => f.id === id);
            row.querySelector('.mc-dl-btn')?.addEventListener('click', () => this._downloadFile(id));
            row.querySelector('.mc-load-btn')?.addEventListener('click', () => this._loadFile(id));
            row.querySelector('.mc-vis-btn')?.addEventListener('click', () => this._toggleFileVis(id, file, row));
            row.querySelector('.mc-del-btn')?.addEventListener('click', () => this._deleteFile(id, file, row));
        });
    }

    _downloadFile(id) {
        const a = document.createElement('a');
        a.href = `/api/waypoints/files/${encodeURIComponent(id)}/download`;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    async _loadFile(id) {
        try {
            const resp = await fetch(`/api/waypoints/files/${id}`);
            if (!resp.ok) throw new Error((await resp.json()).error || 'Failed to load file.');
            const data = await resp.json();
            if (window.app) {
                window.app.waypoints = data.waypoints;
                window.app.updateUI(true);
                window.app.showStatus(`Loaded "${data.file.name}" — ${data.waypoints.length} waypoints.`, 'success');
                document.querySelector('#main-tabs sl-tab[panel="map"]')?.click();
            }
        } catch (err) {
            window.app?.showStatus('Error: ' + err.message, 'error');
        }
    }

    async _toggleFileVis(id, file, row) {
        const newPublic = !file.is_public;
        try {
            const resp = await fetch(`/api/waypoints/files/${id}/visibility`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_public: newPublic }),
            });
            const data = await resp.json();
            if (!resp.ok) {
                window.app?.showStatus(data.error || 'Failed to update visibility.', 'error');
                return;
            }
            file.is_public = data.is_public;
            row.cells[3].innerHTML = data.is_public
                ? '<sl-badge variant="neutral" pill>Public</sl-badge>'
                : '<sl-badge variant="warning" pill>Private</sl-badge>';
            const btn = row.querySelector('.mc-vis-btn');
            if (btn) {
                btn.title = data.is_public ? 'Make private' : 'Make public';
                btn.innerHTML = `<i class="fas fa-${data.is_public ? 'lock' : 'globe'}"></i>`;
            }
        } catch {
            window.app?.showStatus('Network error.', 'error');
        }
    }

    async _deleteFile(id, file, row) {
        const confirmed = await window.showConfirmModal(`Delete waypoint file "${file.name}"? This cannot be undone.`);
        if (!confirmed) return;
        try {
            const resp = await fetch(`/api/waypoints/files/${id}`, { method: 'DELETE' });
            if (!resp.ok && resp.status !== 204) {
                const d = await resp.json();
                window.app?.showStatus(d.error || 'Delete failed.', 'error');
                return;
            }
            row.remove();
            const el = document.getElementById('mc-files-count');
            if (el) el.textContent = Math.max(0, parseInt(el.textContent, 10) - 1);
        } catch {
            window.app?.showStatus('Network error.', 'error');
        }
    }

    // ── Tasks ────────────────────────────────────────────────────────────────

    async _loadTasks() {
        this._tasksLoaded = true;
        const tbody = document.getElementById('mc-tasks-tbody');
        const loading = document.getElementById('mc-tasks-loading');
        const errorEl = document.getElementById('mc-tasks-error');
        if (!tbody) return;

        loading.style.display = '';
        errorEl.style.display = 'none';
        tbody.innerHTML = '';

        try {
            const resp = await fetch('/api/tasks');
            if (!resp.ok) throw new Error((await resp.json()).error || 'Failed to load tasks.');
            const tasks = await resp.json();
            const countEl = document.getElementById('mc-tasks-count');
            if (countEl) countEl.textContent = tasks.length;
            this._renderTasksTable(tasks, tbody);
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.style.display = '';
        } finally {
            loading.style.display = 'none';
        }
    }

    _renderTasksTable(tasks, tbody) {
        if (!tasks.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--text-secondary);">No saved tasks. Use the Task Planner to create and save tasks.</td></tr>';
            return;
        }

        tbody.innerHTML = tasks.map(t => {
            const points = (t.task_data?.points || []).length;
            const dist = t.total_distance ? `${Number(t.total_distance).toFixed(1)} km` : '—';
            const visBadge = t.is_public
                ? '<sl-badge variant="neutral" pill>Public</sl-badge>'
                : '<sl-badge variant="warning" pill>Private</sl-badge>';
            const date = t.created_at ? new Date(t.created_at).toLocaleDateString() : '—';
            return `<tr data-id="${escapeHtml(t.id)}">
                <td class="admin-cell-email" title="${escapeHtml(t.name)}">${escapeHtml(t.name)}</td>
                <td>${points}</td>
                <td>${escapeHtml(dist)}</td>
                <td>${visBadge}</td>
                <td>${date}</td>
                <td class="admin-actions-cell">
                    <sl-dropdown class="mc-task-dl-dropdown">
                        <sl-button slot="trigger" size="small" variant="neutral" caret title="Download">
                            <i class="fas fa-download"></i>
                        </sl-button>
                        <sl-menu>
                            <sl-menu-item data-fmt="cup">SeeYou CUP (.cup)</sl-menu-item>
                            <sl-menu-item data-fmt="tsk">XCSoar TSK (.tsk)</sl-menu-item>
                            <sl-menu-item data-fmt="xctsk">XCTrack XCTSK (.xctsk)</sl-menu-item>
                            <sl-menu-item data-fmt="lkt">LK8000 LKT (.lkt)</sl-menu-item>
                        </sl-menu>
                    </sl-dropdown>
                    <sl-button size="small" variant="primary" class="mc-load-btn" title="Load into Task Planner">
                        <i class="fas fa-upload"></i>
                    </sl-button>
                    <sl-button size="small" variant="neutral" class="mc-vis-btn" title="${t.is_public ? 'Make private' : 'Make public'}">
                        <i class="fas fa-${t.is_public ? 'lock' : 'globe'}"></i>
                    </sl-button>
                    <sl-button size="small" variant="danger" class="mc-del-btn" title="Delete">
                        <i class="fas fa-trash"></i>
                    </sl-button>
                </td>
            </tr>`;
        }).join('');

        tbody.querySelectorAll('tr[data-id]').forEach(row => {
            const id = row.dataset.id;
            const task = tasks.find(t => t.id === id);
            row.querySelector('.mc-task-dl-dropdown')?.addEventListener('sl-select', (e) => this._downloadTask(id, e.detail.item.dataset.fmt));
            row.querySelector('.mc-load-btn')?.addEventListener('click', () => this._loadTask(task));
            row.querySelector('.mc-vis-btn')?.addEventListener('click', () => this._toggleTaskVis(id, task, row));
            row.querySelector('.mc-del-btn')?.addEventListener('click', () => this._deleteTask(id, task, row));
        });
    }

    _downloadTask(id, format) {
        const a = document.createElement('a');
        a.href = `/api/tasks/${encodeURIComponent(id)}/download?format=${encodeURIComponent(format)}`;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    _loadTask(task) {
        if (window.taskPlanner) {
            window.taskPlanner.loadTaskData(task.task_data || {});
            window.app?.showStatus(`Loaded task "${task.name}".`, 'success');
            document.querySelector('#main-tabs sl-tab[panel="task"]')?.click();
        }
    }

    async _toggleTaskVis(id, task, row) {
        const newPublic = !task.is_public;
        try {
            const resp = await fetch(`/api/tasks/${id}/visibility`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_public: newPublic }),
            });
            const data = await resp.json();
            if (!resp.ok) {
                window.app?.showStatus(data.error || 'Failed to update visibility.', 'error');
                return;
            }
            task.is_public = data.is_public;
            row.cells[3].innerHTML = data.is_public
                ? '<sl-badge variant="neutral" pill>Public</sl-badge>'
                : '<sl-badge variant="warning" pill>Private</sl-badge>';
            const btn = row.querySelector('.mc-vis-btn');
            if (btn) {
                btn.title = data.is_public ? 'Make private' : 'Make public';
                btn.innerHTML = `<i class="fas fa-${data.is_public ? 'lock' : 'globe'}"></i>`;
            }
        } catch {
            window.app?.showStatus('Network error.', 'error');
        }
    }

    async _deleteTask(id, task, row) {
        const confirmed = await window.showConfirmModal(`Delete task "${task.name}"? This cannot be undone.`);
        if (!confirmed) return;
        try {
            const resp = await fetch(`/api/tasks/${id}`, { method: 'DELETE' });
            if (!resp.ok && resp.status !== 204) {
                const d = await resp.json();
                window.app?.showStatus(d.error || 'Delete failed.', 'error');
                return;
            }
            row.remove();
            const el = document.getElementById('mc-tasks-count');
            if (el) el.textContent = Math.max(0, parseInt(el.textContent, 10) - 1);
        } catch {
            window.app?.showStatus('Network error.', 'error');
        }
    }

    // ── Custom Gliders ──────────────────────────────────────────────────────

    async _loadGliders() {
        this._glidersLoaded = true;
        const tbody = document.getElementById('mc-gliders-tbody');
        const loading = document.getElementById('mc-gliders-loading');
        const errorEl = document.getElementById('mc-gliders-error');
        if (!tbody) return;

        loading.style.display = '';
        errorEl.style.display = 'none';
        tbody.innerHTML = '';

        try {
            const resp = await fetch('/api/planner/gliders');
            if (!resp.ok) throw new Error('Failed to load gliders.');
            const all = await resp.json();
            const custom = all.filter(g => g.is_custom);
            const countEl = document.getElementById('mc-gliders-count');
            if (countEl) countEl.textContent = custom.length;
            this._renderGlidersTable(custom, tbody);
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.style.display = '';
        } finally {
            loading.style.display = 'none';
        }
    }

    _renderGlidersTable(gliders, tbody) {
        if (!gliders.length) {
            tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:20px; color:var(--text-secondary);">${window.i18n?.t('mc.no_gliders_action') ?? 'No custom gliders. Click \u201cAdd Glider\u201d to create one.'}</td></tr>`;
            return;
        }

        tbody.innerHTML = gliders.map(g => {
            const speedRange = (g.v1_kmh && g.v3_kmh)
                ? `${Math.round(g.v1_kmh)}–${Math.round(g.v3_kmh)} km/h`
                : '—';
            const maxGross = g.max_gross_kg ? `${g.max_gross_kg} kg` : '—';
            return `<tr data-id="${escapeHtml(g.id)}">
                <td>${escapeHtml(g.name)}</td>
                <td>${speedRange}</td>
                <td>${maxGross}</td>
                <td class="admin-actions-cell">
                    <sl-button size="small" variant="neutral" class="mc-edit-btn" title="Edit">
                        <i class="fas fa-edit"></i>
                    </sl-button>
                    <sl-button size="small" variant="neutral" class="mc-polar-btn" title="View polar chart">
                        <i class="fas fa-chart-line"></i>
                    </sl-button>
                    <sl-button size="small" variant="danger" class="mc-del-btn" title="Delete">
                        <i class="fas fa-trash"></i>
                    </sl-button>
                </td>
            </tr>`;
        }).join('');

        tbody.querySelectorAll('tr[data-id]').forEach(row => {
            const id = row.dataset.id;
            const glider = gliders.find(g => g.id === id);
            row.querySelector('.mc-edit-btn')?.addEventListener('click', () => {
                window.aiPlanner?._editCustomGlider(id);
            });
            row.querySelector('.mc-polar-btn')?.addEventListener('click', () => {
                window.aiPlanner?._showPolarChart(id);
            });
            row.querySelector('.mc-del-btn')?.addEventListener('click', () => this._deleteGlider(id, glider, row));
        });
    }

    async _deleteGlider(id, glider, row) {
        const confirmed = await window.showConfirmModal(`Delete glider "${glider.name}"? This cannot be undone.`);
        if (!confirmed) return;
        try {
            const resp = await fetch(`/api/planner/gliders/${id}`, { method: 'DELETE' });
            if (!resp.ok && resp.status !== 204) {
                const d = await resp.json();
                window.app?.showStatus(d.error || 'Delete failed.', 'error');
                return;
            }
            row.remove();
            const el = document.getElementById('mc-gliders-count');
            if (el) el.textContent = Math.max(0, parseInt(el.textContent, 10) - 1);
            // Keep AI Planner in sync
            window.aiPlanner?._fetchGliders();
        } catch {
            window.app?.showStatus('Network error.', 'error');
        }
    }
}

window.myContentPanel = new MyContentPanel();
