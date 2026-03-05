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
        this.airspaces = [];        // Parsed airspace objects
        this.airspaceLayer = null;  // L.layerGroup for airspace polygons
        this.airspaceAltMin = 0;       // feet — altitude filter floor
        this.airspaceAltFilter = 10000; // feet — altitude filter ceiling
    }

    /** Called once when the Task tab is first shown */
    initMap() {
        if (this.initialized) {
            this.map.invalidateSize();
            setTimeout(() => this.fitTaskBounds(), 150);
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

        this.airspaceLayer = L.layerGroup().addTo(this.map);
        this.taskLayer = L.layerGroup().addTo(this.map);
        this.markerLayer = L.layerGroup().addTo(this.map);
        this.waypointLayer = L.layerGroup().addTo(this.map);

        this.initialized = true;

        // Wind indicator control
        this.createWindControl();

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
        document.getElementById('task-download-btn').addEventListener('click', () => {
            const menu = document.getElementById('task-download-menu');
            const expanded = menu.classList.toggle('show');
            document.getElementById('task-download-btn').setAttribute('aria-expanded', expanded);
        });
        document.addEventListener('click', (e) => {
            if (!document.getElementById('task-download-dropdown').contains(e.target)) {
                document.getElementById('task-download-menu').classList.remove('show');
                document.getElementById('task-download-btn').setAttribute('aria-expanded', 'false');
            }
        });
        document.getElementById('task-qr-btn').addEventListener('click', () => this.showQR());
        document.getElementById('task-share-btn').addEventListener('click', () => this.shareTask());
        document.getElementById('share-modal-close').addEventListener('click', () => {
            document.getElementById('share-modal').classList.remove('show');
        });
        document.getElementById('share-copy-btn').addEventListener('click', () => {
            const input = document.getElementById('share-url-input');
            navigator.clipboard.writeText(input.value).then(() => {
                const btn = document.getElementById('share-copy-btn');
                const orig = btn.innerHTML;
                btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
                btn.classList.replace('btn-primary', 'btn-success');
                setTimeout(() => {
                    btn.innerHTML = orig;
                    btn.classList.replace('btn-success', 'btn-primary');
                }, 2000);
            }).catch(() => {
                document.getElementById('share-url-input').select();
                document.execCommand('copy');
            });
        });
        document.getElementById('task-clear-btn').addEventListener('click', () => this.clearTask());

        // OZ modal
        document.getElementById('task-point-modal-close').addEventListener('click', () => this.hideOZModal());
        document.getElementById('oz-cancel-btn').addEventListener('click', () => this.hideOZModal());
        document.getElementById('oz-save-btn').addEventListener('click', () => this.saveOZ());
        document.getElementById('oz-preset').addEventListener('change', (e) => this.applyPreset(e.target.value));

        // OZ info popup
        document.getElementById('oz-info-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleOZInfoPopup();
        });
        document.getElementById('oz-info-close').addEventListener('click', () => this.hideOZInfoPopup());
        document.addEventListener('click', (e) => {
            const popup = document.getElementById('oz-info-popup');
            if (popup.style.display !== 'none' && !popup.contains(e.target) && e.target.id !== 'oz-info-btn') {
                this.hideOZInfoPopup();
            }
        });

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

        // Airspace file
        if (!window.VIEW_MODE) {
            document.getElementById('airspace-open-btn').addEventListener('click', () => {
                document.getElementById('airspace-file-input').click();
            });
            document.getElementById('airspace-file-input').addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    this.loadAirspaceFile(e.target.files[0]);
                    e.target.value = '';
                }
            });
            document.getElementById('airspace-clear-btn').addEventListener('click', () => {
                this.airspaces = [];
                if (this.airspaceLayer) this.airspaceLayer.clearLayers();
                document.getElementById('airspace-filter-panel').style.display = 'none';
                document.getElementById('airspace-clear-btn').style.display = 'none';
            });
            const updateAltSliders = () => {
                let minVal = parseInt(document.getElementById('airspace-alt-min-slider').value);
                let maxVal = parseInt(document.getElementById('airspace-alt-max-slider').value);
                if (minVal > maxVal) {
                    // Swap so min never exceeds max
                    document.getElementById('airspace-alt-min-slider').value = maxVal;
                    document.getElementById('airspace-alt-max-slider').value = minVal;
                    [minVal, maxVal] = [maxVal, minVal];
                }
                this.airspaceAltMin = minVal;
                this.airspaceAltFilter = maxVal;
                document.getElementById('airspace-alt-label').textContent =
                    this.formatAlt(minVal) + '\u2013' + this.formatAlt(maxVal);
                this._updateAltFill();
                this.renderAirspaces();
            };
            document.getElementById('airspace-alt-min-slider').addEventListener('input', updateAltSliders);
            document.getElementById('airspace-alt-max-slider').addEventListener('input', updateAltSliders);

            // XCSoar repository button
            document.getElementById('xcsoar-repo-btn').addEventListener('click', () => this.openRepoModal('airspace'));
            document.getElementById('xcsoar-repo-close').addEventListener('click', () => this.closeRepoModal());
            document.getElementById('xcsoar-repo-modal').addEventListener('click', (e) => {
                if (e.target.id === 'xcsoar-repo-modal') this.closeRepoModal();
            });
            document.getElementById('xcsoar-repo-type').addEventListener('change', () => this._filterRepoList());
            document.getElementById('xcsoar-repo-search').addEventListener('input', () => this._filterRepoList());
            const repoMapBtn = document.getElementById('xcsoar-repo-map-btn');
            if (repoMapBtn) repoMapBtn.addEventListener('click', () => this.openRepoModal('waypoint'));

            // Wind arrow live update
            ['task-wind-dir', 'task-wind-speed', 'task-tas'].forEach(id => {
                document.getElementById(id).addEventListener('input', () => {
                    this.updateWindArrow();
                    this.refreshUI();
                });
            });
        }

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
            setTimeout(() => this.fitTaskBounds(), 50);

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

    toggleOZInfoPopup() {
        const popup = document.getElementById('oz-info-popup');
        if (popup.style.display === 'none') {
            popup.style.display = 'flex';
        } else {
            popup.style.display = 'none';
        }
    }

    hideOZInfoPopup() {
        document.getElementById('oz-info-popup').style.display = 'none';
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
            case 'bga-fixed-course':
                r1.value = 20000; a1.value = 45; r2.value = 500; a2.value = 180; break;
            case 'bga-enhanced':
                r1.value = 10000; a1.value = 90; r2.value = 500; a2.value = 180; break;
            case 'start-line':
                r1.value = 5000; a1.value = 90; r2.value = 0; a2.value = 180; break;
            case 'finish-line':
                r1.value = 1000; a1.value = 90; r2.value = 0; a2.value = 180; break;
        }
    }

    guessPreset(oz) {
        if (oz.a1 === 180 && oz.r2 === 0) return 'cylinder';
        if (oz.a1 === 45 && oz.r2 === 500 && oz.r1 >= 2000 && oz.r1 <= 5000) return 'fai-sector';
        if (oz.a1 === 45 && oz.r2 === 500 && oz.r1 >= 8000 && oz.r1 <= 15000) return 'keyhole';
        if (oz.a1 === 45 && oz.r2 === 500 && oz.r1 > 15000) return 'bga-fixed-course';
        if (oz.a1 === 90 && oz.r2 === 500) return 'bga-enhanced';
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
        if (!window.VIEW_MODE) this.saveTaskState();
    }

    renderPointsList() {
        const viewMode = window.VIEW_MODE;
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
                    ${idx > 0 ? `<span class="task-point-dist">${this.legDistance(idx)} km${this.legTime(idx) ? ' · ' + this.legTime(idx) : ''}</span>` : ''}
                </div>
                ${viewMode ? '' : `<div class="task-point-actions">
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
                </div>`}
            </div>`;
        }).join('');
    }

    presetDisplayName(oz) {
        const p = this.guessPreset(oz);
        const names = {
            'cylinder': 'Cylinder',
            'fai-sector': 'FAI Sector',
            'keyhole': 'BGA Keyhole',
            'bga-fixed-course': 'BGA Fixed Course',
            'bga-enhanced': 'BGA Enhanced Option',
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
    }

    fitTaskBounds() {
        if (!this.initialized || this.taskPoints.length === 0) return;
        const latlngs = this.taskPoints.map(tp => [tp.waypoint.latitude, tp.waypoint.longitude]);
        const bounds = L.latLngBounds(latlngs);
        if (bounds.isValid()) {
            this.map.fitBounds(bounds.pad(0.2));
        }
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

    /** Bearing in radians from taskPoints[idx-1] to taskPoints[idx] */
    legBearingRad(idx) {
        const wp1 = this.taskPoints[idx - 1].waypoint;
        const wp2 = this.taskPoints[idx].waypoint;
        const lat1 = wp1.latitude  * Math.PI / 180;
        const lat2 = wp2.latitude  * Math.PI / 180;
        const dLng = (wp2.longitude - wp1.longitude) * Math.PI / 180;
        return Math.atan2(
            Math.sin(dLng) * Math.cos(lat2),
            Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng)
        );
    }

    /**
     * Estimated ground speed (kt) for leg idx using the headwind component method.
     * Returns null when TAS is not set.
     */
    legGroundSpeed(idx) {
        if (idx <= 0) return null;
        const tasEl = document.getElementById('task-tas');
        const tas = tasEl ? (parseFloat(tasEl.value) || 0) : 0;
        if (tas <= 0) return null;
        const wdEl = document.getElementById('task-wind-dir');
        const wsEl = document.getElementById('task-wind-speed');
        const wd = (wdEl ? (parseFloat(wdEl.value) || 0) : 0) * Math.PI / 180;
        const wsKt = wsEl ? (parseFloat(wsEl.value) || 0) : 0;
        const wsKmh = wsKt * 1.852;  // convert wind speed to km/h to match TAS
        // Headwind component: positive means headwind
        const bearing = this.legBearingRad(idx);
        const hw = wsKmh * Math.cos(bearing - wd);
        return Math.max(tas - hw, 1);  // clamp to 1 km/h to avoid division by zero
    }

    /** Formatted leg time string (e.g. "1h23m" or "45m") for leg idx, or null if TAS not set */
    legTime(idx) {
        if (idx <= 0) return null;
        const gs = this.legGroundSpeed(idx);
        if (!gs) return null;
        const distKm = this.distanceKm(this.taskPoints[idx - 1].waypoint, this.taskPoints[idx].waypoint);
        const totalMin = distKm / gs * 60;  // gs in km/h, dist in km
        const h = Math.floor(totalMin / 60);
        const m = Math.round(totalMin % 60);
        return h > 0 ? `${h}h${String(m).padStart(2, '0')}m` : `${m}m`;
    }

    /** Formatted total task time, or null if TAS not set */
    totalTime() {
        if (this.taskPoints.length < 2) return null;
        let totalMin = 0;
        for (let i = 1; i < this.taskPoints.length; i++) {
            const gs = this.legGroundSpeed(i);
            if (!gs) return null;
            totalMin += this.distanceKm(this.taskPoints[i - 1].waypoint, this.taskPoints[i].waypoint) / gs * 60;  // gs in km/h
        }
        const h = Math.floor(totalMin / 60);
        const m = Math.round(totalMin % 60);
        return h > 0 ? `${h}h${String(m).padStart(2, '0')}m` : `${m}m`;
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
        const t = this.totalTime();
        const timeRow = document.getElementById('task-total-time-row');
        if (timeRow) {
            timeRow.style.display = t ? '' : 'none';
            if (t) document.getElementById('task-total-time').textContent = t;
        }
    }

    updateButtons() {
        const has = this.taskPoints.length >= 2;
        document.getElementById('task-download-btn').disabled = !has;
        document.getElementById('task-qr-btn').disabled = !has;
        if (!window.VIEW_MODE) {
            document.getElementById('task-share-btn').disabled = !has;
        }
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

    async downloadTask(format = 'cup') {
        // Close dropdown
        document.getElementById('task-download-menu').classList.remove('show');
        document.getElementById('task-download-btn').setAttribute('aria-expanded', 'false');

        const payload = this.buildPayload();
        payload.format = format;
        const extMap = { cup: '.cup', tsk: '.tsk', xctsk: '.xctsk', lkt: '.lkt' };
        const ext = extMap[format] || '.cup';
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
            a.download = (payload.name.replace(/\s+/g, '_') || 'task') + ext;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (e) {
            alert('Download failed: ' + e.message);
        }
    }

    async shareTask() {
        const payload = this.buildPayload();
        try {
            const resp = await fetch('/api/task/share', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await resp.json();
            if (!data.success) {
                alert('Share failed: ' + (data.error || 'Unknown error'));
                return;
            }
            document.getElementById('share-url-input').value = data.url;
            document.getElementById('share-open-link').href = data.url;
            document.getElementById('share-modal').classList.add('show');
        } catch (e) {
            alert('Share failed: ' + e.message);
        }
    }

    // ──────────── XCTSK v2 polyline encoding ────────────

    /**
     * Encode a single signed integer using Google's polyline algorithm.
     * @see https://developers.google.com/maps/documentation/utilities/polylinealgorithm
     */
    _encodePolylineNum(num) {
        let pnum = num << 1;
        if (num < 0) pnum = ~pnum;
        let result = '';
        if (pnum === 0) {
            result = String.fromCharCode(63);
        } else {
            while (pnum > 0x1f) {
                result += String.fromCharCode(((pnum & 0x1f) | 0x20) + 63);
                pnum >>>= 5;
            }
            result += String.fromCharCode(63 + pnum);
        }
        return result;
    }

    /**
     * Encode turnpoint coordinates + altitude + radius into XCTSK "z" field.
     * Order: longitude, latitude, altitude (m), radius (m)
     * @see https://xctrack.org/Competition_Interfaces.html
     */
    _encodeXctskZ(lon, lat, alt, radius) {
        return this._encodePolylineNum(Math.round(lon * 1e5)) +
               this._encodePolylineNum(Math.round(lat * 1e5)) +
               this._encodePolylineNum(Math.round(alt)) +
               this._encodePolylineNum(Math.round(radius));
    }

    /**
     * Build XCTSK v2 JSON object from current task state.
     * @see https://xctrack.org/Competition_Interfaces.html#task-definition-format-2---for-qr-codes
     */
    buildXctskPayload() {
        const n = this.taskPoints.length;
        if (n < 2) return null;

        const turnpoints = this.taskPoints.map((tp, i) => {
            const wp = tp.waypoint;
            const oz = tp.obsZone || {};
            const radius = parseInt(oz.r1) || 500;   // lowercase field names from addPoint/saveOZ
            const alt = parseInt(wp.elevation) || 0;

            const point = {
                z: this._encodeXctskZ(wp.longitude, wp.latitude, alt, radius),
                n: wp.name || ''
            };

            // d: description/code — omit if empty to keep QR compact
            if (wp.code) point.d = wp.code;

            // t: 2 = SSS (start), 3 = ESS (finish/last point)
            if (i === 0) point.t = 2;
            if (i === n - 1) point.t = 3;

            // o: observation zone overrides (only non-default values)
            const ozOverrides = {};
            if (oz.isLine) {           // isLine field from addPoint/saveOZ
                ozOverrides.l = 1;
            }
            const a1 = parseInt(oz.a1); // lowercase a1
            if (a1 && a1 !== 180) {
                ozOverrides.a1 = a1;
            }
            if (Object.keys(ozOverrides).length > 0) {
                point.o = ozOverrides;
            }

            return point;
        });

        // Determine goal type from last point's OZ
        const lastOz = this.taskPoints[n - 1].obsZone || {};
        const goalIsLine = !!lastOz.isLine;

        const xctsk = {
            taskType: 'CLASSIC',
            version: 2,
            t: turnpoints,
            s: { g: [], d: 1, t: 1 },                          // start: RACE, ENTRY direction (legacy)
            g: { t: goalIsLine ? 1 : 2 }                       // goal: 1=LINE, 2=CYLINDER
        };

        // Add start time gate if set
        const noStart = document.getElementById('task-no-start').value;
        if (noStart) {
            xctsk.s.g = [noStart + ':00Z'];
        }

        return xctsk;
    }

    // ──────────── Export: QR code ────────────

    showQR() {
        const xctsk = this.buildXctskPayload();
        if (!xctsk) {
            alert('A task needs at least 2 points.');
            return;
        }

        const container = document.getElementById('task-qr-canvas');
        container.innerHTML = '<p style="text-align:center;padding:20px;">Generating QR code…</p>';
        document.getElementById('task-qr-modal').classList.add('show');

        const payload = {
            points: this.taskPoints.map(tp => ({
                waypointIndex: tp.waypointIndex,
                obsZone: tp.obsZone
            })),
            noStart: (document.getElementById('task-no-start').value || '') + ':00'
        };

        fetch('/api/task/xctsk-qr', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(r => r.json())
        .then(result => {
            container.innerHTML = '';
            if (!result.success) {
                container.innerHTML = `<p style="color:red;text-align:center;">QR generation failed: ${this.escapeHtml(result.error)}</p>`;
                return;
            }
            const img = document.createElement('img');
            img.src = result.dataUrl;
            img.style.cssText = 'display:block;margin:0 auto;max-width:360px;width:100%;';
            img.alt = 'XCTSK QR Code';
            container.appendChild(img);

            const infoP = document.createElement('p');
            infoP.style.cssText = 'text-align:center;margin-top:12px;font-size:0.85rem;color:#666;';
            infoP.textContent = `XCTSK task: ${this.taskPoints.length} points, ${this.totalDistance()} km`;
            container.appendChild(infoP);
        })
        .catch(e => {
            container.innerHTML = `<p style="color:red;text-align:center;">QR generation failed: ${this.escapeHtml(e.message)}</p>`;
        });
    }

    hideQRModal() {
        document.getElementById('task-qr-modal').classList.remove('show');
    }

    downloadQRImage() {
        const img = document.querySelector('#task-qr-canvas img');
        if (!img) return;
        const a = document.createElement('a');
        a.download = (document.getElementById('task-name').value || 'task') + '_qr.png';
        a.href = img.src;
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
        // View mode: load task from the share snapshot instead of the user session
        if (window.VIEW_MODE && window.VIEW_TOKEN) {
            try {
                const resp = await fetch(`/share/${encodeURIComponent(window.VIEW_TOKEN)}/taskdata`);
                const data = await resp.json();
                if (!data.success) return;

                // Inject waypoints into app so addPoint/renderMap can use them
                if (window.app) {
                    window.app.waypoints = data.waypoints;
                }

                // Restore task name
                if (data.task_name) document.getElementById('task-name').value = data.task_name;

                this.taskPoints = data.waypoints.map((wp, i) => ({
                    waypointIndex: i,
                    waypoint: wp,
                    obsZone: data.obs_zones[i] || { style: 1, r1: 3000, a1: 45, r2: 500, a2: 180, a12: 0, isLine: false, move: true, reduce: false, directionMode: 'auto', fixedBearing: null }
                }));

                if (this.taskPoints.length > 0) {
                    this.refreshUI();
                    setTimeout(() => this.fitTaskBounds(), 50);
                }
            } catch (e) {
                // Silently ignore
            }
            return;
        }

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
                setTimeout(() => this.fitTaskBounds(), 50);
            }
        } catch (e) {
            // Ignore load errors silently
        }
    }

    // ──────────── Airspace ────────────

    loadAirspaceFile(file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                this.airspaces = this.parseOpenAir(e.target.result);
                document.getElementById('airspace-file-name').textContent = file.name;
                document.getElementById('airspace-count').textContent = this.airspaces.length + ' zones';
                document.getElementById('airspace-filter-panel').style.display = '';
                document.getElementById('airspace-clear-btn').style.display = '';
                this._updateAltFill();
                this.renderAirspaces();
            } catch (err) {
                alert('Failed to parse airspace file: ' + err.message);
            }
        };
        reader.readAsText(file, 'UTF-8');
    }

    parseDMSPoint(str) {
        const m = str.match(/(\d+):(\d+):(\d+(?:\.\d+)?)\s*([NS])\s+(\d+):(\d+):(\d+(?:\.\d+)?)\s*([EW])/);
        if (!m) return null;
        const lat = (parseInt(m[1]) + parseInt(m[2]) / 60 + parseFloat(m[3]) / 3600) * (m[4] === 'S' ? -1 : 1);
        const lon = (parseInt(m[5]) + parseInt(m[6]) / 60 + parseFloat(m[7]) / 3600) * (m[8] === 'W' ? -1 : 1);
        return [lat, lon];
    }

    parseAltFt(str) {
        const s = str.trim().toUpperCase();
        if (s === 'GND' || s === 'SFC' || s === 'AGL' || s === 'MSL') return 0;
        const fl = s.match(/^FL\s*(\d+)/);
        if (fl) return parseInt(fl[1]) * 100;
        const ft = s.match(/^(\d+(?:\.\d+)?)\s*FT/);
        if (ft) return Math.round(parseFloat(ft[1]));
        const mt = s.match(/^(\d+(?:\.\d+)?)\s*M(?:\s|$)/);
        if (mt) return Math.round(parseFloat(mt[1]) * 3.281);
        return 0;
    }

    formatAlt(ft) {
        if (ft === 0) return 'GND';
        if (ft >= 1000 && ft % 100 === 0) return 'FL' + String(ft / 100).padStart(3, '0');
        return ft.toLocaleString() + ' ft';
    }

    parseOpenAir(text) {
        const airspaces = [];
        let cur = null;
        let cx = null;

        for (let raw of text.split('\n')) {
            const line = raw.trim();
            if (!line || line.startsWith('*')) continue;

            if (line.startsWith('AC ')) {
                if (cur) airspaces.push(cur);
                cur = { cls: line.slice(3).trim(), name: '', altLower: 0, altUpper: 99999, time: null, points: [], circles: [] };
                cx = null;
            } else if (!cur) {
                continue;
            } else if (line.startsWith('AN ')) {
                cur.name = line.slice(3).trim();
            } else if (line.startsWith('AL ')) {
                cur.altLower = this.parseAltFt(line.slice(3));
            } else if (line.startsWith('AH ')) {
                cur.altUpper = this.parseAltFt(line.slice(3));
            } else if (line.startsWith('AT ')) {
                cur.time = line.slice(3).trim();
            } else if (line.includes('X=')) {
                cx = this.parseDMSPoint(line.slice(line.indexOf('X=') + 2));
            } else if (line.startsWith('DP ')) {
                const ll = this.parseDMSPoint(line.slice(3));
                if (ll) cur.points.push(ll);
            } else if (line.startsWith('DC ')) {
                const r = parseFloat(line.slice(3));
                if (cx && !isNaN(r)) cur.circles.push({ center: cx, radius: r * 1852 });
            }
        }
        if (cur) airspaces.push(cur);
        return airspaces;
    }

    getAirspaceStyle(cls) {
        const c = (cls || '').trim().toUpperCase();
        if (c === 'R')                         return { color: '#dc2626', fillOpacity: 0.12 };
        if (c === 'P')                         return { color: '#7f1d1d', fillOpacity: 0.18 };
        if (c === 'D')                         return { color: '#ea580c', fillOpacity: 0.12 };
        if (c === 'CTR')                       return { color: '#7c3aed', fillOpacity: 0.10 };
        if (c.includes('RMZ'))                 return { color: '#0891b2', fillOpacity: 0.08 };
        if (c.includes('TMZ'))                 return { color: '#6b7280', fillOpacity: 0.06 };
        if (c === 'C' || c === 'B')            return { color: '#2563eb', fillOpacity: 0.10 };
        if (c === 'A')                         return { color: '#1e3a8a', fillOpacity: 0.14 };
        if (c === 'E')                         return { color: '#3b82f6', fillOpacity: 0.06 };
        if (c.includes('FIR'))                 return { color: '#94a3b8', fillOpacity: 0.03 };
        return                                        { color: '#64748b', fillOpacity: 0.05 };
    }

    _updateAltFill() {
        const fill = document.getElementById('airspace-alt-fill');
        if (!fill) return;
        const sliderMin = 0, sliderMax = 25000;
        const lo = (this.airspaceAltMin - sliderMin) / (sliderMax - sliderMin) * 100;
        const hi = (this.airspaceAltFilter - sliderMin) / (sliderMax - sliderMin) * 100;
        fill.style.left = lo + '%';
        fill.style.width = (hi - lo) + '%';
    }

    renderAirspaces() {
        if (!this.initialized || !this.airspaceLayer) return;
        this.airspaceLayer.clearLayers();
        if (this._airspaceMoveHandler) {
            this.map.off('mousemove', this._airspaceMoveHandler);
            this._airspaceMoveHandler = null;
        }
        const minAlt = this.airspaceAltMin;
        const maxAlt = this.airspaceAltFilter;

        // Create shared floating tooltip element (once)
        if (!this._airspaceTooltipEl) {
            this._airspaceTooltipEl = document.createElement('div');
            this._airspaceTooltipEl.className = 'airspace-multi-tooltip';
            this._airspaceTooltipEl.style.display = 'none';
            document.body.appendChild(this._airspaceTooltipEl);
        }
        const tooltipEl = this._airspaceTooltipEl;

        // Build flat list of {layer, as, s} for hit-testing
        const allLayers = [];

        for (const as of this.airspaces) {
            if (as.altUpper < minAlt || as.altLower > maxAlt) continue;
            const s = this.getAirspaceStyle(as.cls);
            const baseOpts = { color: s.color, weight: 1.5, opacity: 0.85, fillColor: s.color, fillOpacity: s.fillOpacity, interactive: false, bubblingMouseEvents: false };

            if (as.points.length >= 3) {
                const layer = L.polygon(as.points, { ...baseOpts }).addTo(this.airspaceLayer);
                allLayers.push({ layer, as, s });
            }
            for (const c of as.circles) {
                const layer = L.circle(c.center, { ...baseOpts, radius: c.radius }).addTo(this.airspaceLayer);
                allLayers.push({ layer, as, s });
            }
        }

        // Single map-level mousemove — hit-test every shape ourselves
        const prevHit = new Set();

        this._airspaceMoveHandler = (e) => {
            const pt = e.layerPoint;
            const nowHit = new Set();
            const hitAirspaces = [];

            for (const item of allLayers) {
                let inside = false;
                try { inside = item.layer._containsPoint(pt); } catch (_) {}
                if (!inside && item.layer instanceof L.Circle) {
                    inside = e.latlng.distanceTo(item.layer.getLatLng()) <= item.layer.getRadius();
                }

                if (inside) {
                    const id = L.stamp(item.layer);
                    nowHit.add(id);
                    hitAirspaces.push(item);
                    if (!prevHit.has(id)) {
                        item.layer.setStyle({ weight: 2.5, fillOpacity: Math.min(item.s.fillOpacity * 2.5, 0.5) });
                    }
                }
            }

            // Un-highlight shapes we just left
            for (const item of allLayers) {
                const id = L.stamp(item.layer);
                if (prevHit.has(id) && !nowHit.has(id)) {
                    item.layer.setStyle({ weight: 1.5, fillOpacity: item.s.fillOpacity });
                }
            }
            prevHit.clear();
            nowHit.forEach(id => prevHit.add(id));

            if (hitAirspaces.length === 0) {
                tooltipEl.style.display = 'none';
                return;
            }

            // Build tooltip content
            const parts = hitAirspaces.map(({ as }) => {
                let row = `<div class="astt-entry">`;
                row += `<div class="astt-name">${this.escapeHtml(as.name || as.cls)}</div>`;
                row += `<div class="astt-meta">Class&nbsp;<strong>${this.escapeHtml(as.cls)}</strong>`;
                row += `&emsp;${this.escapeHtml(this.formatAlt(as.altLower))}&thinsp;&ndash;&thinsp;${this.escapeHtml(this.formatAlt(as.altUpper))}</div>`;
                if (as.time) row += `<div class="astt-time"><i class="fas fa-clock"></i> ${this.escapeHtml(as.time)}</div>`;
                row += `</div>`;
                return row;
            });
            tooltipEl.innerHTML = parts.join('<hr class="astt-sep">');
            tooltipEl.style.display = '';

            const mx = e.originalEvent.clientX, my = e.originalEvent.clientY;
            const pad = 14;
            const tw = tooltipEl.offsetWidth || 220, th = tooltipEl.offsetHeight || 60;
            tooltipEl.style.left = (mx + pad + tw > window.innerWidth  ? mx - tw - pad : mx + pad) + 'px';
            tooltipEl.style.top  = (my + pad + th > window.innerHeight ? my - th - pad : my + pad) + 'px';
        };

        this.map.on('mousemove', this._airspaceMoveHandler);

        this.map.getContainer().addEventListener('mouseleave', () => {
            for (const item of allLayers) {
                item.layer.setStyle({ weight: 1.5, fillOpacity: item.s.fillOpacity });
            }
            prevHit.clear();
            tooltipEl.style.display = 'none';
        });
    }

    // ──────────── Wind control ────────────

    createWindControl() {
        const self = this;
        const WindControl = L.Control.extend({
            onAdd() {
                const div = L.DomUtil.create('div', 'wind-map-control');
                div.innerHTML = `
                    <div class="wmc-arrow" id="task-wind-arrow">
                        <svg viewBox="-12 -20 24 40" width="24" height="40">
                            <polygon points="0,-18 5,2 0,-3 -5,2" fill="#2563eb" stroke="white" stroke-width="1"/>
                            <line x1="-6" y1="12" x2="6" y2="12" stroke="#2563eb" stroke-width="1.5"/>
                            <line x1="-5" y1="16" x2="5" y2="16" stroke="#2563eb" stroke-width="1.5"/>
                            <line x1="-3" y1="20" x2="3" y2="20" stroke="#2563eb" stroke-width="1.5"/>
                        </svg>
                    </div>
                    <div class="wmc-label" id="task-wind-label">-- / --</div>`;
                L.DomEvent.disableClickPropagation(div);
                return div;
            },
            onRemove() {}
        });
        this._windControl = new WindControl({ position: 'topright' });
        this._windControl.addTo(this.map);
        this.updateWindArrow();
    }

    updateWindArrow() {
        const dirEl  = document.getElementById('task-wind-dir');
        const spdEl  = document.getElementById('task-wind-speed');
        const tasEl  = document.getElementById('task-tas');
        const arrEl  = document.getElementById('task-wind-arrow');
        const lblEl  = document.getElementById('task-wind-label');
        const dir    = dirEl  ? (parseInt(dirEl.value)  || 0) : 0;
        const speed  = spdEl  ? (parseInt(spdEl.value)  || 0) : 0;
        const tas    = tasEl  ? (parseInt(tasEl.value)   || 0) : 0;
        if (arrEl) arrEl.style.transform = `rotate(${(dir + 180) % 360}deg)`;
        const tasStr = tas > 0 ? `\u00a0TAS\u00a0${tas}` : '';
        if (lblEl) lblEl.textContent = `${dir}\u00b0\u00a0${speed}\u00a0kt${tasStr}`;
    }

    // ──────────── XCSoar Repository ────────────

    async openRepoModal(lockedType) {
        this._repoLockedType = lockedType || null;
        document.getElementById('xcsoar-repo-modal').classList.add('show');
        document.getElementById('xcsoar-repo-search').value = '';

        const typeSelect = document.getElementById('xcsoar-repo-type');
        if (lockedType) {
            typeSelect.value = lockedType;
            typeSelect.disabled = true;
        } else {
            typeSelect.value = '';
            typeSelect.disabled = false;
        }

        if (this._repoEntries) {
            this._filterRepoList();
            return;
        }

        const status = document.getElementById('xcsoar-repo-status');
        const list = document.getElementById('xcsoar-repo-list');
        status.textContent = 'Loading repository…';
        status.style.display = '';
        list.innerHTML = '';

        try {
            const resp = await fetch('/api/xcsoar-repo');
            const data = await resp.json();
            if (data.error) throw new Error(data.error);
            this._repoEntries = data.entries;
            status.style.display = 'none';
            this._filterRepoList();
        } catch (e) {
            status.textContent = 'Failed to load repository: ' + e.message;
        }
    }

    closeRepoModal() {
        document.getElementById('xcsoar-repo-modal').classList.remove('show');
    }

    _filterRepoList() {
        const typeFilter = this._repoLockedType || document.getElementById('xcsoar-repo-type').value;
        const search = document.getElementById('xcsoar-repo-search').value.toLowerCase().trim();
        const entries = this._repoEntries || [];
        const filtered = entries.filter(e => {
            if (typeFilter && e.type !== typeFilter) return false;
            if (search) {
                const hay = ((e.area || '') + ' ' + (e.name || '') + ' ' + (e.description || '')).toLowerCase();
                if (!hay.includes(search)) return false;
            }
            return true;
        });
        this._renderRepoList(filtered);
    }

    _renderRepoList(entries) {
        const list = document.getElementById('xcsoar-repo-list');
        if (!entries.length) {
            list.innerHTML = '<div class="xcsoar-repo-empty">No entries found.</div>';
            return;
        }
        list.innerHTML = entries.map((e, i) => {
            const typeBadge = e.type === 'waypoint'
                ? '<span class="xcsoar-badge xcsoar-badge-wp">WPT</span>'
                : '<span class="xcsoar-badge xcsoar-badge-as">ASP</span>';
            const area = e.area ? `<strong>${e.area.toUpperCase()}</strong> · ` : '';
            const desc = this.escapeHtml(e.description || e.name || '');
            const update = e.update ? ` <span class="xcsoar-repo-date">${e.update}</span>` : '';
            return `<div class="xcsoar-repo-item">
                <div class="xcsoar-repo-item-info">
                    ${typeBadge}
                    <span class="xcsoar-repo-item-name">${area}${desc}${update}</span>
                </div>
                <button class="btn btn-sm btn-primary xcsoar-load-btn" data-idx="${i}">
                    <i class="fas fa-download"></i> Load
                </button>
            </div>`;
        }).join('');

        list.querySelectorAll('.xcsoar-load-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const filtered = this._currentFilteredEntries || entries;
                const entry = entries[parseInt(btn.dataset.idx)];
                await this._loadRepoEntry(entry, btn);
            });
        });
        this._currentFilteredEntries = entries;
    }

    async _loadRepoEntry(entry, btn) {
        const origHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        try {
            const proxyUrl = '/api/xcsoar-proxy?url=' + encodeURIComponent(entry.uri);
            const resp = await fetch(proxyUrl);
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.error || resp.statusText);
            }

            if (entry.type === 'waypoint') {
                const blob = await resp.blob();
                const fname = (entry.uri.split('/').pop() || 'wpt.cup');
                const file = new File([blob], fname, { type: 'text/plain' });
                const formData = new FormData();
                formData.append('file', file);
                const uploadResp = await fetch('/api/upload', { method: 'POST', body: formData });
                const result = await uploadResp.json();
                if (!result.success) throw new Error(result.error || 'Upload failed');
                if (window.app) {
                    window.app.waypoints = result.waypoints;
                    window.app.updateUI();
                }
                this.closeRepoModal();
                alert(`Loaded ${result.waypoints.length} waypoints from ${entry.name || entry.area}`);
            } else if (entry.type === 'airspace') {
                const text = await resp.text();
                const fname = (entry.uri.split('/').pop() || 'airspace.txt');
                const file = new File([text], fname, { type: 'text/plain' });
                this.loadAirspaceFile(file);
                this.closeRepoModal();
            }
        } catch (e) {
            alert('Load failed: ' + e.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = origHtml;
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
