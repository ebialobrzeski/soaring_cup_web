/**
 * Task Planner module for SeeYou/XCSoar/LK8000 compatible task creation.
 *
 * Observation Zone (ObsZone) reference:
 *   Style:  0=Fixed, 1=Symmetrical, 2=To next, 3=To prev, 4=To start
 *   R1   :  Outer radius (metres)
 *   A1   :  Half-angle of outer sector (180 = full cylinder)
 *   R2   :  Inner radius
 *   A2   :  Half-angle of inner sector
 *   Line :  1 = treat as line
 *
 * Common presets:
 *   Cylinder      : R1=any, A1=180, R2=0
 *   FAI Sector    : R1=3000, A1=45, R2=500, A2=180
 *   BGA Keyhole   : R1=10000, A1=45, R2=500, A2=180
 *   Start Line    : R1=half-width, A1=90, Line=1
 *   Finish Line   : R1=half-width, A1=90, Line=1
 */

class TaskPlanner {
    constructor() {
        this.taskPoints = [];   // [{waypointIndex, waypoint, obsZone}]
        this.map = null;
        this.taskLayer = null;  // L.layerGroup for task lines/zones
        this.markerLayer = null;
        this.editIndex = -1;    // Index of task point currently being edited
        this.initialized = false;
        this.bearingEditIndex = -1; // Task point index being bearing-edited
        this._onBearingMove = null; // Bound mousemove handler ref
        this._onBearingClick = null; // Bound click handler ref
    }

    /** Called once when the Task tab is first shown */
    initMap() {
        if (this.initialized) {
            this.map.invalidateSize();
            return;
        }

        this.map = L.map('task-map', {
            preferCanvas: true,
            zoomControl: true
        }).setView([52.0, 19.0], 6);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap',
            maxZoom: 18
        }).addTo(this.map);

        this.taskLayer = L.layerGroup().addTo(this.map);
        this.markerLayer = L.layerGroup().addTo(this.map);
        this.waypointLayer = L.layerGroup().addTo(this.map);

        this.initialized = true;

        // Show loaded waypoints immediately
        this.renderWaypointMarkers();

        // Restore saved task state
        this.loadTaskState();
    }

    /** Setup all event listeners — called from SoaringCupEditor.initializeApp */
    setup() {
        // Search
        const searchInput = document.getElementById('task-wp-search');
        searchInput.addEventListener('input', () => this.onSearch(searchInput.value));
        searchInput.addEventListener('focus', () => this.onSearch(searchInput.value));
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#task-wp-search') && !e.target.closest('#task-wp-results')) {
                document.getElementById('task-wp-results').innerHTML = '';
            }
        });

        // Buttons
        document.getElementById('task-download-btn').addEventListener('click', () => this.downloadTask());
        document.getElementById('task-qr-btn').addEventListener('click', () => this.showQR());
        document.getElementById('task-clear-btn').addEventListener('click', () => this.clearTask());

        // OZ modal
        document.getElementById('task-point-modal-close').addEventListener('click', () => this.hideOZModal());
        document.getElementById('oz-cancel-btn').addEventListener('click', () => this.hideOZModal());
        document.getElementById('oz-save-btn').addEventListener('click', () => this.saveOZ());
        document.getElementById('oz-preset').addEventListener('change', (e) => this.applyPreset(e.target.value));

        // Direction mode toggle in OZ modal
        document.getElementById('oz-direction-mode').addEventListener('change', (e) => {
            document.getElementById('oz-bearing').disabled = (e.target.value === 'auto');
        });

        // Open task file
        document.getElementById('task-open-btn').addEventListener('click', () => {
            document.getElementById('task-file-input').click();
        });
        document.getElementById('task-file-input').addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.importTask(e.target.files[0]);
                e.target.value = ''; // Reset so same file can be re-selected
            }
        });

        // QR modal
        document.getElementById('task-qr-close').addEventListener('click', () => this.hideQRModal());
        document.getElementById('task-qr-download-img').addEventListener('click', () => this.downloadQRImage());
        document.getElementById('task-qr-download-cup').addEventListener('click', () => this.downloadTask());

        document.getElementById('task-qr-modal').addEventListener('click', (e) => {
            if (e.target.id === 'task-qr-modal') this.hideQRModal();
        });
        document.getElementById('task-point-modal').addEventListener('click', (e) => {
            if (e.target.id === 'task-point-modal') this.hideOZModal();
        });
    }

    // ──────────── Waypoint search ────────────

    onSearch(query) {
        const results = document.getElementById('task-wp-results');
        if (!query || query.length < 1) {
            results.innerHTML = '';
            return;
        }

        const waypoints = window.app ? window.app.waypoints : [];
        const q = query.toLowerCase();
        const matches = [];
        for (let i = 0; i < waypoints.length && matches.length < 20; i++) {
            const wp = waypoints[i];
            if (wp.name.toLowerCase().includes(q) || (wp.code && wp.code.toLowerCase().includes(q))) {
                matches.push({ index: i, wp });
            }
        }

        if (matches.length === 0) {
            results.innerHTML = '<div class="task-wp-no-result">No matching waypoints</div>';
            return;
        }

        results.innerHTML = matches.map(m =>
            `<div class="task-wp-item" data-index="${m.index}">
                <strong>${this.escapeHtml(m.wp.name)}</strong>
                <span class="task-wp-meta">${this.escapeHtml(m.wp.code || '')} ${m.wp.elevation ? m.wp.elevation + 'm' : ''}</span>
            </div>`
        ).join('');

        results.querySelectorAll('.task-wp-item').forEach(el => {
            el.addEventListener('click', () => {
                const idx = parseInt(el.dataset.index);
                this.addPoint(idx);
                document.getElementById('task-wp-search').value = '';
                results.innerHTML = '';
            });
        });
    }

    // ──────────── Task points CRUD ────────────

    addPoint(waypointIndex) {
        const waypoints = window.app ? window.app.waypoints : [];
        const wp = waypoints[waypointIndex];
        if (!wp) return;

        const isFirst = this.taskPoints.length === 0;
        // Default OZ based on position
        let obsZone;
        if (isFirst) {
            // Start: line 5km half-width
            obsZone = { style: 0, r1: 5000, a1: 90, r2: 0, a2: 180, a12: 0, isLine: true, move: true, reduce: false, directionMode: 'auto', fixedBearing: null };
        } else {
            // Turn point: FAI sector
            obsZone = { style: 1, r1: 3000, a1: 45, r2: 500, a2: 180, a12: 0, isLine: false, move: true, reduce: false, directionMode: 'auto', fixedBearing: null };
        }

        this.taskPoints.push({ waypointIndex, waypoint: wp, obsZone });
        this.refreshUI();
    }

    removePoint(taskIdx) {
        this.taskPoints.splice(taskIdx, 1);
        this.refreshUI();
    }

    movePoint(taskIdx, direction) {
        const newIdx = taskIdx + direction;
        if (newIdx < 0 || newIdx >= this.taskPoints.length) return;
        const tmp = this.taskPoints[taskIdx];
        this.taskPoints[taskIdx] = this.taskPoints[newIdx];
        this.taskPoints[newIdx] = tmp;
        this.refreshUI();
    }

    clearTask() {
        if (this.taskPoints.length > 0 && !confirm('Clear all task points?')) return;
        this.taskPoints = [];
        this.refreshUI();
    }

    // ──────────── Task file import ────────────

    async importTask(file) {
        const formData = new FormData();
        formData.append('file', file);

        try {
            const resp = await fetch('/api/task/import', {
                method: 'POST',
                body: formData
            });
            const result = await resp.json();
            if (!result.success) {
                alert('Import failed: ' + (result.error || 'Unknown error'));
                return;
            }

            // Clear current task
            this.taskPoints = [];

            // Set task name and options
            if (result.task_name) {
                document.getElementById('task-name').value = result.task_name;
            }
            if (result.options) {
                if (result.options.noStart) {
                    // Convert "HH:MM:SS" to "HH:MM" for time input
                    const parts = result.options.noStart.split(':');
                    document.getElementById('task-no-start').value = parts.slice(0, 2).join(':');
                }
                if (result.options.taskTime) {
                    document.getElementById('task-time').value = result.options.taskTime;
                }
            }

            const waypoints = window.app ? window.app.waypoints : [];
            const unmatched = [];

            for (const pt of result.points) {
                let wpIdx = pt.waypointIndex;
                let wp = wpIdx >= 0 ? waypoints[wpIdx] : null;

                if (!wp && pt.fileWaypoint) {
                    // Waypoint not in session — use data from the file
                    wp = pt.fileWaypoint;
                    // Add it to the session waypoints so it gets an index
                    waypoints.push(wp);
                    wpIdx = waypoints.length - 1;
                    if (window.app) {
                        window.app.waypoints = waypoints;
                    }
                }

                if (!wp) {
                    unmatched.push(pt.waypointName);
                    continue;
                }

                this.taskPoints.push({
                    waypointIndex: wpIdx,
                    waypoint: wp,
                    obsZone: pt.obsZone
                });
            }

            this.refreshUI();

            if (unmatched.length > 0) {
                alert('Some waypoints could not be matched:\n' + unmatched.join('\n') +
                    '\n\nLoad a waypoint file containing these points and re-import the task.');
            }
        } catch (e) {
            alert('Import failed: ' + e.message);
        }
    }

    // ──────────── OZ edit modal ────────────

    showOZModal(taskIdx) {
        this.editIndex = taskIdx;
        const tp = this.taskPoints[taskIdx];
        const oz = tp.obsZone;

        document.getElementById('task-point-modal-title').textContent =
            `Edit OZ: ${tp.waypoint.name} (${this.pointLabel(taskIdx)})`;

        document.getElementById('oz-r1').value = oz.r1;
        document.getElementById('oz-a1').value = oz.a1;
        document.getElementById('oz-r2').value = oz.r2;
        document.getElementById('oz-a2').value = oz.a2;

        // Direction fields
        const hasFixed = oz.directionMode === 'fixed';
        document.getElementById('oz-direction-mode').value = hasFixed ? 'fixed' : 'auto';
        document.getElementById('oz-bearing').disabled = !hasFixed;
        document.getElementById('oz-bearing').value = oz.fixedBearing != null ? Math.round(oz.fixedBearing) : 0;

        // Guess preset
        document.getElementById('oz-preset').value = this.guessPreset(oz);

        document.getElementById('task-point-modal').classList.add('show');
    }

    hideOZModal() {
        document.getElementById('task-point-modal').classList.remove('show');
        this.editIndex = -1;
    }

    saveOZ() {
        if (this.editIndex < 0) return;
        const oz = this.taskPoints[this.editIndex].obsZone;
        oz.r1 = parseInt(document.getElementById('oz-r1').value) || 500;
        oz.a1 = parseInt(document.getElementById('oz-a1').value) || 180;
        oz.r2 = parseInt(document.getElementById('oz-r2').value) || 0;
        oz.a2 = parseInt(document.getElementById('oz-a2').value) || 180;
        oz.isLine = (oz.a1 === 90 && oz.r2 === 0);

        // Direction
        const mode = document.getElementById('oz-direction-mode').value;
        oz.directionMode = mode;
        if (mode === 'fixed') {
            oz.fixedBearing = parseFloat(document.getElementById('oz-bearing').value) || 0;
        } else {
            oz.fixedBearing = null;
        }

        this.hideOZModal();
        this.refreshUI();
    }

    applyPreset(preset) {
        const r1 = document.getElementById('oz-r1');
        const a1 = document.getElementById('oz-a1');
        const r2 = document.getElementById('oz-r2');
        const a2 = document.getElementById('oz-a2');
        switch (preset) {
            case 'cylinder':
                r1.value = 500; a1.value = 180; r2.value = 0; a2.value = 180; break;
            case 'fai-sector':
                r1.value = 3000; a1.value = 45; r2.value = 500; a2.value = 180; break;
            case 'keyhole':
                r1.value = 10000; a1.value = 45; r2.value = 500; a2.value = 180; break;
            case 'start-line':
                r1.value = 5000; a1.value = 90; r2.value = 0; a2.value = 180; break;
            case 'finish-line':
                r1.value = 1000; a1.value = 90; r2.value = 0; a2.value = 180; break;
        }
    }

    guessPreset(oz) {
        if (oz.a1 === 180 && oz.r2 === 0) return 'cylinder';
        if (oz.a1 === 45 && oz.r2 === 500 && oz.r1 >= 2000 && oz.r1 <= 5000) return 'fai-sector';
        if (oz.a1 === 45 && oz.r2 === 500 && oz.r1 >= 8000) return 'keyhole';
        if (oz.a1 === 90 && oz.r2 === 0 && oz.r1 >= 3000) return 'start-line';
        if (oz.a1 === 90 && oz.r2 === 0 && oz.r1 <= 2000) return 'finish-line';
        return 'custom';
    }

    pointLabel(idx) {
        if (idx === 0) return 'Start';
        if (idx === this.taskPoints.length - 1) return 'Finish';
        return `TP${idx}`;
    }

    // ──────────── UI rendering ────────────

    refreshUI() {
        this.renderPointsList();
        try {
            this.renderTaskMap();
        } catch (e) {
            console.warn('Task map render error:', e);
        }
        this.updateSummary();
        this.updateButtons();
        this.saveTaskState();
    }

    renderPointsList() {
        const container = document.getElementById('task-points-list');
        if (this.taskPoints.length === 0) {
            container.innerHTML = '<p class="task-empty-msg">No task points added. Search and add waypoints above.</p>';
            return;
        }

        container.innerHTML = this.taskPoints.map((tp, idx) => {
            const label = this.pointLabel(idx);
            const presetName = this.presetDisplayName(tp.obsZone);
            return `<div class="task-point-card" data-idx="${idx}">
                <div class="task-point-header">
                    <span class="task-point-label">${label}</span>
                    <span class="task-point-name">${this.escapeHtml(tp.waypoint.name)}</span>
                </div>
                <div class="task-point-info">
                    <span class="task-point-oz">${presetName} · R1=${tp.obsZone.r1}m</span>
                    ${idx > 0 ? `<span class="task-point-dist">${this.legDistance(idx)} km</span>` : ''}
                </div>
                <div class="task-point-actions">
                    <button class="btn btn-sm btn-secondary" title="Move up" onclick="window.taskPlanner.movePoint(${idx},-1)" ${idx === 0 ? 'disabled' : ''}>
                        <i class="fas fa-arrow-up"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary" title="Move down" onclick="window.taskPlanner.movePoint(${idx},1)" ${idx === this.taskPoints.length - 1 ? 'disabled' : ''}>
                        <i class="fas fa-arrow-down"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary" title="Edit zone" onclick="window.taskPlanner.showOZModal(${idx})">
                        <i class="fas fa-cog"></i>
                    </button>
                    <button class="btn btn-sm btn-danger" title="Remove" onclick="window.taskPlanner.removePoint(${idx})">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>`;
        }).join('');
    }

    presetDisplayName(oz) {
        const p = this.guessPreset(oz);
        const names = {
            'cylinder': 'Cylinder',
            'fai-sector': 'FAI Sector',
            'keyhole': 'BGA Keyhole',
            'start-line': 'Start Line',
            'finish-line': 'Finish Line',
            'custom': 'Custom'
        };
        return names[p] || 'Custom';
    }

    // ──────────── Map drawing ────────────

    renderTaskMap() {
        if (!this.initialized) return;
        this.taskLayer.clearLayers();
        this.markerLayer.clearLayers();

        // Always show loaded waypoints as background markers
        this.renderWaypointMarkers();

        if (this.taskPoints.length === 0) return;

        const coords = this.taskPoints.map(tp => [tp.waypoint.latitude, tp.waypoint.longitude]);

        // Draw task legs as polyline
        if (coords.length > 1) {
            L.polyline(coords, {
                color: '#2563eb',
                weight: 3,
                opacity: 0.8,
                dashArray: '10 6'
            }).addTo(this.taskLayer);
        }

        // Draw each observation zone and marker
        this.taskPoints.forEach((tp, idx) => {
            const latlng = [tp.waypoint.latitude, tp.waypoint.longitude];

            // Draw observation zone
            this.drawObsZone(latlng, tp.obsZone, idx);

            // Marker
            const marker = L.circleMarker(latlng, {
                radius: 8,
                fillColor: idx === 0 ? '#059669' : (idx === this.taskPoints.length - 1 ? '#dc2626' : '#2563eb'),
                color: '#fff',
                weight: 2,
                opacity: 1,
                fillOpacity: 0.9
            }).addTo(this.markerLayer);

            marker.bindTooltip(
                `<strong>${this.pointLabel(idx)}</strong><br>${this.escapeHtml(tp.waypoint.name)}`,
                { permanent: true, direction: 'top', offset: [0, -10], className: 'task-tooltip' }
            );

            // Click on task point marker → popup with edit/delete/bearing actions
            marker.on('click', () => this.showTaskPointPopup(latlng, idx));
        });

        // Fit bounds
        const group = L.featureGroup([this.taskLayer, this.markerLayer]);
        this.map.fitBounds(group.getBounds().pad(0.15));
    }

    renderWaypointMarkers() {
        this.waypointLayer.clearLayers();
        const waypoints = window.app ? window.app.waypoints : [];
        if (waypoints.length === 0) return;

        // Build set of indices already in the task — skip these so task markers get clicks
        const inTask = new Set(this.taskPoints.map(tp => tp.waypointIndex));

        for (let i = 0; i < waypoints.length; i++) {
            const wp = waypoints[i];
            if (wp.latitude == null || wp.longitude == null) continue;
            if (inTask.has(i)) continue; // task markers handle these positions

            const iconSize = 18;
            const icon = createWaypointIcon(wp.style || 1, iconSize);
            const marker = L.marker([wp.latitude, wp.longitude], {
                icon: icon,
                opacity: 0.7
            }).addTo(this.waypointLayer);

            marker.bindTooltip(this.escapeHtml(wp.name), {
                direction: 'top',
                offset: [0, -iconSize / 2],
                className: 'task-tooltip'
            });

            // Click to add as task point
            const idx = i;
            marker.on('click', () => {
                this.addPoint(idx);
            });
        }
    }

    /** Show a popup on a task-point marker with Edit OZ / Set Bearing / Remove actions */
    showTaskPointPopup(latlng, taskIdx) {
        const tp = this.taskPoints[taskIdx];
        const label = this.pointLabel(taskIdx);
        const bearingInfo = tp.obsZone.directionMode === 'fixed'
            ? `Fixed: ${Math.round(tp.obsZone.fixedBearing)}°`
            : 'Auto';

        const popup = L.popup({ closeButton: true, className: 'task-point-popup', offset: [0, -10] })
            .setLatLng(latlng)
            .setContent(`
                <div class="task-popup-content">
                    <strong>${label}: ${this.escapeHtml(tp.waypoint.name)}</strong>
                    <div class="task-popup-bearing-info">Bearing: ${bearingInfo}</div>
                    <div class="task-popup-actions">
                        <button class="btn btn-sm btn-secondary" onclick="window.taskPlanner.startBearingEdit(${taskIdx}); window.taskPlanner.map.closePopup();">
                            <i class="fas fa-sync-alt"></i> Change Bearing
                        </button>
                        <button class="btn btn-sm btn-secondary" onclick="window.taskPlanner.resetBearing(${taskIdx}); window.taskPlanner.map.closePopup();">
                            <i class="fas fa-undo"></i> Auto
                        </button>
                    </div>
                    <div class="task-popup-actions" style="margin-top:4px;">
                        <button class="btn btn-sm btn-secondary" onclick="window.taskPlanner.showOZModal(${taskIdx}); window.taskPlanner.map.closePopup();">
                            <i class="fas fa-cog"></i> Edit OZ
                        </button>
                        <button class="btn btn-sm btn-primary" onclick="window.taskPlanner.addPoint(${tp.waypointIndex}); window.taskPlanner.map.closePopup();">
                            <i class="fas fa-plus"></i> Add Again
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="window.taskPlanner.removePoint(${taskIdx}); window.taskPlanner.map.closePopup();">
                            <i class="fas fa-times"></i> Remove
                        </button>
                    </div>
                </div>
            `)
            .openOn(this.map);
    }

    /** Enter interactive bearing-edit mode: mouse movement rotates the sector */
    startBearingEdit(taskIdx) {
        // Cancel any previous bearing edit
        if (this.bearingEditIndex >= 0) this.stopBearingEdit(false);

        this.bearingEditIndex = taskIdx;
        const tp = this.taskPoints[taskIdx];
        const center = L.latLng(tp.waypoint.latitude, tp.waypoint.longitude);

        // Show instructional banner
        this._showBearingBanner();

        // Change cursor
        this.map.getContainer().style.cursor = 'crosshair';

        // On mouse move: compute bearing from point to cursor, update live
        this._onBearingMove = (e) => {
            const angle = this._latlngBearing(center, e.latlng);
            tp.obsZone.directionMode = 'fixed';
            tp.obsZone.fixedBearing = angle;
            // Redraw only the task layer (fast)
            this.taskLayer.clearLayers();
            this.markerLayer.clearLayers();
            const coords = this.taskPoints.map(p => [p.waypoint.latitude, p.waypoint.longitude]);
            if (coords.length > 1) {
                L.polyline(coords, { color: '#2563eb', weight: 3, opacity: 0.8, dashArray: '10 6' }).addTo(this.taskLayer);
            }
            this.taskPoints.forEach((p, i) => {
                const ll = [p.waypoint.latitude, p.waypoint.longitude];
                this.drawObsZone(ll, p.obsZone, i);
                const m = L.circleMarker(ll, {
                    radius: 8,
                    fillColor: i === 0 ? '#059669' : (i === this.taskPoints.length - 1 ? '#dc2626' : '#2563eb'),
                    color: '#fff', weight: 2, opacity: 1, fillOpacity: 0.9
                }).addTo(this.markerLayer);
                m.bindTooltip(`<strong>${this.pointLabel(i)}</strong><br>${this.escapeHtml(p.waypoint.name)}`,
                    { permanent: true, direction: 'top', offset: [0, -10], className: 'task-tooltip' });
            });
            // Update banner with current angle
            const banner = document.getElementById('bearing-edit-banner');
            if (banner) banner.querySelector('.bearing-value').textContent = `${Math.round(angle)}°`;
        };

        // On click: confirm bearing
        this._onBearingClick = (e) => {
            L.DomEvent.stopPropagation(e);
            this.stopBearingEdit(true);
        };

        this.map.on('mousemove', this._onBearingMove);
        this.map.on('click', this._onBearingClick);
    }

    /** Stop bearing edit, optionally keeping the current value */
    stopBearingEdit(confirm) {
        if (this.bearingEditIndex < 0) return;
        if (!confirm) {
            // Revert to auto
            const oz = this.taskPoints[this.bearingEditIndex].obsZone;
            oz.directionMode = 'auto';
            oz.fixedBearing = null;
        }
        this.bearingEditIndex = -1;
        this.map.off('mousemove', this._onBearingMove);
        this.map.off('click', this._onBearingClick);
        this._onBearingMove = null;
        this._onBearingClick = null;
        this.map.getContainer().style.cursor = '';
        this._hideBearingBanner();
        this.refreshUI();
    }

    /** Reset bearing to auto for a task point */
    resetBearing(taskIdx) {
        const oz = this.taskPoints[taskIdx].obsZone;
        oz.directionMode = 'auto';
        oz.fixedBearing = null;
        this.refreshUI();
    }

    /** Bearing from latlng1 to latlng2 in degrees */
    _latlngBearing(ll1, ll2) {
        const lat1 = ll1.lat * Math.PI / 180;
        const lat2 = ll2.lat * Math.PI / 180;
        const dLng = (ll2.lng - ll1.lng) * Math.PI / 180;
        const y = Math.sin(dLng) * Math.cos(lat2);
        const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);
        return ((Math.atan2(y, x) * 180 / Math.PI) + 360) % 360;
    }

    _showBearingBanner() {
        let banner = document.getElementById('bearing-edit-banner');
        if (!banner) {
            banner = document.createElement('div');
            banner.id = 'bearing-edit-banner';
            banner.className = 'bearing-edit-banner';
            banner.innerHTML = `
                <i class="fas fa-sync-alt"></i>
                Move mouse to set bearing: <span class="bearing-value">0°</span>
                &mdash; click to confirm, <a href="#" id="bearing-edit-cancel">Esc to cancel</a>
            `;
            document.querySelector('.task-map-area').appendChild(banner);
            banner.querySelector('#bearing-edit-cancel').addEventListener('click', (e) => {
                e.preventDefault();
                this.stopBearingEdit(false);
            });
            // Esc key to cancel
            this._onBearingEsc = (e) => {
                if (e.key === 'Escape') this.stopBearingEdit(false);
            };
            document.addEventListener('keydown', this._onBearingEsc);
        }
        banner.style.display = 'flex';
    }

    _hideBearingBanner() {
        const banner = document.getElementById('bearing-edit-banner');
        if (banner) banner.style.display = 'none';
        if (this._onBearingEsc) {
            document.removeEventListener('keydown', this._onBearingEsc);
            this._onBearingEsc = null;
        }
    }

    drawObsZone(center, oz, idx) {
        const r1 = oz.r1;
        const a1 = oz.a1;
        const r2 = oz.r2 || 0;
        const a2 = oz.a2 || 180;

        // Determine bearing for sector orientation
        let bearing = 0;
        if (oz.directionMode === 'fixed' && oz.fixedBearing != null) {
            bearing = oz.fixedBearing;
        } else if (this.taskPoints.length > 1) {
            if (idx === 0) {
                // Start: oriented towards TP1
                bearing = this.bearing(
                    this.taskPoints[0].waypoint,
                    this.taskPoints[1].waypoint
                );
            } else if (idx === this.taskPoints.length - 1) {
                // Finish: oriented from previous TP
                bearing = this.bearing(
                    this.taskPoints[idx - 1].waypoint,
                    this.taskPoints[idx].waypoint
                );
            } else {
                // Turn point: bisector of incoming and outgoing legs
                const inBearing = this.bearing(
                    this.taskPoints[idx - 1].waypoint,
                    this.taskPoints[idx].waypoint
                );
                const outBearing = this.bearing(
                    this.taskPoints[idx].waypoint,
                    this.taskPoints[idx + 1].waypoint
                );
                // Bisector points away from legs (180° rotated)
                bearing = this.bisectorBearing(inBearing, outBearing);
            }
        }

        const color = idx === 0 ? '#059669' : (idx === this.taskPoints.length - 1 ? '#dc2626' : '#2563eb');

        if (a1 === 180) {
            // Full cylinder
            L.circle(center, { radius: r1, color, weight: 2, opacity: 0.6, fillColor: color, fillOpacity: 0.08, dashArray: '5 5' })
                .addTo(this.taskLayer);
        } else {
            // Sector: draw arc from (bearing - a1) to (bearing + a1)
            this.drawSector(center, r1, bearing, a1, color).addTo(this.taskLayer);
        }

        // Inner radius (if > 0)
        if (r2 > 0 && a2 > 0) {
            if (a2 === 180) {
                L.circle(center, { radius: r2, color, weight: 1.5, opacity: 0.5, fillColor: color, fillOpacity: 0.05, dashArray: '3 3' })
                    .addTo(this.taskLayer);
            } else {
                this.drawSector(center, r2, bearing, a2, color).addTo(this.taskLayer);
            }
        }
    }

    drawSector(center, radius, bearing, halfAngle, color) {
        const startAngle = bearing - halfAngle;
        const endAngle = bearing + halfAngle;
        const points = [center];
        const steps = Math.max(24, Math.ceil(halfAngle / 3));

        for (let i = 0; i <= steps; i++) {
            const angle = startAngle + (endAngle - startAngle) * (i / steps);
            points.push(this.destPoint(center, radius, angle));
        }
        points.push(center);

        return L.polygon(points, {
            color,
            weight: 2,
            opacity: 0.6,
            fillColor: color,
            fillOpacity: 0.08,
            dashArray: '5 5'
        });
    }

    /** Compute destination point given start [lat,lng], distance in m, and bearing in degrees */
    destPoint(center, distMeters, bearingDeg) {
        const R = 6371000;
        const lat1 = center[0] * Math.PI / 180;
        const lng1 = center[1] * Math.PI / 180;
        const brng = bearingDeg * Math.PI / 180;
        const d = distMeters / R;

        const lat2 = Math.asin(Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(brng));
        const lng2 = lng1 + Math.atan2(
            Math.sin(brng) * Math.sin(d) * Math.cos(lat1),
            Math.cos(d) - Math.sin(lat1) * Math.sin(lat2)
        );
        return [lat2 * 180 / Math.PI, lng2 * 180 / Math.PI];
    }

    /** Bearing from wp1 to wp2 in degrees */
    bearing(wp1, wp2) {
        const lat1 = wp1.latitude * Math.PI / 180;
        const lat2 = wp2.latitude * Math.PI / 180;
        const dLng = (wp2.longitude - wp1.longitude) * Math.PI / 180;
        const y = Math.sin(dLng) * Math.cos(lat2);
        const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);
        return ((Math.atan2(y, x) * 180 / Math.PI) + 360) % 360;
    }

    /** Bisector bearing: sector opens on the OUTSIDE of the turn (XCSoar convention) */
    bisectorBearing(inBearing, outBearing) {
        // Average of arrival bearing and reversed departure bearing
        // This produces the bisector that points outward from the task polygon
        const revOut = (outBearing + 180) % 360;
        let diff = revOut - inBearing;
        if (diff > 180) diff -= 360;
        if (diff < -180) diff += 360;
        return (inBearing + diff / 2 + 360) % 360;
    }

    // ──────────── Distance calc ────────────

    /** Haversine distance between two waypoints in km */
    distanceKm(wp1, wp2) {
        const R = 6371;
        const dLat = (wp2.latitude - wp1.latitude) * Math.PI / 180;
        const dLng = (wp2.longitude - wp1.longitude) * Math.PI / 180;
        const a = Math.sin(dLat / 2) ** 2 +
            Math.cos(wp1.latitude * Math.PI / 180) * Math.cos(wp2.latitude * Math.PI / 180) *
            Math.sin(dLng / 2) ** 2;
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    legDistance(idx) {
        if (idx <= 0) return '0.0';
        return this.distanceKm(this.taskPoints[idx - 1].waypoint, this.taskPoints[idx].waypoint).toFixed(1);
    }

    totalDistance() {
        let total = 0;
        for (let i = 1; i < this.taskPoints.length; i++) {
            total += this.distanceKm(this.taskPoints[i - 1].waypoint, this.taskPoints[i].waypoint);
        }
        return total.toFixed(1);
    }

    updateSummary() {
        const summary = document.getElementById('task-summary');
        if (this.taskPoints.length < 2) {
            summary.style.display = 'none';
            return;
        }
        summary.style.display = 'block';
        document.getElementById('task-total-distance').textContent = this.totalDistance() + ' km';
        document.getElementById('task-leg-count').textContent = this.taskPoints.length - 1;
    }

    updateButtons() {
        const has = this.taskPoints.length >= 2;
        document.getElementById('task-download-btn').disabled = !has;
        document.getElementById('task-qr-btn').disabled = !has;
    }

    // ──────────── Build task payload ────────────

    buildPayload() {
        return {
            name: document.getElementById('task-name').value || 'Task',
            points: this.taskPoints.map(tp => ({
                waypointIndex: tp.waypointIndex,
                obsZone: tp.obsZone
            })),
            options: {
                noStart: document.getElementById('task-no-start').value + ':00',
                taskTime: document.getElementById('task-time').value
            }
        };
    }

    // ──────────── Export: download ────────────

    async downloadTask() {
        const payload = this.buildPayload();
        try {
            const resp = await fetch('/api/task/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!resp.ok) {
                const err = await resp.json();
                alert('Export failed: ' + (err.error || 'Unknown error'));
                return;
            }
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = (payload.name.replace(/\s+/g, '_') || 'task') + '.cup';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (e) {
            alert('Download failed: ' + e.message);
        }
    }

    // ──────────── Export: QR code ────────────

    async showQR() {
        if (typeof QRCode === 'undefined') {
            alert('QR code library failed to load. Please check your internet connection and reload the page.');
            return;
        }
        const payload = this.buildPayload();
        try {
            const resp = await fetch('/api/task/qr', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await resp.json();
            if (!result.success) {
                alert('Export failed: ' + (result.error || 'Unknown error'));
                return;
            }

            // Build a download URL from the token
            const downloadUrl = `${window.location.origin}/dl/${result.token}`;

            const canvas = document.getElementById('task-qr-canvas');
            canvas.innerHTML = '';

            const qrDiv = document.createElement('div');
            canvas.appendChild(qrDiv);
            new QRCode(qrDiv, {
                text: downloadUrl,
                width: 360,
                height: 360,
                correctLevel: QRCode.CorrectLevel.M
            });

            // Show the download link below the QR
            const linkP = document.createElement('p');
            linkP.style.cssText = 'text-align:center;margin-top:12px;word-break:break-all;font-size:0.85rem;';
            linkP.innerHTML = `<a href="${this.escapeHtml(downloadUrl)}" target="_blank">${this.escapeHtml(downloadUrl)}</a>`;
            canvas.appendChild(linkP);

            document.getElementById('task-qr-modal').classList.add('show');
        } catch (e) {
            alert('Export failed: ' + e.message);
        }
    }

    hideQRModal() {
        document.getElementById('task-qr-modal').classList.remove('show');
    }

    downloadQRImage() {
        const canvas = document.querySelector('#task-qr-canvas canvas');
        if (!canvas) return;
        const a = document.createElement('a');
        a.download = (document.getElementById('task-name').value || 'task') + '_qr.png';
        a.href = canvas.toDataURL('image/png');
        a.click();
    }

    // ──────────── Session persistence ────────────

    saveTaskState() {
        const data = {
            name: document.getElementById('task-name').value,
            noStart: document.getElementById('task-no-start').value,
            taskTime: document.getElementById('task-time').value,
            points: this.taskPoints.map(tp => ({
                waypointIndex: tp.waypointIndex,
                obsZone: tp.obsZone
            }))
        };
        fetch('/api/task/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        }).catch(() => {}); // Fire-and-forget
    }

    async loadTaskState() {
        try {
            const resp = await fetch('/api/task/load');
            const result = await resp.json();
            if (!result.success || !result.task || !result.task.points || result.task.points.length === 0) return;

            const saved = result.task;
            const waypoints = window.app ? window.app.waypoints : [];

            // Restore task name and options
            if (saved.name) document.getElementById('task-name').value = saved.name;
            if (saved.noStart) document.getElementById('task-no-start').value = saved.noStart;
            if (saved.taskTime) document.getElementById('task-time').value = saved.taskTime;

            // Restore task points
            this.taskPoints = [];
            for (const pt of saved.points) {
                const idx = pt.waypointIndex;
                const wp = (idx >= 0 && idx < waypoints.length) ? waypoints[idx] : null;
                if (!wp) continue;
                this.taskPoints.push({
                    waypointIndex: idx,
                    waypoint: wp,
                    obsZone: pt.obsZone || { style: 1, r1: 3000, a1: 45, r2: 500, a2: 180, a12: 0, isLine: false, move: true, reduce: false, directionMode: 'auto', fixedBearing: null }
                });
            }

            if (this.taskPoints.length > 0) {
                this.refreshUI();
            }
        } catch (e) {
            // Ignore load errors silently
        }
    }

    // ──────────── Helpers ────────────

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Global instance 
window.taskPlanner = new TaskPlanner();
