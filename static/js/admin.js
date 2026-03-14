/**
 * AdminPanel — manages the Admin tab: user list, tier changes, content management.
 * Only shown to users with tier === 'admin'.
 */
class AdminPanel {
    constructor() {
        this._currentPage = 1;
        this._currentUserId = null;
        this._searchTimeout = null;
        this._perPage = 25;
        // Wait for DOM ready before binding
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this._init());
        } else {
            this._init();
        }
    }

    _init() {
        this._bindListeners();
        // React to auth changes
        document.addEventListener('auth-changed', () => this._onAuthChanged());
    }

    _onAuthChanged() {
        const isAdmin = window.authManager?.currentUser?.tier === 'admin';
        const tab = document.getElementById('admin-tab');
        if (tab) tab.style.display = isAdmin ? '' : 'none';
    }

    _bindListeners() {
        document.getElementById('admin-user-search')?.addEventListener('sl-input', () => {
            clearTimeout(this._searchTimeout);
            this._searchTimeout = setTimeout(() => this._loadUsers(1), 350);
        });

        document.getElementById('admin-tier-filter')?.addEventListener('sl-change', () => this._loadUsers(1));
        document.getElementById('admin-user-refresh-btn')?.addEventListener('click', () => this._loadUsers(this._currentPage));

        document.getElementById('admin-content-back-btn')?.addEventListener('click', () => {
            document.getElementById('admin-content-user-info').style.display = 'none';
            document.getElementById('admin-content-user-name').textContent = '';
            // Switch back to users sub-tab
            document.querySelector('#admin-tabs sl-tab[panel="admin-users"]')?.click();
        });

        // Usage tracking
        document.getElementById('usage-refresh-btn')?.addEventListener('click', () => this._loadUsage());
        document.getElementById('usage-period-select')?.addEventListener('sl-change', () => this._loadUsage());

        // Load users when admin tab becomes active
        document.getElementById('main-tabs')?.addEventListener('sl-tab-show', (e) => {
            if (e.detail.name === 'admin') this._loadUsers(1);
        });

        // Load usage data when sub-tab shown
        document.getElementById('admin-tabs')?.addEventListener('sl-tab-show', (e) => {
            if (e.detail.name === 'admin-usage') this._loadUsage();
            if (e.detail.name === 'admin-airports') this._loadAirportStats();
        });

        // Airport import
        document.getElementById('airport-import-btn')?.addEventListener('click', () => this._startAirportImport());
        document.getElementById('airport-stats-btn')?.addEventListener('click', () => this._loadAirportStats());
    }

    // ── Users ────────────────────────────────────────────────────────────────

    async _loadUsers(page = 1) {
        this._currentPage = page;
        const q = document.getElementById('admin-user-search')?.value?.trim() || '';
        const tier = document.getElementById('admin-tier-filter')?.value || '';

        const url = new URL('/api/admin/users', window.location.origin);
        url.searchParams.set('page', page);
        url.searchParams.set('per_page', this._perPage);
        if (q) url.searchParams.set('q', q);
        if (tier) url.searchParams.set('tier', tier);

        this._setUsersLoading(true);
        this._showUsersError('');
        try {
            const resp = await fetch(url);
            const data = await resp.json();
            if (!resp.ok) { this._showUsersError(data.error || 'Failed to load users.'); return; }
            this._renderUsersTable(data.items);
            this._renderUsersPagination(data.total, data.page, data.per_page);
        } catch {
            this._showUsersError('Network error. Could not load users.');
        } finally {
            this._setUsersLoading(false);
        }
    }

    _renderUsersTable(users) {
        const tbody = document.getElementById('admin-users-tbody');
        if (!tbody) return;

        if (!users.length) {
            tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; padding:20px; color:var(--text-secondary);">No users found.</td></tr>';
            return;
        }

        tbody.innerHTML = users.map(u => {
            const tierBadge = {
                admin: '<sl-badge variant="danger" pill>Admin</sl-badge>',
                premium: '<sl-badge variant="success" pill>Premium</sl-badge>',
                free: '<sl-badge variant="neutral" pill>Free</sl-badge>',
            }[u.tier] || `<sl-badge variant="neutral" pill>${escapeHtml(u.tier)}</sl-badge>`;

            const activeBadge = u.is_active
                ? '<sl-badge variant="success" pill>Active</sl-badge>'
                : '<sl-badge variant="warning" pill>Disabled</sl-badge>';

            const verifiedBadge = u.email_verified
                ? '<sl-badge variant="success" pill><i class="fas fa-check"></i></sl-badge>'
                : '<sl-badge variant="neutral" pill><i class="fas fa-clock"></i></sl-badge>';

            const registered = u.created_at ? new Date(u.created_at).toLocaleDateString() : '—';

            return `<tr data-user-id="${escapeHtml(u.id)}">
                <td class="admin-cell-email" title="${escapeHtml(u.email)}">${escapeHtml(u.email)}</td>
                <td>${escapeHtml(u.display_name)}</td>
                <td>${tierBadge}</td>
                <td>${activeBadge}</td>
                <td>${verifiedBadge}</td>
                <td>${u.file_count}</td>
                <td>${u.task_count}</td>
                <td>${registered}</td>
                <td class="admin-actions-cell">
                    <sl-button size="small" variant="neutral" class="admin-content-btn" title="View content">
                        <i class="fas fa-folder-open"></i>
                    </sl-button>
                    <sl-dropdown>
                        <sl-button size="small" slot="trigger" caret>Tier</sl-button>
                        <sl-menu class="admin-tier-menu">
                            <sl-menu-item value="free">Free</sl-menu-item>
                            <sl-menu-item value="premium">Premium</sl-menu-item>
                            <sl-menu-item value="admin">Admin</sl-menu-item>
                        </sl-menu>
                    </sl-dropdown>
                    <sl-button size="small" variant="${u.is_active ? 'warning' : 'success'}" class="admin-toggle-btn" title="${u.is_active ? 'Disable' : 'Enable'} account">
                        <i class="fas fa-${u.is_active ? 'ban' : 'check'}"></i>
                    </sl-button>
                    <sl-button size="small" variant="danger" class="admin-delete-btn" title="Delete user">
                        <i class="fas fa-trash"></i>
                    </sl-button>
                </td>
            </tr>`;
        }).join('');

        // Bind row actions
        tbody.querySelectorAll('tr[data-user-id]').forEach(row => {
            const userId = row.dataset.userId;
            const userObj = users.find(u => u.id === userId);

            row.querySelector('.admin-content-btn')?.addEventListener('click', () => this._viewContent(userId, userObj));

            row.querySelector('.admin-tier-menu')?.addEventListener('sl-select', async (e) => {
                await this._setTier(userId, e.detail.item.value, row, userObj);
            });

            row.querySelector('.admin-toggle-btn')?.addEventListener('click', async () => {
                await this._toggleActive(userId, !userObj.is_active, row, userObj);
            });

            row.querySelector('.admin-delete-btn')?.addEventListener('click', async () => {
                await this._deleteUser(userId, userObj, row);
            });
        });
    }

    _renderUsersPagination(total, page, perPage) {
        const el = document.getElementById('admin-users-pagination');
        if (!el) return;
        el.innerHTML = '';
        const totalPages = Math.ceil(total / perPage);
        if (totalPages <= 1) return;

        const info = document.createElement('span');
        info.style.cssText = 'color:var(--text-secondary); font-size:.85rem;';
        info.textContent = `${(page - 1) * perPage + 1}–${Math.min(page * perPage, total)} of ${total}`;
        el.appendChild(info);

        const prev = document.createElement('sl-button');
        prev.size = 'small';
        prev.disabled = page <= 1;
        prev.textContent = '← Prev';
        prev.addEventListener('click', () => this._loadUsers(page - 1));
        el.appendChild(prev);

        const next = document.createElement('sl-button');
        next.size = 'small';
        next.disabled = page >= totalPages;
        next.textContent = 'Next →';
        next.addEventListener('click', () => this._loadUsers(page + 1));
        el.appendChild(next);
    }

    async _setTier(userId, newTier, row, userObj) {
        try {
            const resp = await fetch(`/api/admin/users/${userId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tier: newTier }),
            });
            const data = await resp.json();
            if (!resp.ok) { alert(data.error || 'Failed to update tier.'); return; }
            userObj.tier = data.tier;
            // Re-render just the tier cell
            const tierCell = row.cells[2];
            const tierBadge = {
                admin: '<sl-badge variant="danger" pill>Admin</sl-badge>',
                premium: '<sl-badge variant="success" pill>Premium</sl-badge>',
                free: '<sl-badge variant="neutral" pill>Free</sl-badge>',
            }[data.tier] || `<sl-badge variant="neutral" pill>${escapeHtml(data.tier)}</sl-badge>`;
            tierCell.innerHTML = tierBadge;
        } catch {
            alert('Network error.');
        }
    }

    async _toggleActive(userId, newActive, row, userObj) {
        const action = newActive ? 'enable' : 'disable';
        if (!confirm(`${action.charAt(0).toUpperCase() + action.slice(1)} this account?`)) return;
        try {
            const resp = await fetch(`/api/admin/users/${userId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_active: newActive }),
            });
            const data = await resp.json();
            if (!resp.ok) { alert(data.error || 'Failed to update account.'); return; }
            userObj.is_active = data.is_active;
            // Re-render active + toggle button cells
            row.cells[3].innerHTML = data.is_active
                ? '<sl-badge variant="success" pill>Active</sl-badge>'
                : '<sl-badge variant="warning" pill>Disabled</sl-badge>';
            const btn = row.querySelector('.admin-toggle-btn');
            if (btn) {
                btn.variant = data.is_active ? 'warning' : 'success';
                btn.title = data.is_active ? 'Disable account' : 'Enable account';
                btn.innerHTML = `<i class="fas fa-${data.is_active ? 'ban' : 'check'}"></i>`;
            }
        } catch {
            alert('Network error.');
        }
    }

    async _deleteUser(userId, userObj, row) {
        if (!confirm(`Permanently delete user "${userObj.email}" and ALL their content? This cannot be undone.`)) return;
        try {
            const resp = await fetch(`/api/admin/users/${userId}`, { method: 'DELETE' });
            const data = await resp.json();
            if (!resp.ok) { alert(data.error || 'Failed to delete user.'); return; }
            row.remove();
        } catch {
            alert('Network error.');
        }
    }

    // ── Content ──────────────────────────────────────────────────────────────

    async _viewContent(userId, userObj) {
        this._currentUserId = userId;

        // Switch to the content sub-tab
        document.querySelector('#admin-tabs sl-tab[panel="admin-content"]')?.click();

        const infoEl = document.getElementById('admin-content-user-info');
        const nameEl = document.getElementById('admin-content-user-name');
        if (infoEl) infoEl.style.display = '';
        if (nameEl) nameEl.textContent = `${userObj.display_name} (${userObj.email})`;

        document.getElementById('admin-files-list').innerHTML = '<sl-spinner></sl-spinner>';
        document.getElementById('admin-tasks-list').innerHTML = '';

        try {
            const resp = await fetch(`/api/admin/users/${userId}/content`);
            const data = await resp.json();
            if (!resp.ok) {
                document.getElementById('admin-files-list').innerHTML = `<p class="admin-error">${escapeHtml(data.error || 'Failed to load content.')}</p>`;
                return;
            }
            this._renderContentFiles(data.files);
            this._renderContentTasks(data.tasks);
            document.getElementById('admin-content-file-count').textContent = data.files.length;
            document.getElementById('admin-content-task-count').textContent = data.tasks.length;
        } catch {
            document.getElementById('admin-files-list').innerHTML = '<p class="admin-error">Network error.</p>';
        }
    }

    _renderContentFiles(files) {
        const el = document.getElementById('admin-files-list');
        if (!el) return;
        if (!files.length) {
            el.innerHTML = '<p style="color:var(--text-secondary); padding:12px;">No waypoint files.</p>';
            return;
        }
        el.innerHTML = files.map(f => `
            <div class="admin-content-item" data-id="${escapeHtml(f.id)}">
                <div class="admin-content-item-info">
                    <span class="admin-content-item-name">${escapeHtml(f.name)}</span>
                    <span class="admin-content-item-meta">${f.waypoint_count} waypoints &middot; ${f.is_public ? 'Public' : 'Private'}</span>
                </div>
                <sl-button size="small" variant="danger" class="admin-delete-file-btn">
                    <i class="fas fa-trash" slot="prefix"></i> Delete
                </sl-button>
            </div>`).join('');
        el.querySelectorAll('[data-id]').forEach(row => {
            row.querySelector('.admin-delete-file-btn')?.addEventListener('click', async () => {
                if (!confirm('Delete this waypoint file?')) return;
                const resp = await fetch(`/api/admin/content/files/${row.dataset.id}`, { method: 'DELETE' });
                if (resp.ok) { row.remove(); this._decrementCount('admin-content-file-count'); }
                else { const d = await resp.json(); alert(d.error || 'Delete failed.'); }
            });
        });
    }

    _renderContentTasks(tasks) {
        const el = document.getElementById('admin-tasks-list');
        if (!el) return;
        if (!tasks.length) {
            el.innerHTML = '<p style="color:var(--text-secondary); padding:12px;">No saved tasks.</p>';
            return;
        }
        el.innerHTML = tasks.map(t => `
            <div class="admin-content-item" data-id="${escapeHtml(t.id)}">
                <div class="admin-content-item-info">
                    <span class="admin-content-item-name">${escapeHtml(t.name)}</span>
                    <span class="admin-content-item-meta">${t.total_distance ? t.total_distance + ' km' : ''} &middot; ${t.is_public ? 'Public' : 'Private'}</span>
                </div>
                <sl-button size="small" variant="danger" class="admin-delete-task-btn">
                    <i class="fas fa-trash" slot="prefix"></i> Delete
                </sl-button>
            </div>`).join('');
        el.querySelectorAll('[data-id]').forEach(row => {
            row.querySelector('.admin-delete-task-btn')?.addEventListener('click', async () => {
                if (!confirm('Delete this task?')) return;
                const resp = await fetch(`/api/admin/content/tasks/${row.dataset.id}`, { method: 'DELETE' });
                if (resp.ok) { row.remove(); this._decrementCount('admin-content-task-count'); }
                else { const d = await resp.json(); alert(d.error || 'Delete failed.'); }
            });
        });
    }

    _decrementCount(elId) {
        const el = document.getElementById(elId);
        if (el) el.textContent = Math.max(0, parseInt(el.textContent, 10) - 1);
    }

    // ── Usage Tracking ─────────────────────────────────────────────────────────

    async _loadUsage() {
        const days = document.getElementById('usage-period-select')?.value || '30';
        this._setUsageLoading(true);
        this._showUsageError('');
        try {
            const resp = await fetch(`/api/admin/usage/summary?days=${days}`);
            if (!resp.ok) throw new Error((await resp.json()).error || resp.statusText);
            const data = await resp.json();
            this._renderUsageSummary(data);
            // Also fetch first page of log
            await this._loadUsageLog(1);
        } catch (err) {
            this._showUsageError(err.message);
        } finally {
            this._setUsageLoading(false);
        }
    }

    _renderUsageSummary(data) {
        document.getElementById('usage-summary-cards').style.display = '';
        document.getElementById('usage-total-calls').textContent = data.total_calls.toLocaleString();
        document.getElementById('usage-endpoint-count').textContent = data.by_endpoint.length;
        const totalErrors = data.by_endpoint.reduce((s, e) => s + (e.errors || 0), 0);
        document.getElementById('usage-total-errors').textContent = totalErrors;
        document.getElementById('usage-unique-users').textContent = data.top_users.length;

        // Endpoint table
        const epSection = document.getElementById('usage-endpoint-section');
        const epBody = document.getElementById('usage-endpoint-tbody');
        if (data.by_endpoint.length) {
            epSection.style.display = '';
            epBody.innerHTML = data.by_endpoint.map(e =>
                `<tr><td><code>${this._esc(e.endpoint)}</code></td><td>${e.count}</td><td>${e.avg_time_ms ?? '—'}</td><td>${e.errors || 0}</td></tr>`
            ).join('');
        } else {
            epSection.style.display = 'none';
        }

        // Daily chart
        const dailySection = document.getElementById('usage-daily-section');
        const chart = document.getElementById('usage-daily-chart');
        if (data.by_day.length) {
            dailySection.style.display = '';
            const max = Math.max(...data.by_day.map(d => d.count), 1);
            chart.innerHTML = data.by_day.map(d => {
                const h = Math.max(2, (d.count / max) * 90);
                return `<div class="usage-bar" style="height:${h}px" title="${d.date}: ${d.count} calls, ${d.errors} errors"></div>`;
            }).join('');
        } else {
            dailySection.style.display = 'none';
        }

        // External APIs
        const extSection = document.getElementById('usage-external-section');
        const extBody = document.getElementById('usage-external-tbody');
        if (data.external_apis.length) {
            extSection.style.display = '';
            extBody.innerHTML = data.external_apis.map(e =>
                `<tr><td>${this._esc(e.service)}</td><td>${e.count}</td><td>${e.total_calls ?? '—'}</td><td>${e.total_ok ?? '—'}</td><td>${e.total_errors ?? '—'}</td><td>${e.avg_time_ms ?? '—'}</td></tr>`
            ).join('');
        } else {
            extSection.style.display = 'none';
        }

        // Top users
        const tuSection = document.getElementById('usage-topusers-section');
        const tuBody = document.getElementById('usage-topusers-tbody');
        if (data.top_users.length) {
            tuSection.style.display = '';
            tuBody.innerHTML = data.top_users.map(u =>
                `<tr><td>${this._esc(u.email)}</td><td>${u.count}</td></tr>`
            ).join('');
        } else {
            tuSection.style.display = 'none';
        }

        // Recent errors
        const errSection = document.getElementById('usage-errors-section');
        const errBody = document.getElementById('usage-errors-tbody');
        if (data.recent_errors.length) {
            errSection.style.display = '';
            errBody.innerHTML = data.recent_errors.map(e => {
                const t = e.time ? new Date(e.time).toLocaleString() : '—';
                return `<tr><td>${t}</td><td><code>${this._esc(e.endpoint)}</code></td><td>${e.status}</td><td>${this._esc(e.error || '')}</td></tr>`;
            }).join('');
        } else {
            errSection.style.display = 'none';
        }
    }

    async _loadUsageLog(page = 1) {
        this._usageLogPage = page;
        const section = document.getElementById('usage-log-section');
        section.style.display = '';
        const tbody = document.getElementById('usage-log-tbody');
        const pag = document.getElementById('usage-log-pagination');
        try {
            const resp = await fetch(`/api/admin/usage/log?page=${page}&per_page=30`);
            if (!resp.ok) throw new Error('Failed to load log');
            const data = await resp.json();
            tbody.innerHTML = data.entries.map(e => {
                const t = e.created_at ? new Date(e.created_at).toLocaleString() : '—';
                return `<tr><td>${t}</td><td>${this._esc(e.user_id || '—')}</td><td><code>${this._esc(e.endpoint)}</code></td><td>${e.response_status}</td><td>${e.response_time_ms ?? '—'}</td></tr>`;
            }).join('') || '<tr><td colspan="5" style="text-align:center;color:var(--text-secondary)">No records yet.</td></tr>';

            // Pagination
            pag.innerHTML = '';
            if (data.pages > 1) {
                if (page > 1) {
                    const prev = document.createElement('sl-button');
                    prev.size = 'small'; prev.variant = 'text'; prev.textContent = '← Prev';
                    prev.addEventListener('click', () => this._loadUsageLog(page - 1));
                    pag.appendChild(prev);
                }
                const info = document.createElement('span');
                info.style.fontSize = '.85rem';
                info.textContent = `Page ${page} of ${data.pages}`;
                pag.appendChild(info);
                if (page < data.pages) {
                    const next = document.createElement('sl-button');
                    next.size = 'small'; next.variant = 'text'; next.textContent = 'Next →';
                    next.addEventListener('click', () => this._loadUsageLog(page + 1));
                    pag.appendChild(next);
                }
            }
        } catch {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--sl-color-danger-600)">Failed to load log.</td></tr>';
        }
    }

    _esc(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    // ── Airports ──────────────────────────────────────────────────────────────

    async _loadAirportStats() {
        const statsWrap = document.getElementById('airport-stats-wrap');
        const tbody = document.getElementById('airport-stats-tbody');
        if (!statsWrap || !tbody) return;
        statsWrap.style.display = 'none';
        try {
            const resp = await fetch('/api/admin/airports/stats');
            const data = await resp.json();
            if (!resp.ok) { alert(data.error || 'Failed to load airport stats.'); return; }
            document.getElementById('airport-total-count').textContent = data.total.toLocaleString();
            document.getElementById('airport-country-count').textContent = data.by_country.length;
            tbody.innerHTML = data.by_country.map(r =>
                `<tr><td>${this._esc(r.country)}</td><td>${r.count.toLocaleString()}</td></tr>`
            ).join('');
            statsWrap.style.display = '';
        } catch {
            alert('Failed to load airport stats.');
        }
    }

    async _startAirportImport() {
        const btn = document.getElementById('airport-import-btn');
        const progressWrap = document.getElementById('airport-import-progress');
        const statusEl = document.getElementById('airport-import-status');
        const bar = document.getElementById('airport-import-bar');
        const resultEl = document.getElementById('airport-import-result');

        const countriesRaw = document.getElementById('airport-import-countries')?.value?.trim() || '';
        const countries = countriesRaw ? countriesRaw.toUpperCase().split(/[\s,]+/).filter(Boolean) : null;

        if (!confirm(countries
            ? `Import airports for: ${countries.join(', ')}?`
            : 'Import airports for ALL countries? This will take several minutes.')) return;

        btn.disabled = true;
        progressWrap.style.display = '';
        resultEl.style.display = 'none';
        statusEl.textContent = 'Starting…';
        bar.value = 0;

        try {
            const resp = await fetch('/api/admin/airports/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(countries ? { countries } : {}),
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.error || `HTTP ${resp.status}`);
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buf = '';
            let totalUpserted = 0;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += decoder.decode(value, { stream: true });
                const lines = buf.split('\n');
                buf = lines.pop();
                for (const line of lines) {
                    if (!line.trim()) continue;
                    try {
                        const msg = JSON.parse(line);
                        if (msg.type === 'progress') {
                            const pct = Math.round((msg.index / msg.total) * 100);
                            bar.value = pct;
                            statusEl.textContent = `[${msg.index}/${msg.total}] ${msg.country}: ${msg.upserted} airports — total: ${msg.total_upserted.toLocaleString()}`;
                            totalUpserted = msg.total_upserted;
                        } else if (msg.type === 'error') {
                            throw new Error(msg.message);
                        } else if (msg.type === 'done') {
                            totalUpserted = msg.total_upserted;
                        }
                    } catch { /* skip malformed line */ }
                }
            }

            bar.value = 100;
            statusEl.textContent = 'Done.';
            resultEl.style.display = '';
            resultEl.innerHTML = `<sl-alert variant="success" open><sl-icon slot="icon" name="check2-circle"></sl-icon>
                Import complete — <strong>${totalUpserted.toLocaleString()}</strong> airports upserted.</sl-alert>`;
            await this._loadAirportStats();

        } catch (err) {
            statusEl.textContent = 'Failed.';
            resultEl.style.display = '';
            resultEl.innerHTML = `<sl-alert variant="danger" open><sl-icon slot="icon" name="exclamation-octagon"></sl-icon>${this._esc(err.message)}</sl-alert>`;
        } finally {
            btn.disabled = false;
            progressWrap.querySelector('sl-spinner').style.display = 'none';
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    _setUsersLoading(on) {
        const el = document.getElementById('admin-users-loading');
        const wrap = document.getElementById('admin-users-table-wrap');
        if (el) el.style.display = on ? '' : 'none';
        if (wrap) wrap.style.opacity = on ? '0.5' : '';
    }

    _showUsersError(msg) {
        const el = document.getElementById('admin-users-error');
        if (!el) return;
        el.textContent = msg;
        el.style.display = msg ? '' : 'none';
    }

    _setUsageLoading(on) {
        const el = document.getElementById('usage-loading');
        if (el) el.style.display = on ? '' : 'none';
    }

    _showUsageError(msg) {
        const el = document.getElementById('usage-error');
        if (!el) return;
        el.textContent = msg;
        el.style.display = msg ? '' : 'none';
    }

}

window.adminPanel = new AdminPanel();
