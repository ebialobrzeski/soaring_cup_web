/**
 * Shared HTML-escape utility used by BrowseDialog and other standalone code.
 */
function escapeHtml(text) {
    const s = String(text ?? '');
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
             .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/**
 * BrowseDialog — reusable dialog for browsing public/private waypoint files and tasks.
 *
 * Usage:
 *   const waypointBrowser = new BrowseDialog('waypoints');
 *   waypointBrowser.open();
 */
class BrowseDialog {
    /**
     * @param {'waypoints'|'tasks'} type
     */
    constructor(type) {
        this.type = type;
        this.dialogId = type === 'waypoints' ? 'browse-waypoints-dialog' : 'browse-tasks-dialog';
        this.currentPage = 1;
        this.totalItems = 0;
        this.perPage = 20;
        this._searchTimeout = null;
        this._bind();
    }

    get _dialog() { return document.getElementById(this.dialogId); }
    get _searchInput() { return document.getElementById(`${this.dialogId}-search`); }
    get _mineToggle() { return document.getElementById(`${this.dialogId}-mine`); }
    get _resultsList() { return document.getElementById(`${this.dialogId}-results`); }
    get _pagination() { return document.getElementById(`${this.dialogId}-pagination`); }
    get _loadingEl() { return document.getElementById(`${this.dialogId}-loading`); }
    get _errorEl() { return document.getElementById(`${this.dialogId}-error`); }

    _bind() {
        const dlg = this._dialog;
        if (!dlg) return;

        this._searchInput?.addEventListener('sl-input', () => {
            clearTimeout(this._searchTimeout);
            this._searchTimeout = setTimeout(() => this._search(), 350);
        });

        this._mineToggle?.addEventListener('sl-change', () => this._search());

        dlg.addEventListener('sl-after-show', () => this._search());
    }

    open() {
        this._dialog?.show();
    }

    close() {
        this._dialog?.hide();
    }

    async _search(page = 1) {
        this.currentPage = page;
        const q = this._searchInput?.value?.trim() || '';
        const mine = this._mineToggle?.checked || false;
        const url = new URL(`/api/browse/${this.type}`, window.location.origin);
        url.searchParams.set('page', page);
        url.searchParams.set('per_page', this.perPage);
        if (q) url.searchParams.set('q', q);
        if (mine) url.searchParams.set('mine', 'true');

        this._setLoading(true);
        this._showError('');
        try {
            const resp = await fetch(url);
            if (!resp.ok) throw new Error('Failed to load results.');
            const data = await resp.json();
            this.totalItems = data.total;
            this._renderResults(data.items);
            this._renderPagination(data.total, data.page, data.per_page);
        } catch (err) {
            this._showError(err.message);
            this._renderResults([]);
        } finally {
            this._setLoading(false);
        }
    }

    _renderResults(items) {
        const list = this._resultsList;
        if (!list) return;
        list.innerHTML = '';

        if (items.length === 0) {
            list.innerHTML = '<p class="browse-empty">No results found.</p>';
            return;
        }

        items.forEach(item => {
            const row = document.createElement('div');
            row.className = 'browse-item';
            row.dataset.id = item.id;

            const privacyBadge = item.is_mine && !item.is_public
                ? '<sl-badge variant="warning" pill>Private</sl-badge>'
                : '<sl-badge variant="neutral" pill>Public</sl-badge>';
            const mine = item.is_mine ? '<sl-badge variant="primary" pill>Mine</sl-badge>' : '';

            if (this.type === 'waypoints') {
                row.innerHTML = `
                    <div class="browse-item-main">
                        <div class="browse-item-name">${escapeHtml(item.name)}</div>
                        <div class="browse-item-meta">
                            <span><i class="fas fa-user"></i> ${escapeHtml(item.owner_name)}</span>
                            <span><i class="fas fa-map-marker-alt"></i> ${item.waypoint_count} waypoints</span>
                            <span><i class="fas fa-calendar"></i> ${this._formatDate(item.created_at)}</span>
                        </div>
                        ${item.description ? `<div class="browse-item-desc">${escapeHtml(item.description)}</div>` : ''}
                    </div>
                    <div class="browse-item-badges">${privacyBadge}${mine}</div>
                    <sl-button size="small" variant="primary" class="browse-load-btn">Load</sl-button>
                `;
            } else {
                const dist = item.total_distance ? `${item.total_distance.toFixed(1)} km` : '—';
                row.innerHTML = `
                    <div class="browse-item-main">
                        <div class="browse-item-name">${escapeHtml(item.name)}</div>
                        <div class="browse-item-meta">
                            <span><i class="fas fa-user"></i> ${escapeHtml(item.owner_name)}</span>
                            <span><i class="fas fa-route"></i> ${dist}</span>
                            <span><i class="fas fa-map-pin"></i> ${item.turnpoint_count} turnpoints</span>
                            <span><i class="fas fa-calendar"></i> ${this._formatDate(item.created_at)}</span>
                        </div>
                        ${item.description ? `<div class="browse-item-desc">${escapeHtml(item.description)}</div>` : ''}
                    </div>
                    <div class="browse-item-badges">${privacyBadge}${mine}</div>
                    <sl-button size="small" variant="primary" class="browse-load-btn">Load</sl-button>
                `;
            }

            row.querySelector('.browse-load-btn').addEventListener('click', () => this._loadItem(item));
            list.appendChild(row);
        });
    }

    _renderPagination(total, page, perPage) {
        const el = this._pagination;
        if (!el) return;
        el.innerHTML = '';
        const totalPages = Math.ceil(total / perPage);
        if (totalPages <= 1) return;

        const prev = document.createElement('sl-button');
        prev.size = 'small';
        prev.textContent = '← Prev';
        prev.disabled = page <= 1;
        prev.addEventListener('click', () => this._search(page - 1));
        el.appendChild(prev);

        const info = document.createElement('span');
        info.className = 'browse-page-info';
        info.textContent = `${page} / ${totalPages}`;
        el.appendChild(info);

        const next = document.createElement('sl-button');
        next.size = 'small';
        next.textContent = 'Next →';
        next.disabled = page >= totalPages;
        next.addEventListener('click', () => this._search(page + 1));
        el.appendChild(next);
    }

    async _loadItem(item) {
        const confirmed = await window.showConfirmModal(
            this.type === 'waypoints'
                ? 'This will replace your current waypoints with the selected file. Continue?'
                : 'This will replace your current task. Continue?'
        );
        if (!confirmed) return;

        if (this.type === 'waypoints') {
            await this._loadWaypointFile(item.id);
        } else {
            await this._loadTask(item.id);
        }
        this.close();
    }

    async _loadWaypointFile(fileId) {
        try {
            const resp = await fetch(`/api/waypoints/files/${fileId}`);
            if (!resp.ok) throw new Error('Failed to load file.');
            const data = await resp.json();
            if (window.app) {
                window.app.waypoints = data.waypoints;
                window.app.updateUI(true);
                window.app.showStatus(`Loaded "${data.file.name}" — ${data.waypoints.length} waypoints.`, 'success');
            }
        } catch (err) {
            window.app?.showStatus('Error loading waypoint file: ' + err.message, 'error');
        }
    }

    async _loadTask(taskId) {
        try {
            const resp = await fetch(`/api/tasks/${taskId}`);
            if (!resp.ok) throw new Error('Failed to load task.');
            const data = await resp.json();
            const td = data.task_data || {};
            if (window.taskPlanner) {
                window.taskPlanner.loadTaskData(td);
                window.app?.showStatus(`Loaded task "${data.name}".`, 'success');
            }
        } catch (err) {
            window.app?.showStatus('Error loading task: ' + err.message, 'error');
        }
    }

    _setLoading(on) {
        const el = this._loadingEl;
        if (el) el.style.display = on ? '' : 'none';
        const list = this._resultsList;
        if (list && on) list.innerHTML = '';
    }

    _showError(msg) {
        const el = this._errorEl;
        if (!el) return;
        el.textContent = msg;
        el.style.display = msg ? '' : 'none';
    }

    _formatDate(iso) {
        if (!iso) return '';
        try {
            return new Date(iso).toLocaleDateString();
        } catch (_) {
            return iso;
        }
    }
}

// Initialise global instances after DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.waypointBrowser = new BrowseDialog('waypoints');
    window.taskBrowser = new BrowseDialog('tasks');
});
