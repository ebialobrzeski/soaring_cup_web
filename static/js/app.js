// GlidePlan - Web Application JavaScript

class SoaringCupEditor {
    constructor() {
        this.waypoints = [];
        this.selectedWaypoints = new Set();
        this.currentEditIndex = -1;
        this.map = null;
        this.mapMarkers = {};
        this.markerClusterGroup = null;
        this.sortColumn = null;
        this.sortDirection = 'asc';
        
        // Performance optimization settings
        this.maxMarkersOnMap = 2000; // Limit markers for performance
        this.tablePageSize = 100; // Virtual scrolling page size
        this.currentTablePage = 0;
        this.visibleWaypoints = []; // Currently displayed waypoints
        this.updateTimeout = null; // Debounce timeout for smooth updates
        
        this.initializeApp();
    }

    initializeApp() {
        this.setupEventListeners();
        this.setupThemeToggle();
        this.initializeMap();
        if (!window.VIEW_MODE) {
            this.loadWaypoints(); // Not needed in view mode — task data comes from share token
        }
        this.updateUI();
        
        // Since map tab is now default, ensure map renders properly
        setTimeout(() => {
            this.map.invalidateSize();
        }, 100);
        
        // Handle window resize to adjust map
        this.setupResizeHandler();

        // Setup task planner listeners
        if (window.taskPlanner) {
            window.taskPlanner.setup();
        }

        // Initialise AI planner panel visibility based on auth state
        this._updateAiPlannerPanel();

        // View mode: task tab is already active via the `active` attribute in HTML
        // — do NOT call switchTab('task') as it causes Shoelace to briefly hide/re-show
        //   the panel, which makes Leaflet lose its container dimensions (blank map).
        if (window.VIEW_MODE) {
            const nameInput = document.getElementById('task-name');
            if (nameInput) nameInput.readOnly = true;
            // Init task map after Shoelace has fully upgraded the tab group.
            // Use a shorter initial delay, then force additional invalidateSize calls
            // so Leaflet always recalculates after the panel CSS transition finishes.
            setTimeout(() => {
                if (window.taskPlanner) {
                    window.taskPlanner.initMap();
                    setTimeout(() => window.taskPlanner?.map?.invalidateSize(true), 200);
                    setTimeout(() => window.taskPlanner?.map?.invalidateSize(true), 500);
                }
            }, 300);
        }
    }

    setupEventListeners() {
        // File operations (not present in view mode)
        if (!window.VIEW_MODE) {
            document.getElementById('file-upload').addEventListener('change', (e) => this.handleFileUpload(e));
            document.getElementById('open-file-btn').addEventListener('click', () => document.getElementById('file-upload').click());
            document.getElementById('new-btn').addEventListener('click', () => this.newFile());
            document.getElementById('save-cup-btn').addEventListener('click', () => this.downloadFile('cup'));

            // Account save/browse
            document.getElementById('save-to-account-btn')?.addEventListener('click', () => this.showSaveWaypointsDialog());
            document.getElementById('browse-waypoints-btn')?.addEventListener('click', () => window.waypointBrowser?.open());
        }

        // Tab navigation (Shoelace tab group)
        document.getElementById('main-tabs').addEventListener('sl-tab-show', (e) => {
            const panel = e.detail.name;
            if (panel === 'map') {
                setTimeout(() => this.map.invalidateSize(), 100);
            }
            if (panel === 'task') {
                // Show overlay when no waypoints are loaded (editor mode only)
                if (!window.VIEW_MODE) {
                    const hasWaypoints = this.waypoints && this.waypoints.length > 0;
                    const overlay = document.getElementById('task-no-waypoints-overlay');
                    if (overlay) overlay.style.display = hasWaypoints ? 'none' : 'flex';
                }
                if (window.taskPlanner) {
                    setTimeout(() => {
                        window.taskPlanner.initMap();
                        // Extra invalidation after Shoelace panel CSS transition completes (~300ms)
                        setTimeout(() => window.taskPlanner?.map?.invalidateSize(true), 350);
                    }, 100);
                }
            }
            if (panel === 'ai-planner') {
                this._updateAiPlannerPanel();
            }
        });

        // "Go to Map View" button inside task planner no-waypoints overlay
        document.getElementById('task-go-to-map-btn')?.addEventListener('click', () => {
            document.getElementById('main-tabs')?.show('map');
        });

        // Map controls (present in both modes)
        document.getElementById('fit-bounds-btn').addEventListener('click', () => this.fitMapBounds());
        document.getElementById('add-waypoint-map-btn').addEventListener('click', () => this.addWaypointOnMap());
        document.getElementById('show-legend-btn').addEventListener('click', () => this.showLegendModal());

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => this.handleKeyboardShortcuts(e));

        if (!window.VIEW_MODE) {
            // Waypoint operations
            document.getElementById('add-waypoint-btn').addEventListener('click', () => this.showWaypointModal());
            document.getElementById('edit-waypoint-btn').addEventListener('click', () => this.editSelectedWaypoint());
            document.getElementById('delete-waypoint-btn').addEventListener('click', () => this.deleteSelectedWaypoints());

            // Table interactions
            document.getElementById('select-all').addEventListener('change', (e) => this.toggleSelectAll(e.target.checked));

            // Table sorting
            document.querySelectorAll('[data-sort]').forEach(th => {
                th.addEventListener('click', () => this.sortTable(th.dataset.sort));
            });

            // Waypoint modal (sl-dialog)
            document.getElementById('cancel-btn').addEventListener('click', () => this.hideWaypointModal());
            document.getElementById('waypoint-form').addEventListener('submit', (e) => this.handleWaypointSubmit(e));
            document.getElementById('fetch-elevation-btn').addEventListener('click', () => this.fetchElevation());
            document.getElementById('paste-coords-btn').addEventListener('click', () => this.pasteCoordinates());

            // Save waypoints dialog
            document.getElementById('save-wf-cancel')?.addEventListener('click', () => document.getElementById('save-waypoints-dialog').hide());
            document.getElementById('save-wf-submit')?.addEventListener('click', () => this.handleSaveWaypointsSubmit());

            // My files dialog
            // (populated on open)

            // AI Planner CTA buttons
            document.getElementById('ai-login-btn')?.addEventListener('click', () => window.authManager?.showLoginDialog());
            document.getElementById('ai-signup-btn')?.addEventListener('click', () => window.authManager?.showRegisterDialog());
            document.getElementById('ai-upgrade-btn')?.addEventListener('click', () => window.authManager?.showLoginDialog());
        }

        // React to auth state changes
        document.addEventListener('auth-changed', () => {
            this._updateAiPlannerPanel();
        });
    }

    setupThemeToggle() {
        const toggle = document.getElementById('theme-toggle');
        const saved = localStorage.getItem('glideplan-theme');
        // Default to dark mode unless user has explicitly chosen light
        const preferDark = saved !== 'light';
        if (preferDark) {
            document.documentElement.classList.add('sl-theme-dark');
            toggle.name = 'sun';
        }
        toggle.addEventListener('click', () => {
            const isDark = document.documentElement.classList.toggle('sl-theme-dark');
            toggle.name = isDark ? 'sun' : 'moon';
            localStorage.setItem('glideplan-theme', isDark ? 'dark' : 'light');
        });
    }

    setupResizeHandler() {
        // Debounce resize events to avoid performance issues
        let resizeTimeout;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(() => {
                // Only invalidate size if map tab is active
                const mapTab = document.getElementById('map-tab');
                if (mapTab && mapTab.classList.contains('active')) {
                    this.map.invalidateSize();
                }
            }, 250); // 250ms debounce
        });
    }

    initializeMap() {
        this.map = L.map('map', {
            preferCanvas: true,          // Use canvas renderer for better performance
            zoomAnimation: true,         // Keep zoom animations smooth
            fadeAnimation: true,         // Keep fade animations
            markerZoomAnimation: false   // Disable marker zoom animations to reduce jumpiness
        }).setView([50.0, 10.0], 6);
        
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            updateWhenIdle: true,        // Only update tiles when map stops moving
            updateWhenZooming: false,    // Don't update during zoom for smoother experience
            keepBuffer: 2                // Keep more tiles in memory for smoother panning
        }).addTo(this.map);

        // Initialize marker cluster group with custom options for performance
        this.markerClusterGroup = L.markerClusterGroup({
            maxClusterRadius: 30,
            disableClusteringAtZoom: 13, // Keep clustering until zoom 13 to reduce individual marker count
            spiderfyOnMaxZoom: true,
            showCoverageOnHover: false,
            zoomToBoundsOnClick: true,
            removeOutsideVisibleBounds: true, // Only render markers inside the visible viewport
            animate: false,
            animateAddingMarkers: false,
            singleMarkerMode: false,
            spiderfyDistanceMultiplier: 1,
            chunkedLoading: true,        // Load markers in chunks to avoid blocking the UI thread
            chunkInterval: 100,
            chunkDelay: 50,
            maxZoom: 18
        });
        
        this.map.addLayer(this.markerClusterGroup);

        // Add click handler for adding waypoints on map
        this.map.on('click', (e) => {
            if (this.map.getContainer().classList.contains('adding-waypoint')) {
                this.addWaypointAtLocation(e.latlng.lat, e.latlng.lng);
                this.map.getContainer().classList.remove('adding-waypoint');
                document.getElementById('add-waypoint-map-btn').innerHTML = '<i class="fas fa-map-pin" slot="prefix"></i> Add Waypoint on Map';
            }
        });
    }

    async loadWaypoints() {
        try {
            const response = await fetch('/api/waypoints');
            if (response.ok) {
                this.waypoints = await response.json();
                this.updateUI(true); // Fit bounds on initial load
            }
        } catch (error) {
            this.showStatus('Error loading waypoints: ' + error.message, 'error');
        }
    }

    async handleFileUpload(event) {
        const file = event.target.files[0];
        if (!file) return;

        this.showLoading(true);
        
        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            
            if (result.success) {
                this.waypoints = result.waypoints;
                this.updateUI(true); // Fit bounds after file upload
                this.showStatus(result.message, 'success');
            } else {
                this.showStatus('Error: ' + result.error, 'error');
            }
        } catch (error) {
            this.showStatus('Upload failed: ' + error.message, 'error');
        } finally {
            this.showLoading(false);
            event.target.value = ''; // Reset file input
        }
    }

    async newFile() {
        if (this.waypoints.length > 0) {
            const confirmed = await window.showConfirmModal(window.i18n?.t('confirm.clear_waypoints') ?? 'This will clear all current waypoints. Continue?');
            if (!confirmed) return;
        }

        try {
            const response = await fetch('/api/clear', { method: 'POST' });
            if (response.ok) {
                this.waypoints = [];
                this.selectedWaypoints.clear();
                this.updateUI();
                this.showStatus('New file created', 'success');
            }
        } catch (error) {
            this.showStatus('Error creating new file: ' + error.message, 'error');
        }
    }

    async downloadFile(format) {
        if (this.waypoints.length === 0) {
            this.showStatus('No waypoints to download', 'error');
            return;
        }

        try {
            const response = await fetch('/api/download/cup');
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'waypoints.cup';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                this.showStatus(`Downloaded ${this.waypoints.length} waypoints as CUP`, 'success');
            } else {
                const error = await response.json();
                this.showStatus('Download failed: ' + error.error, 'error');
            }
        } catch (error) {
            this.showStatus('Download failed: ' + error.message, 'error');
        }
    }

    showWaypointModal(waypoint = null, index = -1) {
        this.currentEditIndex = index;
        const modal = document.getElementById('waypoint-modal');
        const form = document.getElementById('waypoint-form');

        modal.label = waypoint
            ? window.i18n.t('wp.edit_title', 'Edit Waypoint')
            : window.i18n.t('wp.add_title', 'Add Waypoint');
        
        // Reset form and switch to first tab
        form.reset();
        this.switchModalTab('basic');
        
        // Populate form if editing
        if (waypoint) {
            document.getElementById('wp-name').value = waypoint.name || '';
            document.getElementById('wp-code').value = waypoint.code || '';
            document.getElementById('wp-country').value = waypoint.country || '';
            document.getElementById('wp-latitude').value = waypoint.latitude || '';
            document.getElementById('wp-longitude').value = waypoint.longitude || '';
            document.getElementById('wp-style').value = waypoint.style || 1;
            document.getElementById('wp-runway-direction').value = waypoint.runway_direction || '';
            document.getElementById('wp-frequency').value = waypoint.frequency || '';
            document.getElementById('wp-description').value = waypoint.description || '';
            
            // Handle elevation - backend returns int, so just display the value
            if (waypoint.elevation) {
                document.getElementById('wp-elevation-value').value = waypoint.elevation;
                document.getElementById('wp-elevation-unit').value = 'm';
            }
            
            // Handle runway length - backend returns int, so just display the value
            if (waypoint.runway_length) {
                document.getElementById('wp-runway-length-value').value = waypoint.runway_length;
                document.getElementById('wp-runway-length-unit').value = 'm';
            }
            
            // Handle runway width - backend returns int, so just display the value
            if (waypoint.runway_width) {
                document.getElementById('wp-runway-width-value').value = waypoint.runway_width;
                document.getElementById('wp-runway-width-unit').value = 'm';
            }
        }

        modal.show();
        setTimeout(() => document.getElementById('wp-name').focus(), 100);
    }

    hideWaypointModal() {
        document.getElementById('waypoint-modal').hide();
        this.currentEditIndex = -1;
    }

    showLegendModal() {
        const modal = document.getElementById('legend-modal');
        const legendItems = document.getElementById('legend-items');
        
        // Clear existing content
        legendItems.innerHTML = '';
        
        // Create legend items for each waypoint type
        Object.keys(WAYPOINT_ICONS).forEach(style => {
            const config = WAYPOINT_ICONS[style];
            const item = document.createElement('div');
            item.className = 'legend-item';
            item.innerHTML = `
                <div class="legend-icon">
                    <div style="
                        width: 20px; 
                        height: 20px; 
                        background-image: url('${config.icon}'); 
                        background-size: contain; 
                        background-repeat: no-repeat; 
                        background-position: center;
                        display: inline-block;
                        vertical-align: middle;
                    "></div>
                </div>
                <div class="legend-label">
                    <strong>${style}:</strong> ${config.name}
                </div>
            `;
            legendItems.appendChild(item);
        });
        
        modal.show();
    }

    hideLegendModal() {
        document.getElementById('legend-modal').hide();
    }

    async handleWaypointSubmit(event) {
        event.preventDefault();
        
        const formData = new FormData(event.target);
        const waypointData = {};
        
        // Handle basic fields
        waypointData.name = formData.get('name').trim();
        waypointData.code = formData.get('code').trim();
        waypointData.country = formData.get('country').trim();
        waypointData.latitude = parseFloat(formData.get('latitude'));
        waypointData.longitude = parseFloat(formData.get('longitude'));
        waypointData.style = parseInt(formData.get('style'));
        waypointData.runway_direction = formData.get('runway_direction').trim();
        waypointData.frequency = formData.get('frequency').trim();
        waypointData.description = formData.get('description').trim();
        
        // Handle elevation with unit
        const elevValue = formData.get('elevation_value');
        const elevUnit = formData.get('elevation_unit');
        if (elevValue && elevValue.trim()) {
            waypointData.elevation = `${elevValue.trim()}${elevUnit}`;
        } else {
            waypointData.elevation = '';
        }
        
        // Handle runway length with unit
        const rwLenValue = formData.get('runway_length_value');
        const rwLenUnit = formData.get('runway_length_unit');
        if (rwLenValue && rwLenValue.trim()) {
            waypointData.runway_length = `${rwLenValue.trim()}${rwLenUnit}`;
        } else {
            waypointData.runway_length = '';
        }
        
        // Handle runway width with unit
        const rwWidthValue = formData.get('runway_width_value');
        const rwWidthUnit = formData.get('runway_width_unit');
        if (rwWidthValue && rwWidthValue.trim()) {
            waypointData.runway_width = `${rwWidthValue.trim()}${rwWidthUnit}`;
        } else {
            waypointData.runway_width = '';
        }

        try {
            let response;
            if (this.currentEditIndex >= 0) {
                // Update existing waypoint
                response = await fetch(`/api/waypoints/${this.currentEditIndex}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(waypointData)
                });
            } else {
                // Add new waypoint
                response = await fetch('/api/waypoints', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(waypointData)
                });
            }

            const result = await response.json();
            
            if (result.success) {
                await this.loadWaypoints(); // Reload to get updated data
                this.hideWaypointModal();
                this.showStatus(
                    this.currentEditIndex >= 0 ? 'Waypoint updated' : 'Waypoint added', 
                    'success'
                );
            } else {
                this.showStatus('Error: ' + result.error, 'error');
            }
        } catch (error) {
            this.showStatus('Save failed: ' + error.message, 'error');
        }
    }

    editSelectedWaypoint() {
        if (this.selectedWaypoints.size !== 1) {
            this.showStatus('Please select exactly one waypoint to edit', 'error');
            return;
        }

        const index = Array.from(this.selectedWaypoints)[0];
        const waypoint = this.waypoints[index];
        this.showWaypointModal(waypoint, index);
    }

    async deleteSelectedWaypoints() {
        if (this.selectedWaypoints.size === 0) {
            this.showStatus('Please select waypoints to delete', 'error');
            return;
        }

        const count = this.selectedWaypoints.size;
        const confirmed = await window.showConfirmModal(
            (window.i18n?.t('confirm.delete_n_waypoints') ?? 'Delete {n} waypoint(s)?').replace('{n}', count)
        );
        if (!confirmed) return;

        try {
            // Delete in reverse order to maintain indices
            const indices = Array.from(this.selectedWaypoints).sort((a, b) => b - a);
            
            for (const index of indices) {
                const response = await fetch(`/api/waypoints/${index}`, {
                    method: 'DELETE'
                });
                if (!response.ok) {
                    throw new Error('Failed to delete waypoint');
                }
            }

            this.selectedWaypoints.clear();
            await this.loadWaypoints();
            this.showStatus(`Deleted ${count} waypoint(s)`, 'success');
        } catch (error) {
            this.showStatus('Delete failed: ' + error.message, 'error');
        }
    }

    async deleteWaypointFromMap(index) {
        const waypoint = this.waypoints[index];
        if (!waypoint) {
            this.showStatus('Waypoint not found', 'error');
            return;
        }

        const confirmed = await window.showConfirmModal(
            (window.i18n?.t('confirm.delete_waypoint') ?? 'Delete waypoint "{name}"?').replace('{name}', waypoint.name)
        );
        if (!confirmed) return;

        try {
            const response = await fetch(`/api/waypoints/${index}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) {
                throw new Error('Failed to delete waypoint');
            }

            await this.loadWaypoints();
            this.showStatus(`Deleted waypoint "${waypoint.name}"`, 'success');
        } catch (error) {
            this.showStatus('Delete failed: ' + error.message, 'error');
        }
    }

    async fetchElevation() {
        const latInput = document.getElementById('wp-latitude');
        const lonInput = document.getElementById('wp-longitude');
        const elevValueInput = document.getElementById('wp-elevation-value');
        const elevUnitSelect = document.getElementById('wp-elevation-unit');
        
        const lat = parseFloat(latInput.value);
        const lon = parseFloat(lonInput.value);
        
        if (!lat || !lon) {
            this.showStatus('Please enter latitude and longitude first', 'error');
            return;
        }

        try {
            const response = await fetch(`/api/elevation?lat=${lat}&lon=${lon}`);
            const result = await response.json();
            
            if (result.success) {
                elevValueInput.value = result.elevation;
                elevUnitSelect.value = 'm'; // API returns meters
                this.showStatus('Elevation fetched successfully', 'success');
            } else {
                this.showStatus('Error fetching elevation: ' + result.error, 'error');
            }
        } catch (error) {
            this.showStatus('Elevation fetch failed: ' + error.message, 'error');
        }
    }

    addWaypointOnMap() {
        const button = document.getElementById('add-waypoint-map-btn');
        const map = this.map.getContainer();
        
        if (map.classList.contains('adding-waypoint')) {
            map.classList.remove('adding-waypoint');
            button.innerHTML = '<i class="fas fa-map-pin" slot="prefix"></i> Add Waypoint on Map';
        } else {
            map.classList.add('adding-waypoint');
            button.innerHTML = '<i class="fas fa-times" slot="prefix"></i> Cancel';
            this.showStatus('Click on the map to add a waypoint', 'info');
        }
    }

    async addWaypointAtLocation(lat, lng) {
        // Try to get town name using reverse geocoding
        let waypointName = '';
        
        try {
            // Use Nominatim (OpenStreetMap) reverse geocoding service
            const response = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=10&addressdetails=1`);
            if (response.ok) {
                const data = await response.json();
                
                // Try to extract a meaningful place name
                const address = data.address || {};
                waypointName = address.town || 
                              address.city || 
                              address.village || 
                              address.hamlet || 
                              address.municipality || 
                              address.county || 
                              '';
                
                // If we got a name, clean it up
                if (waypointName) {
                    // Remove any extra spaces and capitalize properly
                    waypointName = waypointName.trim();
                }
            }
        } catch (error) {
            console.warn('Could not fetch town name:', error);
        }
        
        // Fallback to coordinate-based name if no town name found
        if (!waypointName) {
            const latDir = lat >= 0 ? 'N' : 'S';
            const lonDir = lng >= 0 ? 'E' : 'W';
            waypointName = `WP ${Math.abs(lat).toFixed(3)}${latDir} ${Math.abs(lng).toFixed(3)}${lonDir}`;
        }
        
        this.showWaypointModal({
            name: waypointName,
            latitude: lat,
            longitude: lng,
            code: '',
            country: '',
            elevation: '',
            style: 1,
            runway_direction: '',
            runway_length: '',
            runway_width: '',
            frequency: '',
            description: ''
        });
    }

    toggleSelectAll(checked) {
        const checkboxes = document.querySelectorAll('.waypoint-checkbox');
        checkboxes.forEach((cb, index) => {
            cb.checked = checked;
            if (checked) {
                this.selectedWaypoints.add(index);
            } else {
                this.selectedWaypoints.delete(index);
            }
        });
        this.updateActionButtons();
    }

    toggleWaypointSelection(index, checked) {
        if (checked) {
            this.selectedWaypoints.add(index);
        } else {
            this.selectedWaypoints.delete(index);
        }
        this.updateActionButtons();
        
        // Update select-all checkbox
        const selectAll = document.getElementById('select-all');
        const totalCheckboxes = document.querySelectorAll('.waypoint-checkbox').length;
        selectAll.checked = this.selectedWaypoints.size === totalCheckboxes;
        selectAll.indeterminate = this.selectedWaypoints.size > 0 && this.selectedWaypoints.size < totalCheckboxes;
    }

    sortTable(column) {
        if (this.sortColumn === column) {
            this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortColumn = column;
            this.sortDirection = 'asc';
        }

        this.waypoints.sort((a, b) => {
            let aVal = a[column];
            let bVal = b[column];
            
            // Handle numeric columns
            if (column === 'latitude' || column === 'longitude' || column === 'style') {
                aVal = parseFloat(aVal) || 0;
                bVal = parseFloat(bVal) || 0;
            } else {
                aVal = String(aVal || '').toLowerCase();
                bVal = String(bVal || '').toLowerCase();
            }
            
            let result = 0;
            if (aVal < bVal) result = -1;
            else if (aVal > bVal) result = 1;
            
            return this.sortDirection === 'desc' ? -result : result;
        });

        this.updateTable();
        this.updateSortIndicators();
    }

    updateSortIndicators() {
        document.querySelectorAll('[data-sort] i').forEach(i => {
            i.className = 'fas fa-sort';
        });
        
        if (this.sortColumn) {
            const header = document.querySelector(`[data-sort="${this.sortColumn}"] i`);
            if (header) {
                header.className = `fas fa-sort-${this.sortDirection === 'asc' ? 'up' : 'down'}`;
            }
        }
    }

    switchTab(tabName) {
        document.getElementById('main-tabs').show(tabName);
    }

    switchModalTab(tabName) {
        document.getElementById('modal-tabs').show(tabName);
    }

    handleKeyboardShortcuts(event) {
        // Only handle shortcuts when waypoint modal is open
        const modal = document.getElementById('waypoint-modal');
        if (!modal.open) {
            return;
        }

        if (event.key === 'Escape') {
            event.preventDefault();
            this.hideWaypointModal();
        } else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            // Trigger form submit
            document.getElementById('waypoint-form').dispatchEvent(new Event('submit'));
        }
    }

    updateUI(fitBounds = false) {
        this.updateTable();
        this.updateMapMarkers(fitBounds); // Pass fitBounds flag through
        this.updateActionButtons();
        this.updateStatus();
        if (window.taskPlanner) {
            window.taskPlanner.refreshUI();
        }
    }

    updateTable() {
        if (window.VIEW_MODE) return;
        const tbody = document.getElementById('waypoints-tbody');
        tbody.innerHTML = '';

        this.waypoints.forEach((waypoint, index) => {
            const row = document.createElement('tr');
            const isSelected = this.selectedWaypoints.has(index);
            
            if (isSelected) {
                row.classList.add('selected');
            }

            const isAirfield = waypoint.runway_direction || waypoint.runway_length || waypoint.frequency;
            
            row.innerHTML = `
                <td>
                    <input type="checkbox" class="waypoint-checkbox" ${isSelected ? 'checked' : ''} 
                           onchange="app.toggleWaypointSelection(${index}, this.checked)">
                </td>
                <td class="font-bold">${this.escapeHtml(waypoint.name)}</td>
                <td>${this.escapeHtml(waypoint.code || '')}</td>
                <td>${this.escapeHtml(waypoint.country || '')}</td>
                <td>${waypoint.latitude.toFixed(6)}</td>
                <td>${waypoint.longitude.toFixed(6)}</td>
                <td>${waypoint.elevation ? waypoint.elevation + ' m' : ''}</td>
                <td>${waypoint.style}</td>
                <td>
                    <span class="airfield-indicator ${isAirfield ? 'airfield-yes' : 'airfield-no'}">
                        <i class="fas fa-${isAirfield ? 'plane' : 'circle'}"></i>
                        ${isAirfield ? (window.i18n?.t('common.yes') ?? 'Yes') : (window.i18n?.t('common.no') ?? 'No')}
                    </span>
                </td>
                <td>
                    <sl-button size="small" variant="neutral" onclick="app.showWaypointModal(app.waypoints[${index}], ${index})">
                        <i class="fas fa-edit"></i>
                    </sl-button>
                </td>
            `;
            
            tbody.appendChild(row);
        });
    }

    debouncedUpdateMapMarkers() {
        // Clear any existing timeout
        if (this.updateTimeout) {
            clearTimeout(this.updateTimeout);
        }
        
        // Set a new timeout for smoother updates
        this.updateTimeout = setTimeout(() => {
            this.updateMapMarkers();
        }, 150); // 150ms delay for smooth updates
    }

    updateMapMarkers(fitBounds = false) {
        // Clear existing markers from cluster group
        this.markerClusterGroup.clearLayers();
        this.mapMarkers = {};

        // Show loading indicator for large datasets
        if (this.waypoints.length > 1000) {
            this.showLoadingIndicator(`Loading ${this.waypoints.length} waypoints on map...`);
        }

        // Use requestAnimationFrame for smooth rendering
        requestAnimationFrame(() => {
            // Create markers array for batch adding to cluster group
            const markers = [];
            
            // Add markers for all waypoints
            this.waypoints.forEach((waypoint, index) => {
                // Create custom icon based on waypoint style
                const customIcon = createWaypointIcon(waypoint.style || 1, 24);
                
                const marker = L.marker([waypoint.latitude, waypoint.longitude], {
                    icon: customIcon
                });

                // Get style info for popup
                const styleInfo = getWaypointIcon(waypoint.style || 1);

                // Create popup content and bind it to marker
                const popupContent = this.createDetailedPopup(waypoint, index, styleInfo);
                marker.bindPopup(popupContent, {
                    maxWidth: 350,
                    className: 'waypoint-detailed-popup',
                    autoClose: true,
                    closeOnClick: true
                });
                
                this.mapMarkers[index] = marker;
                markers.push(marker);
            });

            // Add all markers to cluster group at once for better performance
            this.markerClusterGroup.addLayers(markers);

            // Fit bounds only when explicitly requested (initial/file load)
            if (fitBounds && this.waypoints.length > 0) {
                this.fitMapBounds();
            }

            // Hide loading indicator with a small delay
            setTimeout(() => {
                this.hideLoadingIndicator();
            }, 100);
        });
    }

    fitMapBounds() {
        if (this.waypoints.length === 0) return;

        // Use cluster group bounds for better performance
        if (this.markerClusterGroup.getLayers().length > 0) {
            this.map.fitBounds(this.markerClusterGroup.getBounds().pad(0.1));
        }
    }

    updateActionButtons() {
        if (window.VIEW_MODE) return;
        const hasWaypoints = this.waypoints.length > 0;
        const hasSelection = this.selectedWaypoints.size > 0;
        const singleSelection = this.selectedWaypoints.size === 1;

        document.getElementById('save-cup-btn').disabled = !hasWaypoints;
        document.getElementById('edit-waypoint-btn').disabled = !singleSelection;
        document.getElementById('delete-waypoint-btn').disabled = !hasSelection;
    }

    updateStatus() {
        const count = this.waypoints.length;
        document.getElementById('status-text').textContent = count > 0 ? 'Ready' : 'Ready - No waypoints loaded';
        document.getElementById('waypoint-count').textContent = `${count} waypoint${count !== 1 ? 's' : ''}`;
    }

    showStatus(message, type = 'info') {
        const statusText = document.getElementById('status-text');
        const badge = statusText.closest('sl-badge');
        const originalText = statusText.textContent;

        const variantMap = { success: 'success', error: 'danger', warning: 'warning', info: 'neutral' };
        const variant = variantMap[type] || 'neutral';

        statusText.textContent = message;
        statusText.className = '';
        if (badge) badge.setAttribute('variant', variant);

        setTimeout(() => {
            statusText.textContent = originalText;
            statusText.className = '';
            if (badge) badge.setAttribute('variant', 'neutral');
        }, 3000);
    }

    showLoading(show) {
        const overlay = document.getElementById('loading-overlay');
        overlay.style.display = show ? 'flex' : 'none';
    }

    async pasteCoordinates() {
        try {
            const text = await navigator.clipboard.readText();
            const cleanText = text.trim();
            
            // Try to parse various coordinate formats
            // Format: "lat, lon" (e.g., "52.7652, 23.1867")
            const latLonMatch = cleanText.match(/(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)/);
            
            if (latLonMatch) {
                const lat = parseFloat(latLonMatch[1]);
                const lon = parseFloat(latLonMatch[2]);
                
                // Validate coordinates
                if (lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
                    document.getElementById('wp-latitude').value = lat;
                    document.getElementById('wp-longitude').value = lon;
                    this.showStatus('Coordinates pasted successfully', 'success');
                } else {
                    this.showStatus('Invalid coordinate range. Latitude: -90 to 90, Longitude: -180 to 180', 'error');
                }
            } else {
                this.showStatus('Could not parse coordinates. Expected format: "lat, lon" (e.g., "52.7652, 23.1867")', 'error');
            }
        } catch (error) {
            this.showStatus('Could not access clipboard. Please paste manually.', 'error');
        }
    }

    createDetailedPopup(waypoint, index, styleInfo) {
        // Helper function to format coordinate display
        const formatCoordinate = (value, type) => {
            const abs = Math.abs(value);
            const dir = type === 'lat' ? (value >= 0 ? 'N' : 'S') : (value >= 0 ? 'E' : 'W');
            return `${abs.toFixed(6)}° ${dir}`;
        };

        // Helper function to check if field has meaningful value
        const hasValue = (field) => field && field.toString().trim() !== '';

        const i18n = window.i18n || { t: (k, fb) => fb !== undefined ? fb : k };

        // Build information sections
        const displayName = waypoint.name || waypoint.code || '—';
        let basicInfo = `
            <div class="popup-section">
                <h4 class="popup-title" style="color:var(--sl-color-neutral-900); word-break:break-word;">${this.escapeHtml(displayName)}</h4>
                <div class="popup-field">
                    <span class="field-label">${i18n.t('popup.type', 'Type')}:</span>
                    <span class="field-value">${styleInfo.name} (${waypoint.style || 1})</span>
                </div>
            </div>
        `;

        // Identification section
        let identificationSection = '';
        if (hasValue(waypoint.code) || hasValue(waypoint.country)) {
            identificationSection = `
                <div class="popup-section">
                    <h5 class="popup-section-title">${i18n.t('popup.identification', 'Identification')}</h5>
                    ${hasValue(waypoint.code) ? `
                        <div class="popup-field">
                            <span class="field-label">${i18n.t('tbl.code', 'Code')}:</span>
                            <span class="field-value">${this.escapeHtml(waypoint.code)}</span>
                        </div>
                    ` : ''}
                    ${hasValue(waypoint.country) ? `
                        <div class="popup-field">
                            <span class="field-label">${i18n.t('tbl.country', 'Country')}:</span>
                            <span class="field-value">${this.escapeHtml(waypoint.country)}</span>
                        </div>
                    ` : ''}
                </div>
            `;
        }

        // Position section (always present)
        let positionSection = `
            <div class="popup-section">
                <h5 class="popup-section-title">${i18n.t('popup.position', 'Position')}</h5>
                <div class="popup-field">
                    <span class="field-label">${i18n.t('tbl.latitude', 'Latitude')}:</span>
                    <span class="field-value">${formatCoordinate(waypoint.latitude, 'lat')}</span>
                </div>
                <div class="popup-field">
                    <span class="field-label">${i18n.t('tbl.longitude', 'Longitude')}:</span>
                    <span class="field-value">${formatCoordinate(waypoint.longitude, 'lon')}</span>
                </div>
                <div class="popup-field">
                    <span class="field-label">${i18n.t('popup.decimal', 'Decimal')}:</span>
                    <span class="field-value">${waypoint.latitude.toFixed(6)}, ${waypoint.longitude.toFixed(6)}</span>
                </div>
                ${hasValue(waypoint.elevation) ? `
                    <div class="popup-field">
                        <span class="field-label">${i18n.t('tbl.elevation', 'Elevation')}:</span>
                        <span class="field-value">${this.escapeHtml(waypoint.elevation)} m</span>
                    </div>
                ` : ''}
            </div>
        `;

        // Airfield section
        let airfieldSection = '';
        if (hasValue(waypoint.runway_direction) || hasValue(waypoint.runway_length) || 
            hasValue(waypoint.runway_width) || hasValue(waypoint.frequency)) {
            airfieldSection = `
                <div class="popup-section">
                    <h5 class="popup-section-title">${i18n.t('popup.airfield_info', 'Airfield Information')}</h5>
                    ${hasValue(waypoint.runway_direction) ? `
                        <div class="popup-field">
                            <span class="field-label">${i18n.t('popup.runway_direction', 'Runway Direction')}:</span>
                            <span class="field-value">${this.escapeHtml(waypoint.runway_direction)}</span>
                        </div>
                    ` : ''}
                    ${hasValue(waypoint.runway_length) ? `
                        <div class="popup-field">
                            <span class="field-label">${i18n.t('popup.runway_length', 'Runway Length')}:</span>
                            <span class="field-value">${this.escapeHtml(waypoint.runway_length)} m</span>
                        </div>
                    ` : ''}
                    ${hasValue(waypoint.runway_width) ? `
                        <div class="popup-field">
                            <span class="field-label">${i18n.t('popup.runway_width', 'Runway Width')}:</span>
                            <span class="field-value">${this.escapeHtml(waypoint.runway_width)} m</span>
                        </div>
                    ` : ''}
                    ${hasValue(waypoint.frequency) ? `
                        <div class="popup-field">
                            <span class="field-label">${i18n.t('popup.radio_frequency', 'Radio Frequency')}:</span>
                            <span class="field-value">${this.escapeHtml(waypoint.frequency)} MHz</span>
                        </div>
                    ` : ''}
                </div>
            `;
        }

        // Description section
        let descriptionSection = '';
        if (hasValue(waypoint.description)) {
            descriptionSection = `
                <div class="popup-section">
                    <h5 class="popup-section-title">${i18n.t('popup.description', 'Description')}</h5>
                    <div class="popup-description">
                        ${this.escapeHtml(waypoint.description)}
                    </div>
                </div>
            `;
        }

        // Action buttons
        let actionsSection = `
            <div class="popup-actions">
                <sl-button size="small" variant="neutral" onclick="app.showWaypointModal(app.waypoints[${index}], ${index})">
                    <i class="fas fa-edit"></i> ${i18n.t('btn.edit', 'Edit')}
                </sl-button>
                <sl-button size="small" variant="danger" onclick="app.deleteWaypointFromMap(${index})">
                    <i class="fas fa-trash"></i> ${i18n.t('btn.delete', 'Delete')}
                </sl-button>
            </div>
        `;

        return `
            <div class="marker-popup detailed-popup">
                ${basicInfo}
                ${identificationSection}
                ${positionSection}
                ${airfieldSection}
                ${descriptionSection}
                ${actionsSection}
            </div>
        `;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Performance optimization methods
    updateProgress(processed, total) {
        // Update progress indicator for large dataset loading
        const percent = Math.round((processed / total) * 100);
        const progressElement = document.getElementById('loading-progress');
        if (progressElement) {
            progressElement.textContent = `Loading waypoints: ${percent}% (${processed}/${total})`;
        }
    }

    showLoadingIndicator(message = 'Loading...') {
        // Create loading overlay
        let overlay = document.getElementById('loading-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'loading-overlay';
            overlay.innerHTML = `
                <div class="loading-content">
                    <div class="spinner"></div>
                    <div id="loading-progress">${message}</div>
                </div>
            `;
            document.body.appendChild(overlay);
        } else {
            const progressElement = document.getElementById('loading-progress');
            if (progressElement) {
                progressElement.textContent = message;
            }
            overlay.style.display = 'flex';
        }
    }

    hideLoadingIndicator() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    }

    // ── AI Planner panel ─────────────────────────────────────────────────────
    _updateAiPlannerPanel() {
        const anon    = document.getElementById('ai-planner-anon-cta');
        const upgrade = document.getElementById('ai-planner-upgrade-cta');
        const content = document.getElementById('ai-planner-premium-content');
        if (!anon || !upgrade || !content) return;

        const am = window.authManager;
        if (!am || !am.isAuthenticated) {
            anon.hidden = false; upgrade.hidden = true; content.hidden = true;
        } else if (!am.currentUser.has_openrouter_key) {
            // Logged in but no API key configured
            anon.hidden = true; upgrade.hidden = false; content.hidden = true;
            // Wire up the "go to settings" button
            document.getElementById('ai-goto-settings-btn')?.addEventListener('click', () => {
                document.getElementById('main-tabs')?.show?.('my-content');
                setTimeout(() => document.getElementById('my-content-tabs')?.show?.('mc-settings'), 100);
            }, { once: true });
        } else {
            anon.hidden = true; upgrade.hidden = true; content.hidden = false;
            if (window.aiPlanner) window.aiPlanner.init();
        }
    }

    // ── Save waypoints to account ─────────────────────────────────────────────
    showSaveWaypointsDialog() {
        const dialog = document.getElementById('save-waypoints-dialog');
        if (!dialog) return;
        const nameEl = document.getElementById('save-wf-name');
        if (nameEl) nameEl.value = this.currentFileName || '';
        // Premium gate: visibility switch
        const visRow = document.getElementById('save-wf-visibility-row');
        if (visRow) visRow.hidden = !(window.authManager?.isPremium());
        const wfErrEl = document.getElementById('save-wf-error');
        if (wfErrEl) { wfErrEl.textContent = ''; wfErrEl.style.display = 'none'; }
        dialog.show();
    }

    async handleSaveWaypointsSubmit() {
        const name = document.getElementById('save-wf-name')?.value?.trim();
        const errorEl = document.getElementById('save-wf-error');
        const showError = (msg) => { errorEl.textContent = msg; errorEl.style.display = msg ? '' : 'none'; };
        if (!name) { showError('Name is required.'); return; }
        const desc = document.getElementById('save-wf-desc')?.value?.trim() || '';
        const isPublic = document.getElementById('save-wf-public')?.checked ?? true;

        // Build entries from current session waypoints
        const entries = this.waypoints.map(wp => ({
            name: wp.name, code: wp.code, country: wp.country,
            latitude: wp.latitude, longitude: wp.longitude, elevation: wp.elevation,
            style: wp.style, runway_direction: wp.runway_direction,
            runway_length: wp.runway_length, runway_width: wp.runway_width,
            frequency: wp.frequency, description: wp.description
        }));

        showError('');
        try {
            const resp = await fetch('/api/waypoints/files', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name, description: desc, is_public: isPublic, waypoints: entries})
            });
            const data = await resp.json();
            if (!resp.ok) { showError(data.error || 'Save failed.'); return; }
            document.getElementById('save-waypoints-dialog').hide();
        } catch (err) {
            showError('Network error. Please try again.');
        }
    }

}

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.app = new SoaringCupEditor();
});

// Add custom CSS for map markers
const style = document.createElement('style');
style.textContent = `
    .custom-marker {
        background: white;
        border-radius: 50%;
        border: 2px solid #2563eb;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #2563eb;
        font-size: 12px;
    }
    
    .airfield-marker {
        border-color: #059669;
        color: #059669;
    }
    
    .adding-waypoint {
        cursor: crosshair !important;
    }
    
    .marker-popup h4 {
        margin: 0 0 10px 0;
        color: #1e293b;
    }
    
    .marker-popup p {
        margin: 5px 0;
        font-size: 14px;
    }
    
    /* Loading overlay styles */
    #loading-overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.7);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 10000;
    }
    
    .loading-content {
        background: white;
        padding: 2rem;
        border-radius: 8px;
        text-align: center;
        min-width: 300px;
    }
    
    .spinner {
        width: 40px;
        height: 40px;
        border: 4px solid #f3f4f6;
        border-top: 4px solid #3b82f6;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto 1rem;
    }
    
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    
    #loading-progress {
        color: #374151;
        font-weight: 500;
    }
    
    /* Map performance optimizations */
    .leaflet-container {
        will-change: transform;
        transform: translateZ(0);
    }
    
    .leaflet-tile-container {
        will-change: transform;
    }
    
    .leaflet-marker-icon, .leaflet-marker-shadow {
        will-change: transform;
    }
`;
document.head.appendChild(style);

// Reusable confirmation dialog (replaces native browser confirm)
window.showConfirmModal = function(message) {
    return new Promise((resolve) => {
        const dialog = document.getElementById('confirm-modal');
        const msgEl = document.getElementById('confirm-modal-message');
        const okBtn = document.getElementById('confirm-modal-ok');
        const cancelBtn = document.getElementById('confirm-modal-cancel');

        msgEl.textContent = message;
        dialog.show();

        let resolved = false;
        function done(result) {
            if (resolved) return;
            resolved = true;
            dialog.hide();
            cleanup();
            resolve(result);
        }

        function onOk() { done(true); }
        function onCancel() { done(false); }
        function onRequestClose(e) {
            e.preventDefault();
            done(false);
        }

        function cleanup() {
            okBtn.removeEventListener('click', onOk);
            cancelBtn.removeEventListener('click', onCancel);
            dialog.removeEventListener('sl-request-close', onRequestClose);
        }

        okBtn.addEventListener('click', onOk);
        cancelBtn.addEventListener('click', onCancel);
        dialog.addEventListener('sl-request-close', onRequestClose);
    });
};