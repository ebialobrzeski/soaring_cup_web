/**
 * AI Planner — frontend controller for the AI Task Planner tab.
 *
 * Manages the form inputs, API calls, and result rendering.
 * Instantiated by app.js when the AI Planner tab is shown for a premium user.
 */
class AiPlanner {
    constructor() {
        this._bound = false;
        this._generating = false;
    }

    /** Bind event listeners (idempotent). */
    init() {
        if (this._bound) return;
        this._bound = true;
        this._currentSessionId = null;

        // Set default flight date to tomorrow
        const dateEl = document.getElementById('aip-flight-date');
        if (dateEl && !dateEl.value) {
            const tomorrow = new Date();
            tomorrow.setDate(tomorrow.getDate() + 1);
            dateEl.value = tomorrow.toISOString().slice(0, 10);
        }

        // Generate button
        document.getElementById('aip-generate-btn')
            ?.addEventListener('click', () => this._handleGenerate());

        // Regenerate
        document.getElementById('aip-regenerate-btn')
            ?.addEventListener('click', () => this._handleGenerate());

        // Load into editor
        document.getElementById('aip-load-editor-btn')
            ?.addEventListener('click', () => this._loadIntoEditor());

        // Fetch glider list then set up autocomplete
        this._fetchGliders().then(() => this._setupGliderAutocomplete());

        // Airport autocomplete
        this._setupAirportAutocomplete('aip-takeoff', 'aip-takeoff-ac');
        this._setupAirportAutocomplete('aip-destination', 'aip-destination-ac');

        // Session history menu
        this._setupSessionMenu();
        this._loadSessions();

        // Restore last session on refresh
        this._restoreLastSession();
    }

    // ── Airport autocomplete ────────────────────────────────────────────────

    _setupAirportAutocomplete(inputId, listId) {
        const input = document.getElementById(inputId);
        const list = document.getElementById(listId);
        if (!input || !list) return;

        let debounce = null;
        let activeIdx = -1;
        let items = [];

        input.addEventListener('sl-input', () => {
            clearTimeout(debounce);
            const q = input.value.trim();
            if (q.length < 2) { this._closeAcList(list); return; }
            debounce = setTimeout(() => this._fetchAirports(q, list, input), 250);
        });

        input.addEventListener('sl-focus', () => {
            if (input.value.trim().length >= 2 && list.children.length > 0) {
                list.classList.add('open');
            }
        });

        input.addEventListener('keydown', (e) => {
            items = Array.from(list.querySelectorAll('.aip-ac-item'));
            if (!list.classList.contains('open') || !items.length) return;

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                activeIdx = Math.min(activeIdx + 1, items.length - 1);
                this._highlightAcItem(items, activeIdx);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                activeIdx = Math.max(activeIdx - 1, 0);
                this._highlightAcItem(items, activeIdx);
            } else if (e.key === 'Enter' && activeIdx >= 0) {
                e.preventDefault();
                items[activeIdx]?.click();
            } else if (e.key === 'Escape') {
                this._closeAcList(list);
            }
        });

        // Close on outside click
        document.addEventListener('click', (e) => {
            if (!input.contains(e.target) && !list.contains(e.target)) {
                this._closeAcList(list);
            }
        });
    }

    async _fetchAirports(q, listEl, inputEl) {
        try {
            const resp = await fetch(`/api/planner/airports?q=${encodeURIComponent(q)}`);
            if (!resp.ok) return;
            const airports = await resp.json();
            this._renderAcList(airports, listEl, inputEl);
        } catch { /* silent */ }
    }

    _renderAcList(airports, listEl, inputEl) {
        if (!airports.length) {
            listEl.innerHTML = '<div class="aip-ac-item" style="color:var(--text-secondary);cursor:default;">No airports found</div>';
            listEl.classList.add('open');
            return;
        }
        listEl.innerHTML = airports.map(a => {
            const label = a.icao ? `${a.name} (${a.icao})` : a.name;
            const meta = [a.country, a.elevation != null ? `${a.elevation}m` : ''].filter(Boolean).join(' · ');
            return `<div class="aip-ac-item" data-id="${a.id}" data-name="${this._escapeAttr(a.name)}" data-icao="${a.icao || ''}">
                <span class="aip-ac-item-name">${this._escapeHtml(label)}</span>
                <span class="aip-ac-item-meta">${this._escapeHtml(meta)}</span>
            </div>`;
        }).join('');

        listEl.querySelectorAll('.aip-ac-item[data-id]').forEach(item => {
            item.addEventListener('click', () => {
                const name = item.dataset.name;
                const icao = item.dataset.icao;
                inputEl.value = icao || name;
                this._closeAcList(listEl);
            });
        });

        listEl.classList.add('open');
    }

    _highlightAcItem(items, idx) {
        items.forEach((el, i) => el.classList.toggle('active', i === idx));
        items[idx]?.scrollIntoView({ block: 'nearest' });
    }

    _closeAcList(listEl) {
        listEl.classList.remove('open');
    }

    _escapeAttr(s) {
        return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
    }

    // ── Glider autocomplete ─────────────────────────────────────────────────

    async _fetchGliders() {
        try {
            const resp = await fetch('/api/planner/gliders');
            if (!resp.ok) { this._gliders = []; return; }
            this._gliders = await resp.json();
        } catch {
            this._gliders = [];
        }
    }

    _setupGliderAutocomplete() {
        const input = document.getElementById('aip-glider');
        const list = document.getElementById('aip-glider-ac');
        const hidden = document.getElementById('aip-glider-id');
        if (!input || !list || !hidden) return;

        let activeIdx = -1;
        let items = [];

        const filterAndShow = () => {
            const q = input.value.trim().toLowerCase();
            const matches = q.length
                ? this._gliders.filter(g => g.name.toLowerCase().includes(q))
                : this._gliders;
            this._renderGliderList(matches.slice(0, 30), list, input, hidden);
            activeIdx = -1;
        };

        input.addEventListener('sl-input', () => {
            // Clear hidden id when user types (selection invalidated)
            hidden.value = '';
            filterAndShow();
        });

        input.addEventListener('sl-focus', filterAndShow);

        input.addEventListener('sl-clear', () => {
            hidden.value = '';
            input.value = '';
            this._closeAcList(list);
        });

        input.addEventListener('keydown', (e) => {
            items = Array.from(list.querySelectorAll('.aip-ac-item'));
            if (!list.classList.contains('open') || !items.length) return;

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                activeIdx = Math.min(activeIdx + 1, items.length - 1);
                this._highlightAcItem(items, activeIdx);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                activeIdx = Math.max(activeIdx - 1, 0);
                this._highlightAcItem(items, activeIdx);
            } else if (e.key === 'Enter' && activeIdx >= 0) {
                e.preventDefault();
                items[activeIdx]?.click();
            } else if (e.key === 'Escape') {
                this._closeAcList(list);
            }
        });

        document.addEventListener('click', (e) => {
            if (!input.contains(e.target) && !list.contains(e.target)) {
                this._closeAcList(list);
            }
        });
    }

    _renderGliderList(gliders, listEl, inputEl, hiddenEl) {
        if (!gliders.length) {
            listEl.innerHTML = '<div class="aip-ac-item" style="color:var(--text-secondary);cursor:default;">No matching gliders</div>';
            listEl.classList.add('open');
            return;
        }
        listEl.innerHTML = gliders.map(g => {
            const label = `${g.name} (${g.max_gross_kg} kg)`;
            return `<div class="aip-ac-item" data-id="${g.id}" data-name="${this._escapeAttr(g.name)}">
                <span class="aip-ac-item-name">${this._escapeHtml(label)}</span>
            </div>`;
        }).join('');

        listEl.querySelectorAll('.aip-ac-item[data-id]').forEach(item => {
            item.addEventListener('click', () => {
                hiddenEl.value = item.dataset.id;
                inputEl.value = item.dataset.name;
                this._closeAcList(listEl);
            });
        });

        listEl.classList.add('open');
    }

    // ── Collect form data ────────────────────────────────────────────────────

    _collectInputs() {
        const val = (id) => document.getElementById(id)?.value?.trim() || '';
        const checked = (id) => document.getElementById(id)?.checked ?? false;

        const excludeClasses = [];
        if (checked('aip-exclude-C')) excludeClasses.push('C');
        if (checked('aip-exclude-D')) excludeClasses.push('D');
        if (checked('aip-exclude-E')) excludeClasses.push('E');

        return {
            takeoff_airport: val('aip-takeoff'),
            destination_airport: val('aip-destination') || val('aip-takeoff'),
            target_distance_km: parseFloat(val('aip-distance')) || 150,
            flight_date: val('aip-flight-date'),
            max_duration_hours: parseFloat(val('aip-max-duration')) || 4,
            takeoff_time: val('aip-takeoff-time') || null,
            glider_id: val('aip-glider-id') || null,
            safety_profile: document.getElementById('aip-safety')?.value || 'standard',
            soaring_mode: document.getElementById('aip-soaring-mode')?.value || 'thermal',
            constraints: {
                exclude_transponder: checked('aip-exclude-transponder'),
                exclude_flight_plan: checked('aip-exclude-flightplan'),
                exclude_restricted: checked('aip-exclude-restricted'),
                exclude_danger: checked('aip-exclude-danger'),
                exclude_prohibited: true, // always
                allow_border_crossing: checked('aip-allow-border-crossing'),
                exclude_classes: excludeClasses,
            },
        };
    }

    // ── Validation ───────────────────────────────────────────────────────────

    _validate(inputs) {
        if (!inputs.takeoff_airport) return 'Takeoff airport is required.';
        if (!inputs.flight_date) return 'Flight date is required.';
        if (inputs.target_distance_km < 10) return 'Target distance must be at least 10 km.';
        return null;
    }

    // ── Generate ─────────────────────────────────────────────────────────────

    async _handleGenerate() {
        if (this._generating) return;

        const inputs = this._collectInputs();
        const err = this._validate(inputs);
        if (err) {
            this._showError(err);
            return;
        }

        this._setViewState('loading');
        this._generating = true;

        try {
            const resp = await fetch('/api/planner/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(inputs),
            });

            if (!resp.ok) {
                const data = await resp.json().catch(() => ({}));
                this._showError(data.error || `Server error (${resp.status})`);
                return;
            }

            const proposal = await resp.json();

            // Persist session reference
            if (proposal.session_id) {
                this._currentSessionId = proposal.session_id;
                try { localStorage.setItem('aip_last_session', proposal.session_id); } catch {}
                this._loadSessions();  // refresh session list
            }

            this._renderProposal(proposal);
        } catch (e) {
            this._showError('Network error — could not reach the server.');
        } finally {
            this._generating = false;
        }
    }

    // ── View state management ────────────────────────────────────────────────

    _setViewState(state) {
        const statusEl = document.getElementById('aip-status');
        const loadingEl = document.getElementById('aip-loading');
        const resultEl = document.getElementById('aip-result');

        if (statusEl) statusEl.hidden = state !== 'idle' && state !== 'error';
        if (loadingEl) loadingEl.hidden = state !== 'loading';
        if (resultEl) resultEl.hidden = state !== 'result';
    }

    _showError(msg) {
        this._setViewState('error');
        const statusEl = document.getElementById('aip-status');
        if (statusEl) {
            statusEl.hidden = false;
            statusEl.innerHTML = `
                <div class="aip-empty-state aip-error-state">
                    <i class="fas fa-exclamation-triangle fa-2x" style="color:var(--sl-color-danger-500); margin-bottom:12px;"></i>
                    <p>${this._escapeHtml(msg)}</p>
                </div>`;
        }
    }

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ── Render proposal ──────────────────────────────────────────────────────

    _renderProposal(proposal) {
        if (proposal.status === 'error') {
            this._showError(proposal.message || 'Task generation failed.');
            return;
        }

        if (proposal.status === 'pending') {
            // Backend modules not complete yet — show informational message
            this._setViewState('result');
            const resultEl = document.getElementById('aip-result');
            if (!resultEl) return;
            resultEl.hidden = false;

            document.getElementById('aip-result-title').textContent = 'Task Generation';
            document.getElementById('aip-result-distance').textContent =
                `${proposal.inputs?.target_distance_km || '—'} km (target)`;
            document.getElementById('aip-result-time').textContent =
                `${proposal.inputs?.max_duration_hours || '—'}h max`;
            document.getElementById('aip-result-speed').textContent = '—';
            document.getElementById('aip-result-airspace').textContent = '—';

            const legsEl = document.getElementById('aip-legs-table');
            if (legsEl) legsEl.innerHTML = '';

            const conflictsEl = document.getElementById('aip-conflicts');
            if (conflictsEl) conflictsEl.innerHTML = '';

            const narrativeEl = document.getElementById('aip-narrative');
            if (narrativeEl) {
                narrativeEl.innerHTML = `
                    <div class="aip-narrative-box">
                        <i class="fas fa-info-circle"></i>
                        <div>
                            <strong>Status:</strong> ${this._escapeHtml(proposal.message)}<br>
                            <small>
                                Takeoff: <strong>${this._escapeHtml(proposal.inputs?.takeoff_airport || '—')}</strong> |
                                Date: <strong>${proposal.inputs?.flight_date || '—'}</strong> |
                                Mode: <strong>${proposal.inputs?.soaring_mode || '—'}</strong> |
                                Safety: <strong>${proposal.inputs?.safety_profile || '—'}</strong>
                            </small>
                        </div>
                    </div>`;
            }
            return;
        }

        // ── status === 'completed' — full task proposal ──────────────────
        this._setViewState('result');
        const resultEl = document.getElementById('aip-result');
        if (resultEl) resultEl.hidden = false;

        const task = proposal.task || {};
        const inputs = proposal.inputs || {};

        // Score badge
        const scoreBadge = this._scoreBadge(proposal.score);

        // Title
        document.getElementById('aip-result-title').textContent =
            task.description || `${inputs.takeoff_airport || 'Task'} — ${(task.total_distance_km || 0).toFixed(0)} km`;

        // Key stats
        document.getElementById('aip-result-distance').textContent =
            `${(task.total_distance_km || 0).toFixed(1)} km`;
        document.getElementById('aip-result-time').textContent =
            proposal.estimated_duration_hours
                ? `${proposal.estimated_duration_hours.toFixed(1)}h`
                : '—';
        document.getElementById('aip-result-speed').textContent =
            proposal.estimated_speed_kmh
                ? `${proposal.estimated_speed_kmh.toFixed(0)} km/h`
                : '—';

        // Airspace info
        const airInfoEl = document.getElementById('aip-result-airspace');
        if (airInfoEl) {
            if (proposal.airspace) {
                const a = proposal.airspace;
                airInfoEl.textContent = a.has_blocking
                    ? `⚠ ${a.conflicts} conflict(s)`
                    : a.conflicts > 0
                        ? `${a.zones_count} zones, ${a.conflicts} minor`
                        : `${a.zones_count} zones, clear`;
            } else {
                airInfoEl.textContent = '—';
            }
        }

        // Render score + recommended takeoff
        const scoreEl = document.getElementById('aip-result-score');
        if (scoreEl) scoreEl.innerHTML = scoreBadge;
        const takeoffTimeEl = document.getElementById('aip-result-takeoff-time');
        if (takeoffTimeEl) {
            takeoffTimeEl.textContent = proposal.recommended_takeoff_time || '—';
        }

        // Legs table
        this._renderLegs(task.legs || []);

        // Airspace conflicts
        if (proposal.airspace?.conflicts > 0) {
            this._renderConflicts([{
                zone_name: `${proposal.airspace.conflicts} airspace conflict(s)`,
                zone_type: proposal.airspace.has_blocking ? 'blocking' : 'advisory',
                suggestion: proposal.airspace.has_blocking ? 'avoid' : 'caution',
            }]);
        } else {
            const conflictsEl = document.getElementById('aip-conflicts');
            if (conflictsEl) conflictsEl.innerHTML = '';
        }

        // Terrain info
        const terrainEl = document.getElementById('aip-terrain');
        if (terrainEl && proposal.terrain) {
            const t = proposal.terrain;
            terrainEl.innerHTML = `<div class="aip-terrain-info">
                <i class="fas fa-mountain"></i>
                <span>Terrain: ${t.safe ? '✅ Clear' : '⚠ Check required'} — max ${t.max_terrain_m || '?'}m ASL</span>
            </div>`;
        }

        // AI narrative
        const narrativeEl = document.getElementById('aip-narrative');
        if (narrativeEl) {
            let html = '';
            // Weather summary
            if (proposal.weather_summary_en) {
                html += `<div class="aip-narrative-box aip-weather-summary">
                    <i class="fas fa-cloud-sun"></i>
                    <div>${this._renderMarkdown(proposal.weather_summary_en)}</div>
                </div>`;
            }
            // Explanation
            if (proposal.explanation_en) {
                html += `<div class="aip-narrative-box">
                    <i class="fas fa-robot"></i>
                    <div>${this._renderMarkdown(proposal.explanation_en)}</div>
                </div>`;
            }
            // Safety notes
            if (proposal.safety_notes?.length) {
                html += `<div class="aip-narrative-box aip-safety-notes">
                    <i class="fas fa-shield-alt"></i>
                    <div><strong>Safety Notes:</strong><ul>${
                        proposal.safety_notes.map(n => `<li>${this._escapeHtml(n)}</li>`).join('')
                    }</ul></div>
                </div>`;
            }
            // AI model attribution
            if (proposal.ai_model && proposal.ai_model !== 'none') {
                html += `<div class="aip-ai-attr"><small>Analysis by: ${this._escapeHtml(proposal.ai_model)}</small></div>`;
            }
            narrativeEl.innerHTML = html || '<div class="aip-narrative-box"><i class="fas fa-info-circle"></i><div>No detailed analysis available.</div></div>';
        }

        // Alternatives section
        this._renderAlternatives(proposal.alternatives || []);

        // Store task data for "Load into editor"
        this._currentTask = proposal;
    }

    _scoreBadge(score) {
        if (score == null) return '';
        let cls = 'aip-score-poor';
        if (score >= 81) cls = 'aip-score-excellent';
        else if (score >= 61) cls = 'aip-score-good';
        else if (score >= 41) cls = 'aip-score-marginal';
        return `<span class="aip-score-badge ${cls}">${score}/100</span>`;
    }

    _renderMarkdown(text) {
        // Simple bold only: **text** → <strong>text</strong>
        return this._escapeHtml(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    }

    _renderAlternatives(alts) {
        const el = document.getElementById('aip-alternatives');
        if (!el) return;
        if (!alts.length) { el.innerHTML = ''; return; }

        let html = '<h4><i class="fas fa-route"></i> Alternative Routes</h4>';
        html += '<div class="aip-alt-list">';
        alts.forEach((alt, i) => {
            html += `<div class="aip-alt-card" data-alt-idx="${i}">
                <span class="aip-alt-desc">${this._escapeHtml(alt.description || `Alternative ${i + 1}`)}</span>
                <span class="aip-alt-dist">${(alt.total_distance_km || 0).toFixed(1)} km</span>
                <span class="aip-alt-score">${(alt.score || 0).toFixed(0)} pts</span>
            </div>`;
        });
        html += '</div>';
        el.innerHTML = html;
    }

    _renderLegs(legs) {
        const el = document.getElementById('aip-legs-table');
        if (!el || !legs.length) { if (el) el.innerHTML = ''; return; }

        let html = '<table class="aip-legs"><thead><tr><th>Leg</th><th>Dist</th><th>Bearing</th><th>Thermal</th><th>Wind</th></tr></thead><tbody>';
        legs.forEach((leg, i) => {
            html += `<tr>
                <td>${i + 1}</td>
                <td>${(leg.distance_km || 0).toFixed(1)} km</td>
                <td>${leg.bearing || '—'}°</td>
                <td>${leg.thermal_quality || '—'}</td>
                <td>${leg.wind_exposure || '—'}</td>
            </tr>`;
        });
        html += '</tbody></table>';
        el.innerHTML = html;
    }

    _renderConflicts(conflicts) {
        const el = document.getElementById('aip-conflicts');
        if (!el || !conflicts.length) { if (el) el.innerHTML = ''; return; }

        let html = '<h4><i class="fas fa-exclamation-triangle"></i> Airspace Conflicts</h4><ul class="aip-conflict-list">';
        conflicts.forEach(c => {
            const icon = c.suggestion === 'avoid'
                ? '<i class="fas fa-ban" style="color:var(--sl-color-danger-500)"></i>'
                : '<i class="fas fa-info-circle" style="color:var(--sl-color-warning-500)"></i>';
            html += `<li>${icon} <strong>${this._escapeHtml(c.zone_name)}</strong> (${c.zone_type}) — ${c.suggestion}</li>`;
        });
        html += '</ul>';
        el.innerHTML = html;
    }

    // ── Session persistence ─────────────────────────────────────────────────

    _setupSessionMenu() {
        const menu = document.getElementById('aip-session-menu');
        if (!menu) return;

        menu.addEventListener('sl-select', (e) => {
            const item = e.detail?.item;
            if (!item) return;
            const action = item.dataset.action;
            const sid = item.dataset.sessionId;

            if (action === 'delete' && sid) {
                this._deleteSession(sid);
            } else if (sid) {
                this._loadSession(sid);
            }
        });
    }

    async _loadSessions() {
        const menu = document.getElementById('aip-session-menu');
        if (!menu) return;

        try {
            const resp = await fetch('/api/planner/sessions');
            if (!resp.ok) return;
            const sessions = await resp.json();

            if (!sessions.length) {
                menu.innerHTML = '<sl-menu-item disabled>No saved sessions</sl-menu-item>';
                return;
            }

            menu.innerHTML = sessions.map(s => {
                const d = s.updated_at ? new Date(s.updated_at).toLocaleDateString() : '';
                const active = s.id === this._currentSessionId ? ' style="font-weight:600;"' : '';
                return `<sl-menu-item data-session-id="${this._escapeAttr(s.id)}"${active}>
                    <span>${this._escapeHtml(s.name || 'Untitled')}</span>
                    <small style="opacity:.6;margin-left:8px;">${d}</small>
                </sl-menu-item>`;
            }).join('') +
                '<sl-divider></sl-divider>' +
                '<sl-menu-item data-action="delete" data-session-id="__current__" ' +
                'style="color:var(--sl-color-danger-500);">' +
                '<i class="fas fa-trash-alt" slot="prefix"></i> Delete current session</sl-menu-item>';
        } catch { /* silent */ }
    }

    async _loadSession(sessionId) {
        try {
            const resp = await fetch(`/api/planner/sessions/${encodeURIComponent(sessionId)}`);
            if (!resp.ok) return;
            const session = await resp.json();

            this._currentSessionId = session.id;
            try { localStorage.setItem('aip_last_session', session.id); } catch {}

            // Restore form inputs
            const inputs = session.inputs || {};
            this._setInputValue('aip-takeoff', inputs.takeoff_airport);
            this._setInputValue('aip-destination', inputs.destination_airport !== inputs.takeoff_airport ? inputs.destination_airport : '');
            this._setInputValue('aip-distance', inputs.target_distance_km);
            this._setInputValue('aip-max-duration', inputs.max_duration_hours);
            this._setInputValue('aip-flight-date', inputs.flight_date);
            this._setInputValue('aip-takeoff-time', inputs.takeoff_time || '');

            // Restore glider
            if (inputs.glider_id) {
                const hidden = document.getElementById('aip-glider-id');
                if (hidden) hidden.value = inputs.glider_id;
                const glider = (this._gliders || []).find(g => g.id === inputs.glider_id);
                if (glider) this._setInputValue('aip-glider', glider.name);
            }

            // Restore soaring mode
            const modeEl = document.getElementById('aip-soaring-mode');
            if (modeEl && inputs.soaring_mode) modeEl.value = inputs.soaring_mode;

            // Restore safety profile
            const safetyEl = document.getElementById('aip-safety');
            if (safetyEl && inputs.safety_profile) safetyEl.value = inputs.safety_profile;

            // Restore constraint checkboxes
            if (inputs.constraints) {
                this._setChecked('aip-exclude-transponder', inputs.constraints.exclude_transponder);
                this._setChecked('aip-exclude-flightplan', inputs.constraints.exclude_flight_plan);
                this._setChecked('aip-exclude-restricted', inputs.constraints.exclude_restricted);
                this._setChecked('aip-exclude-danger', inputs.constraints.exclude_danger);
                this._setChecked('aip-allow-border-crossing', inputs.constraints.allow_border_crossing);
                const cls = inputs.constraints.exclude_classes || [];
                this._setChecked('aip-exclude-C', cls.includes('C'));
                this._setChecked('aip-exclude-D', cls.includes('D'));
                this._setChecked('aip-exclude-E', cls.includes('E'));
            }

            // Render result if available
            if (session.result) {
                session.result.session_id = session.id;
                this._renderProposal(session.result);
            }

            this._loadSessions(); // refresh active indicator
        } catch { /* silent */ }
    }

    async _deleteSession(sessionId) {
        const id = sessionId === '__current__' ? this._currentSessionId : sessionId;
        if (!id) return;

        try {
            const resp = await fetch(`/api/planner/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' });
            if (!resp.ok) return;

            if (id === this._currentSessionId) {
                this._currentSessionId = null;
                try { localStorage.removeItem('aip_last_session'); } catch {}
                this._setViewState('idle');
            }
            this._loadSessions();
        } catch { /* silent */ }
    }

    async _restoreLastSession() {
        let lastId;
        try { lastId = localStorage.getItem('aip_last_session'); } catch {}
        if (lastId) {
            // Wait for gliders to be ready before restoring (for glider name display)
            await this._fetchGliders().catch(() => {});
            await this._loadSession(lastId);
        }
    }

    _setInputValue(id, val) {
        const el = document.getElementById(id);
        if (el && val != null) el.value = String(val);
    }

    _setChecked(id, val) {
        const el = document.getElementById(id);
        if (el) el.checked = !!val;
    }

    // ── Load into editor ─────────────────────────────────────────────────────

    _loadIntoEditor() {
        const proposal = this._currentTask;
        if (!proposal?.task?.turnpoints?.length) return;

        const task = proposal.task;
        const inputs = proposal.inputs || {};
        const tp = window.taskPlanner;
        if (!tp) return;

        // Build waypoint objects from turnpoints
        const waypoints = window.app ? window.app.waypoints : [];
        tp.taskPoints = [];

        task.turnpoints.forEach((pt, i) => {
            let name;
            if (i === 0) name = inputs.takeoff_airport || 'Start';
            else if (i === task.turnpoints.length - 1 && task.turnpoints.length > 2) name = inputs.destination_airport || inputs.takeoff_airport || 'Finish';
            else name = `TP${i}`;

            const wp = {
                name,
                latitude: pt.lat,
                longitude: pt.lon,
                elevation: 0,
                code: name.slice(0, 6).toUpperCase(),
            };
            waypoints.push(wp);
            const wpIdx = waypoints.length - 1;

            let obsZone;
            if (i === 0) {
                obsZone = { style: 0, r1: 5000, a1: 90, r2: 0, a2: 180, a12: 0, isLine: true, move: true, reduce: false, directionMode: 'auto', fixedBearing: null };
            } else if (i === task.turnpoints.length - 1) {
                obsZone = { style: 2, r1: 3000, a1: 180, r2: 0, a2: 180, a12: 0, isLine: false, move: true, reduce: false, directionMode: 'auto', fixedBearing: null };
            } else {
                obsZone = { style: 1, r1: 3000, a1: 45, r2: 500, a2: 180, a12: 0, isLine: false, move: true, reduce: false, directionMode: 'auto', fixedBearing: null };
            }

            tp.taskPoints.push({ waypointIndex: wpIdx, waypoint: wp, obsZone });
        });

        if (window.app) window.app.waypoints = waypoints;

        // Set task name
        const nameEl = document.getElementById('task-name');
        if (nameEl) nameEl.value = task.description || `AI Task ${(task.total_distance_km || 0).toFixed(0)}km`;

        tp.refreshUI();
        setTimeout(() => tp.fitTaskBounds(), 100);

        // Switch to task tab
        const tabGroup = document.querySelector('#main-tabs');
        if (tabGroup) tabGroup.show?.('task');
    }
}

// Singleton
window.aiPlanner = new AiPlanner();
