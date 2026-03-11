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
                const countryBadges = item.country_codes
                    ? item.country_codes.split(',').slice(0, 5)
                          .map(c => `<sl-badge variant="neutral" pill>${escapeHtml(c.trim())}</sl-badge>`)
                          .join('')
                    : '';
                const minimap = this._renderWaypointMinimap(item.bbox);
                const bbox = item.bbox;
                const bboxStr = (bbox && bbox.min_lat != null)
                    ? `${bbox.min_lat.toFixed(2)}\u00b0\u2013${bbox.max_lat.toFixed(2)}\u00b0 N, ${bbox.min_lon.toFixed(2)}\u00b0\u2013${bbox.max_lon.toFixed(2)}\u00b0 E`
                    : '';
                const hasDetails = !!(bboxStr || item.description);
                row.innerHTML = `
                    ${minimap}
                    <div class="browse-item-main">
                        <div class="browse-item-name">${escapeHtml(item.name)}</div>
                        <div class="browse-item-meta">
                            <span><i class="fas fa-user"></i> ${escapeHtml(item.owner_name)}</span>
                            <span><i class="fas fa-map-marker-alt"></i> ${item.waypoint_count} waypoints</span>
                            <span><i class="fas fa-calendar"></i> ${this._formatDate(item.created_at)}</span>
                        </div>
                        ${countryBadges ? `<div class="browse-item-countries">${countryBadges}</div>` : ''}
                        ${item.description ? `<div class="browse-item-desc">${escapeHtml(item.description)}</div>` : ''}
                    </div>
                    <div class="browse-item-badges">${privacyBadge}${mine}</div>
                    ${hasDetails ? '<button class="browse-info-btn" title="Show details"><i class="fas fa-info-circle"></i></button>' : ''}
                    <sl-button size="small" variant="primary" class="browse-load-btn">Load</sl-button>
                    ${item.is_mine ? '<sl-button size="small" variant="danger" class="browse-delete-btn" title="Delete"><i class="fas fa-trash"></i></sl-button>' : ''}
                    ${hasDetails ? `<div class="browse-item-details" style="display:none">
                        ${bboxStr ? `<span class="browse-detail-item"><i class="fas fa-expand-arrows-alt"></i> ${escapeHtml(bboxStr)}</span>` : ''}
                        ${item.description ? `<span class="browse-detail-item browse-detail-desc">${escapeHtml(item.description)}</span>` : ''}
                    </div>` : ''}
                `;
            } else {
                const dist = item.total_distance ? `${item.total_distance.toFixed(1)} km` : '\u2014';
                const minimap = this._renderTaskMinimap(item.points);
                const pointsHtml = item.points.length
                    ? item.points.map((p, i) => `<li>${escapeHtml(p.name || '?')}</li>`).join('')
                    : '';
                row.innerHTML = `
                    ${minimap}
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
                    ${pointsHtml ? '<button class="browse-info-btn" title="Show waypoints"><i class="fas fa-info-circle"></i></button>' : ''}
                    <sl-button size="small" variant="primary" class="browse-load-btn">Load</sl-button>
                    ${item.is_mine ? '<sl-button size="small" variant="danger" class="browse-delete-btn" title="Delete"><i class="fas fa-trash"></i></sl-button>' : ''}
                    ${pointsHtml ? `<div class="browse-item-details" style="display:none"><ol class="browse-points-list">${pointsHtml}</ol></div>` : ''}
                `;
            }

            row.querySelector('.browse-load-btn').addEventListener('click', () => this._loadItem(item));
            row.querySelector('.browse-info-btn')?.addEventListener('click', (e) => {
                e.stopPropagation();
                const details = row.querySelector('.browse-item-details');
                if (details) {
                    const visible = details.style.display !== 'none';
                    details.style.display = visible ? 'none' : 'block';
                    e.currentTarget.classList.toggle('active', !visible);
                }
            });
            if (item.is_mine) {
                row.querySelector('.browse-delete-btn')?.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this._deleteItem(item);
                });
            }
            list.appendChild(row);
        });
    }

    _renderWaypointMinimap(bbox) {
        if (!bbox || bbox.min_lat == null || bbox.max_lat == null) return '';
        const W = 80, H = 55, pad = 4;
        // European context bounds — covers the main soaring areas
        const ctxMinLat = 30, ctxMaxLat = 72, ctxMinLon = -25, ctxMaxLon = 50;
        const latR = ctxMaxLat - ctxMinLat;
        const lonR = ctxMaxLon - ctxMinLon;
        const toX = lon => pad + (lon - ctxMinLon) / lonR * (W - 2 * pad);
        const toY = lat => (H - pad) - (lat - ctxMinLat) / latR * (H - 2 * pad);
        const x1 = Math.max(pad, toX(bbox.min_lon)).toFixed(1);
        const y1 = Math.max(pad, toY(bbox.max_lat)).toFixed(1);
        const x2 = Math.min(W - pad, toX(bbox.max_lon)).toFixed(1);
        const y2 = Math.min(H - pad, toY(bbox.min_lat)).toFixed(1);
        const rw = Math.max(3, x2 - x1).toFixed(1);
        const rh = Math.max(3, y2 - y1).toFixed(1);
        return `<svg class="browse-item-minimap" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">
            <rect x="0" y="0" width="${W}" height="${H}" rx="3" fill="#1e293b" stroke="none"/>
            <rect x="${x1}" y="${y1}" width="${rw}" height="${rh}"
                  fill="rgba(59,130,246,0.35)" stroke="#3b82f6" stroke-width="1.5" rx="1"/>
        </svg>`;
    }

    _renderTaskMinimap(points) {
        if (!points || points.length < 2) return '';
        const W = 80, H = 55, pad = 5;
        const lats = points.map(p => p.lat);
        const lons = points.map(p => p.lon);
        const minLat = Math.min(...lats), maxLat = Math.max(...lats);
        const minLon = Math.min(...lons), maxLon = Math.max(...lons);
        const latR = maxLat - minLat || 0.01;
        const lonR = maxLon - minLon || 0.01;
        const toX = lon => pad + (lon - minLon) / lonR * (W - 2 * pad);
        const toY = lat => (H - pad) - (lat - minLat) / latR * (H - 2 * pad);
        const pathD = points.map((p, i) =>
            `${i === 0 ? 'M' : 'L'}${toX(p.lon).toFixed(1)},${toY(p.lat).toFixed(1)}`
        ).join(' ');
        const dots = points.map((p, i) => {
            const x = toX(p.lon).toFixed(1), y = toY(p.lat).toFixed(1);
            const isEnd = i === 0 || i === points.length - 1;
            const title = p.name ? `<title>${escapeHtml(p.name)}</title>` : '';
            return `<circle cx="${x}" cy="${y}" r="${isEnd ? 3 : 2}" fill="${isEnd ? '#e63946' : '#3b82f6'}">${title}</circle>`;
        }).join('');
        return `<svg class="browse-item-minimap" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}"><path d="${pathD}" fill="none" stroke="#3b82f6" stroke-width="1.5" stroke-linejoin="round"/>${dots}</svg>`;
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

    async _deleteItem(item) {
        const label = this.type === 'waypoints' ? 'waypoint file' : 'task';
        const confirmed = await window.showConfirmModal(
            `Delete "${item.name}"? This cannot be undone.`
        );
        if (!confirmed) return;

        try {
            const url = this.type === 'waypoints'
                ? `/api/waypoints/files/${item.id}`
                : `/api/tasks/${item.id}`;
            const resp = await fetch(url, { method: 'DELETE' });
            if (!resp.ok && resp.status !== 204) throw new Error(`Failed to delete ${label}.`);
            this._search(this.currentPage);
        } catch (err) {
            window.app?.showStatus('Error: ' + err.message, 'error');
        }
    }

    async _loadItem(item) {
        const confirmed = await window.showConfirmModal(
            this.type === 'waypoints'
                ? (window.i18n?.t('confirm.replace_waypoints') ?? 'This will replace your current waypoints with the selected file. Continue?')
                : (window.i18n?.t('confirm.replace_task') ?? 'This will replace your current task. Continue?')
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
