/**
 * waypoint-gen.js — Waypoint Generation from selected map area.
 *
 * Integrates with window.app (SoaringCupEditor) and the main Leaflet map.
 *
 * Flow:
 *  1. User clicks "Select Area" → map enters rectangle-draw mode.
 *  2. User drags to draw a bbox on the map.
 *  3. UI shows the selected area + type checkboxes.
 *  4. User clicks "Generate" → POST /api/waypoint-gen/generate.
 *  5. Response is merged into window.app.waypoints and updateUI() is called.
 *
 * Aviation data is fetched on-demand from OpenAIP; no local import required.
 */
(function () {
    'use strict';

    // ── State ────────────────────────────────────────────────────────────────
    let _selectionRect = null;   // L.Rectangle on the main map
    let _startLatLng = null;
    let _selectedBounds = null;  // L.LatLngBounds — the finalised bbox
    let _selecting = false;

    // ── DOM helpers ───────────────────────────────────────────────────────────
    const $ = (id) => document.getElementById(id);

    function _setStatus(msg, variant) {
        const el = $('wpgen-status');
        if (!el) return;
        el.style.display = msg ? 'block' : 'none';
        el.innerHTML = msg || '';
        el.className = 'wpgen-status' + (variant ? ` wpgen-status--${variant}` : '');
    }

    function _setGenerateEnabled() {
        const btn = $('wpgen-generate-btn');
        if (!btn) return;
        const hasBounds = !!_selectedBounds;
        const hasType = [
            'wpgen-airports', 'wpgen-outlandings', 'wpgen-obstacles',
            'wpgen-navaids', 'wpgen-hotspots', 'wpgen-hang-glidings', 'wpgen-reporting-points',
            'wpgen-cities', 'wpgen-towns', 'wpgen-villages',
        ].some((id) => {
            const el = $(id);
            return el && el.checked;
        });
        btn.disabled = !(hasBounds && hasType);
    }

    // ── Map area selection ────────────────────────────────────────────────────
    function _getMap() {
        return window.app && window.app.map;
    }

    function _formatBounds(bounds) {
        const fmt = (v) => v.toFixed(3);
        return (
            `${fmt(bounds.getSouth())}°N / ${fmt(bounds.getWest())}°E  →  ` +
            `${fmt(bounds.getNorth())}°N / ${fmt(bounds.getEast())}°E`
        );
    }

    function _updateAreaUI() {
        const areaInfo = $('wpgen-area-info');
        const areaText = $('wpgen-area-text');
        const selectBtn = $('wpgen-select-area-btn');

        if (_selectedBounds) {
            if (areaInfo) areaInfo.style.display = 'flex';
            if (areaText) areaText.textContent = _formatBounds(_selectedBounds);
            if (selectBtn) selectBtn.textContent = window.i18n?.t('wpgen.change_area') ?? 'Change Area';
        } else {
            if (areaInfo) areaInfo.style.display = 'none';
            if (selectBtn) selectBtn.innerHTML = `<i class="fas fa-vector-square" slot="prefix"></i> ${window.i18n?.t('wpgen.select_area') ?? 'Select Area'}`;
        }
        _setGenerateEnabled();
    }

    function _clearSelection() {
        const map = _getMap();
        if (_selectionRect && map) {
            map.removeLayer(_selectionRect);
            _selectionRect = null;
        }
        _selectedBounds = null;
        _startLatLng = null;
        _updateAreaUI();
        _setStatus('', '');
    }

    function _startAreaSelection() {
        const map = _getMap();
        if (!map || _selecting) return;

        _selecting = true;
        map.getContainer().style.cursor = 'crosshair';
        map.getContainer().classList.add('wpgen-selecting');
        // Disable dragging so mousedown/mousemove work cleanly
        map.dragging.disable();

        // Remove previous rect if any
        if (_selectionRect) { map.removeLayer(_selectionRect); _selectionRect = null; }

        // Touch / mouse unified events via Leaflet
        map.once('mousedown', function onDown(e) {
            _startLatLng = e.latlng;
            _selectionRect = L.rectangle(
                [e.latlng, e.latlng],
                { interactive: false, color: '#2563eb', weight: 2, fillOpacity: 0.15 }
            ).addTo(map);

            function onMove(ev) {
                _selectionRect && _selectionRect.setBounds([_startLatLng, ev.latlng]);
            }
            function onUp(ev) {
                map.off('mousemove', onMove);
                map.off('mouseup', onUp);
                _finishSelection(ev.latlng);
            }
            map.on('mousemove', onMove);
            map.on('mouseup', onUp);
        });
    }

    function _finishSelection(endLatLng) {
        const map = _getMap();
        _selecting = false;
        map.dragging.enable();
        map.getContainer().style.cursor = '';
        map.getContainer().classList.remove('wpgen-selecting');

        if (!_startLatLng || !endLatLng) {
            _clearSelection();
            return;
        }

        const bounds = L.latLngBounds(_startLatLng, endLatLng);
        if (bounds.getNorth() === bounds.getSouth() || bounds.getEast() === bounds.getWest()) {
            _clearSelection();
            return;
        }
        _selectedBounds = bounds;
        if (_selectionRect) _selectionRect.setBounds(bounds);
        _startLatLng = null;
        _updateAreaUI();
        _setStatus('', '');
    }

    // ── Generate ──────────────────────────────────────────────────────────────
    async function _generate() {
        if (!_selectedBounds) { _setStatus('Select an area on the map first.', 'error'); return; }

        const types = [];
        const typeMap = {
            'wpgen-airports': 'airports',
            'wpgen-outlandings': 'outlandings',
            'wpgen-obstacles': 'obstacles',
            'wpgen-navaids': 'navaids',
            'wpgen-hotspots': 'hotspots',
            'wpgen-hang-glidings': 'hang_glidings',
            'wpgen-reporting-points': 'reporting_points',
            'wpgen-cities': 'cities',
            'wpgen-towns': 'towns',
            'wpgen-villages': 'villages',
        };
        for (const [id, val] of Object.entries(typeMap)) {
            const el = $(id);
            if (el && el.checked) types.push(val);
        }
        if (!types.length) { _setStatus('Select at least one waypoint type.', 'error'); return; }

        const btn = $('wpgen-generate-btn');
        if (btn) { btn.loading = true; btn.disabled = true; }
        _setStatus('<i class="fas fa-spinner fa-spin"></i> Generating waypoints…', 'info');

        const body = {
            bbox: {
                min_lat: _selectedBounds.getSouth(),
                max_lat: _selectedBounds.getNorth(),
                min_lon: _selectedBounds.getWest(),
                max_lon: _selectedBounds.getEast(),
            },
            types,
        };

        try {
            const res = await fetch('/api/waypoint-gen/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();

            if (!data.success) {
                _setStatus(`<i class="fas fa-exclamation-circle"></i> ${data.error || 'Generation failed.'}`, 'error');
                return;
            }

            // Merge generated waypoints into existing client-side waypoints,
            // de-duplicating by name+lat+lon so re-generating the same area is safe.
            if (window.app) {
                const existing = window.app.waypoints || [];
                const existingKeys = new Set(
                    existing.map(wp => `${wp.name}|${(+wp.latitude).toFixed(5)}|${(+wp.longitude).toFixed(5)}`)
                );
                const incoming = data.waypoints || [];
                const newOnly = incoming.filter(
                    wp => !existingKeys.has(`${wp.name}|${(+wp.latitude).toFixed(5)}|${(+wp.longitude).toFixed(5)}`)
                );
                window.app.waypoints = existing.concat(newOnly);
                window.app.updateUI(true);
                data.added = newOnly.length;
            }

            // Build result message
            const src = data.sources || {};
            const parts = [];
            if (src.aviation) parts.push(`${src.aviation} aviation`);
            if (src.osm) parts.push(`${src.osm} OSM places`);
            const detail = parts.length ? ` (${parts.join(', ')})` : '';
            let msg = `<i class="fas fa-check-circle"></i> Added ${data.added} waypoint${data.added !== 1 ? 's' : ''}${detail}.`;

            if (data.warnings && data.warnings.length) {
                msg += `<br><small><i class="fas fa-exclamation-triangle"></i> ${data.warnings.join(' ')}</small>`;
            }
            _setStatus(msg, 'success');
        } catch (err) {
            _setStatus(`<i class="fas fa-exclamation-circle"></i> Error: ${err.message}`, 'error');
        } finally {
            if (btn) { btn.loading = false; btn.disabled = false; }
            _setGenerateEnabled();
        }
    }

    // ── Card collapse ─────────────────────────────────────────────────────────
    function _setupCardCollapse() {
        const btn = $('wpgen-card-toggle');
        const body = $('wpgen-card-body');
        if (!btn || !body) return;
        let collapsed = false;
        btn.addEventListener('click', () => {
            collapsed = !collapsed;
            body.style.display = collapsed ? 'none' : '';
            btn.name = collapsed ? 'chevron-right' : 'chevron-down';
        });
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        // Setup collapse
        _setupCardCollapse();

        // Select Area button
        const selectBtn = $('wpgen-select-area-btn');
        if (selectBtn) {
            selectBtn.addEventListener('click', _startAreaSelection);
        }

        // Clear area button
        const clearBtn = $('wpgen-clear-area-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', _clearSelection);
        }

        // Generate button
        const genBtn = $('wpgen-generate-btn');
        if (genBtn) {
            genBtn.addEventListener('click', _generate);
        }

        // Update generate button state when checkboxes change
        [
            'wpgen-airports', 'wpgen-outlandings', 'wpgen-obstacles',
            'wpgen-navaids', 'wpgen-hotspots', 'wpgen-hang-glidings', 'wpgen-reporting-points',
            'wpgen-cities', 'wpgen-towns', 'wpgen-villages',
        ].forEach((id) => {
            const el = $(id);
            if (el) el.addEventListener('sl-change', _setGenerateEnabled);
        });
    }

    // Wait for DOM + Shoelace to be ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        // Also wait a tick for Shoelace custom elements to upgrade
        requestAnimationFrame(init);
    }

    // Expose for debugging
    window.waypointGen = { clearSelection: _clearSelection };
})();
