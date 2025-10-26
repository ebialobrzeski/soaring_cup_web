// Soaring CUP File Editor - Web Application JavaScript

class SoaringCupEditor {
    constructor() {
        this.waypoints = [];
        this.selectedWaypoints = new Set();
        this.currentEditIndex = -1;
        this.map = null;
        this.mapMarkers = {};
        this.sortColumn = null;
        this.sortDirection = 'asc';
        
        this.initializeApp();
    }

    initializeApp() {
        this.setupEventListeners();
        this.initializeMap();
        this.loadWaypoints();
        this.updateUI();
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

        // Map controls
        document.getElementById('fit-bounds-btn').addEventListener('click', () => this.fitMapBounds());
        document.getElementById('add-waypoint-map-btn').addEventListener('click', () => this.addWaypointOnMap());

        // Close modal when clicking outside
        document.getElementById('waypoint-modal').addEventListener('click', (e) => {
            if (e.target.id === 'waypoint-modal') {
                this.hideWaypointModal();
            }
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => this.handleKeyboardShortcuts(e));
    }

    initializeMap() {
        this.map = L.map('map').setView([50.0, 10.0], 6);
        
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(this.map);

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

    async handleWaypointSubmit(event) {
        event.preventDefault();
        
        const formData = new FormData(event.target);
        const waypointData = {};
        
        // Convert form data to object
        for (let [key, value] of formData.entries()) {
            if (key === 'latitude' || key === 'longitude') {
                waypointData[key] = parseFloat(value);
            } else if (key === 'style') {
                waypointData[key] = parseInt(value);
            } else {
                waypointData[key] = value.trim();
            }
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

    async fetchElevation() {
        const latInput = document.getElementById('wp-latitude');
        const lonInput = document.getElementById('wp-longitude');
        const elevInput = document.getElementById('wp-elevation');
        
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
                elevInput.value = `${result.elevation}m`;
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

    addWaypointAtLocation(lat, lng) {
        this.showWaypointModal({
            name: '',
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
                this.updateMapMarkers();
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
        this.updateMapMarkers();
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

    updateMapMarkers() {
        // Clear existing markers
        Object.values(this.mapMarkers).forEach(marker => {
            this.map.removeLayer(marker);
        });
        this.mapMarkers = {};

        // Add markers for all waypoints
        this.waypoints.forEach((waypoint, index) => {
            const isAirfield = waypoint.runway_direction || waypoint.runway_length || waypoint.frequency;
            
            const marker = L.marker([waypoint.latitude, waypoint.longitude], {
                icon: L.divIcon({
                    className: `custom-marker ${isAirfield ? 'airfield-marker' : 'waypoint-marker'}`,
                    html: `<i class="fas fa-${isAirfield ? 'plane' : 'map-pin'}"></i>`,
                    iconSize: [20, 20],
                    iconAnchor: [10, 10]
                })
            }).addTo(this.map);

            const popupContent = `
                <div class="marker-popup">
                    <h4>${this.escapeHtml(waypoint.name)}</h4>
                    ${waypoint.code ? `<p><strong>Code:</strong> ${this.escapeHtml(waypoint.code)}</p>` : ''}
                    <p><strong>Position:</strong> ${waypoint.latitude.toFixed(6)}, ${waypoint.longitude.toFixed(6)}</p>
                    ${waypoint.elevation ? `<p><strong>Elevation:</strong> ${this.escapeHtml(waypoint.elevation)}</p>` : ''}
                    ${waypoint.description ? `<p><strong>Description:</strong> ${this.escapeHtml(waypoint.description)}</p>` : ''}
                    <div style="margin-top: 10px;">
                        <button class="btn btn-sm btn-secondary" onclick="app.showWaypointModal(app.waypoints[${index}], ${index})">
                            Edit
                        </button>
                    </div>
                </div>
            `;
            
            marker.bindPopup(popupContent);
            this.mapMarkers[index] = marker;
        });

        // Fit bounds if there are waypoints
        if (this.waypoints.length > 0) {
            this.fitMapBounds();
        }
    }

    fitMapBounds() {
        if (this.waypoints.length === 0) return;

        const group = new L.featureGroup(Object.values(this.mapMarkers));
        this.map.fitBounds(group.getBounds().pad(0.1));
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

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
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
`;
document.head.appendChild(style);