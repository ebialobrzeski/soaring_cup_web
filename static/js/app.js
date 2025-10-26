// Soaring CUP File Editor - Web Application JavaScript

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
        this.initializeMap();
        this.loadWaypoints();
        this.updateUI();
        
        // Since map tab is now default, ensure map renders properly
        setTimeout(() => {
            this.map.invalidateSize();
        }, 100);
    }

    setupEventListeners() {
        // File operations
        document.getElementById('file-upload').addEventListener('change', (e) => this.handleFileUpload(e));
        document.getElementById('new-btn').addEventListener('click', () => this.newFile());
        document.getElementById('save-cup-btn').addEventListener('click', () => this.downloadFile('cup'));
        document.getElementById('save-csv-btn').addEventListener('click', () => this.downloadFile('csv'));

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

        // Tab navigation
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => this.switchTab(btn.dataset.tab));
        });

        // Modal tab navigation
        document.querySelectorAll('.modal-tab-btn').forEach(btn => {
            btn.addEventListener('click', () => this.switchModalTab(btn.dataset.modalTab));
        });

        // Modal
        document.getElementById('modal-close').addEventListener('click', () => this.hideWaypointModal());
        document.getElementById('cancel-btn').addEventListener('click', () => this.hideWaypointModal());
        document.getElementById('waypoint-form').addEventListener('submit', (e) => this.handleWaypointSubmit(e));
        document.getElementById('fetch-elevation-btn').addEventListener('click', () => this.fetchElevation());
        document.getElementById('paste-coords-btn').addEventListener('click', () => this.pasteCoordinates());

        // Map controls
        document.getElementById('fit-bounds-btn').addEventListener('click', () => this.fitMapBounds());
        document.getElementById('add-waypoint-map-btn').addEventListener('click', () => this.addWaypointOnMap());
        document.getElementById('show-legend-btn').addEventListener('click', () => this.showLegendModal());

        // Legend modal
        document.getElementById('legend-close').addEventListener('click', () => this.hideLegendModal());

        // Close modal when clicking outside
        document.getElementById('waypoint-modal').addEventListener('click', (e) => {
            if (e.target.id === 'waypoint-modal') {
                this.hideWaypointModal();
            }
        });

        document.getElementById('legend-modal').addEventListener('click', (e) => {
            if (e.target.id === 'legend-modal') {
                this.hideLegendModal();
            }
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => this.handleKeyboardShortcuts(e));
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
            maxClusterRadius: 30,        // Even smaller cluster radius for smoother transitions
            disableClusteringAtZoom: 11, // Stop clustering earlier at zoom level 11
            spiderfyOnMaxZoom: true,
            showCoverageOnHover: false,
            zoomToBoundsOnClick: true,
            removeOutsideVisibleBounds: false, // Keep all markers loaded - prevents panning jumpiness
            animate: false,              // Disable all animations to prevent jumpiness
            animateAddingMarkers: false, // Disable marker addition animations for performance
            singleMarkerMode: false,     // Keep clustering even for single markers
            spiderfyDistanceMultiplier: 1, // Reduce spiderfy animation
            maxZoom: 18                  // Prevent clustering issues at high zoom
        });
        
        this.map.addLayer(this.markerClusterGroup);

        // Add click handler for adding waypoints on map
        this.map.on('click', (e) => {
            if (this.map.getContainer().classList.contains('adding-waypoint')) {
                this.addWaypointAtLocation(e.latlng.lat, e.latlng.lng);
                this.map.getContainer().classList.remove('adding-waypoint');
                document.getElementById('add-waypoint-map-btn').textContent = '📍 Add Waypoint on Map';
            }
        });
    }

    async loadWaypoints() {
        try {
            const response = await fetch('/api/waypoints');
            if (response.ok) {
                this.waypoints = await response.json();
                this.updateUI();
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
                this.updateUI();
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
            if (!confirm('This will clear all current waypoints. Continue?')) {
                return;
            }
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
            const response = await fetch(`/api/download/${format}`);
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `waypoints.${format}`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                this.showStatus(`Downloaded ${this.waypoints.length} waypoints as ${format.toUpperCase()}`, 'success');
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
        const title = document.getElementById('modal-title');
        const form = document.getElementById('waypoint-form');

        title.textContent = waypoint ? 'Edit Waypoint' : 'Add Waypoint';
        
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
            
            // Handle elevation with unit
            if (waypoint.elevation) {
                const elevMatch = waypoint.elevation.toString().match(/^(\d+(?:\.\d+)?)(m|ft)?$/);
                if (elevMatch) {
                    document.getElementById('wp-elevation-value').value = elevMatch[1];
                    document.getElementById('wp-elevation-unit').value = elevMatch[2] || 'm';
                } else {
                    document.getElementById('wp-elevation-value').value = waypoint.elevation;
                }
            }
            
            // Handle runway length with unit
            if (waypoint.runway_length) {
                const lenMatch = waypoint.runway_length.toString().match(/^(\d+(?:\.\d+)?)(m|nm|ml)?$/);
                if (lenMatch) {
                    document.getElementById('wp-runway-length-value').value = lenMatch[1];
                    document.getElementById('wp-runway-length-unit').value = lenMatch[2] || 'm';
                } else {
                    document.getElementById('wp-runway-length-value').value = waypoint.runway_length;
                }
            }
            
            // Handle runway width with unit
            if (waypoint.runway_width) {
                const widthMatch = waypoint.runway_width.toString().match(/^(\d+(?:\.\d+)?)(m|nm|ml)?$/);
                if (widthMatch) {
                    document.getElementById('wp-runway-width-value').value = widthMatch[1];
                    document.getElementById('wp-runway-width-unit').value = widthMatch[2] || 'm';
                } else {
                    document.getElementById('wp-runway-width-value').value = waypoint.runway_width;
                }
            }
        }

        modal.classList.add('show');
        document.getElementById('wp-name').focus();
    }

    hideWaypointModal() {
        const modal = document.getElementById('waypoint-modal');
        modal.classList.remove('show');
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
        
        modal.classList.add('show');
    }

    hideLegendModal() {
        const modal = document.getElementById('legend-modal');
        modal.classList.remove('show');
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
        if (!confirm(`Delete ${count} waypoint(s)?`)) {
            return;
        }

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

        if (!confirm(`Delete waypoint "${waypoint.name}"?`)) {
            return;
        }

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
            const response = await fetch(`/api/elevation/${lat}/${lon}`);
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
            button.innerHTML = '<i class="fas fa-map-pin"></i> Add Waypoint on Map';
        } else {
            map.classList.add('adding-waypoint');
            button.innerHTML = '<i class="fas fa-times"></i> Cancel';
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
        // Update tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });
        
        // Update tab panes
        document.querySelectorAll('.tab-pane').forEach(pane => {
            pane.classList.toggle('active', pane.id === `${tabName}-tab`);
        });
        
        // Refresh map if switching to map tab
        if (tabName === 'map') {
            setTimeout(() => {
                this.map.invalidateSize();
                // Removed updateMapMarkers() - markers should already be loaded
            }, 100);
        }
    }

    switchModalTab(tabName) {
        // Update modal tab buttons
        document.querySelectorAll('.modal-tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.modalTab === tabName);
        });
        
        // Update modal tab panes
        document.querySelectorAll('.modal-tab-pane').forEach(pane => {
            pane.classList.toggle('active', pane.id === `modal-${tabName}-tab`);
        });
    }

    handleKeyboardShortcuts(event) {
        // Only handle shortcuts when modal is open
        const modal = document.getElementById('waypoint-modal');
        if (!modal.classList.contains('show')) {
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

    updateUI() {
        this.updateTable();
        this.updateMapMarkers(); // Use direct call instead of debounced for initial loads
        this.updateActionButtons();
        this.updateStatus();
    }

    updateTable() {
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
                <td>${this.escapeHtml(waypoint.elevation || '')}</td>
                <td>${waypoint.style}</td>
                <td>
                    <span class="airfield-indicator ${isAirfield ? 'airfield-yes' : 'airfield-no'}">
                        <i class="fas fa-${isAirfield ? 'plane' : 'circle'}"></i>
                        ${isAirfield ? 'Yes' : 'No'}
                    </span>
                </td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick="app.showWaypointModal(app.waypoints[${index}], ${index})">
                        <i class="fas fa-edit"></i>
                    </button>
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

    updateMapMarkers() {
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

                // Use lazy popup creation for better performance
                marker.on('click', () => {
                    const popupContent = this.createDetailedPopup(waypoint, index, styleInfo);
                    marker.bindPopup(popupContent, {
                        maxWidth: 350,
                        className: 'waypoint-detailed-popup'
                    }).openPopup();
                });
                
                this.mapMarkers[index] = marker;
                markers.push(marker);
            });

            // Add all markers to cluster group at once for better performance
            this.markerClusterGroup.addLayers(markers);

            // Fit bounds if there are waypoints
            if (this.waypoints.length > 0) {
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
        const hasWaypoints = this.waypoints.length > 0;
        const hasSelection = this.selectedWaypoints.size > 0;
        const singleSelection = this.selectedWaypoints.size === 1;

        document.getElementById('save-cup-btn').disabled = !hasWaypoints;
        document.getElementById('save-csv-btn').disabled = !hasWaypoints;
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
        const originalText = statusText.textContent;
        
        statusText.textContent = message;
        statusText.className = `text-${type}`;
        
        setTimeout(() => {
            statusText.textContent = originalText;
            statusText.className = '';
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

        // Build information sections
        let basicInfo = `
            <div class="popup-section">
                <h4 class="popup-title">${this.escapeHtml(waypoint.name)}</h4>
                <div class="popup-field">
                    <span class="field-label">Type:</span>
                    <span class="field-value">${styleInfo.name} (${waypoint.style || 1})</span>
                </div>
            </div>
        `;

        // Identification section
        let identificationSection = '';
        if (hasValue(waypoint.code) || hasValue(waypoint.country)) {
            identificationSection = `
                <div class="popup-section">
                    <h5 class="popup-section-title">Identification</h5>
                    ${hasValue(waypoint.code) ? `
                        <div class="popup-field">
                            <span class="field-label">Code:</span>
                            <span class="field-value">${this.escapeHtml(waypoint.code)}</span>
                        </div>
                    ` : ''}
                    ${hasValue(waypoint.country) ? `
                        <div class="popup-field">
                            <span class="field-label">Country:</span>
                            <span class="field-value">${this.escapeHtml(waypoint.country)}</span>
                        </div>
                    ` : ''}
                </div>
            `;
        }

        // Position section (always present)
        let positionSection = `
            <div class="popup-section">
                <h5 class="popup-section-title">Position</h5>
                <div class="popup-field">
                    <span class="field-label">Latitude:</span>
                    <span class="field-value">${formatCoordinate(waypoint.latitude, 'lat')}</span>
                </div>
                <div class="popup-field">
                    <span class="field-label">Longitude:</span>
                    <span class="field-value">${formatCoordinate(waypoint.longitude, 'lon')}</span>
                </div>
                <div class="popup-field">
                    <span class="field-label">Decimal:</span>
                    <span class="field-value">${waypoint.latitude.toFixed(6)}, ${waypoint.longitude.toFixed(6)}</span>
                </div>
                ${hasValue(waypoint.elevation) ? `
                    <div class="popup-field">
                        <span class="field-label">Elevation:</span>
                        <span class="field-value">${this.escapeHtml(waypoint.elevation)}</span>
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
                    <h5 class="popup-section-title">Airfield Information</h5>
                    ${hasValue(waypoint.runway_direction) ? `
                        <div class="popup-field">
                            <span class="field-label">Runway Direction:</span>
                            <span class="field-value">${this.escapeHtml(waypoint.runway_direction)}</span>
                        </div>
                    ` : ''}
                    ${hasValue(waypoint.runway_length) ? `
                        <div class="popup-field">
                            <span class="field-label">Runway Length:</span>
                            <span class="field-value">${this.escapeHtml(waypoint.runway_length)}</span>
                        </div>
                    ` : ''}
                    ${hasValue(waypoint.runway_width) ? `
                        <div class="popup-field">
                            <span class="field-label">Runway Width:</span>
                            <span class="field-value">${this.escapeHtml(waypoint.runway_width)}</span>
                        </div>
                    ` : ''}
                    ${hasValue(waypoint.frequency) ? `
                        <div class="popup-field">
                            <span class="field-label">Radio Frequency:</span>
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
                    <h5 class="popup-section-title">Description</h5>
                    <div class="popup-description">
                        ${this.escapeHtml(waypoint.description)}
                    </div>
                </div>
            `;
        }

        // Action buttons
        let actionsSection = `
            <div class="popup-actions">
                <button class="btn btn-sm btn-secondary" onclick="app.showWaypointModal(app.waypoints[${index}], ${index})">
                    <i class="fas fa-edit"></i> Edit
                </button>
                <button class="btn btn-sm btn-danger" onclick="app.deleteWaypointFromMap(${index})">
                    <i class="fas fa-trash"></i> Delete
                </button>
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