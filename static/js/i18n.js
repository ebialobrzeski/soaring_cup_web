/**
 * i18n.js — Client-side internationalisation for GlidePlan.
 *
 * Usage:
 *   window.i18n.t('btn.save')               // → translated string or fallback
 *   window.i18n.t('btn.save', 'Save')       // → translated string or provided fallback
 *   window.i18n.setLanguage('pl')           // → switch language & re-apply DOM
 *   window.i18n.currentLang                 // → active language code string
 *
 * Any element with a [data-i18n] attribute will have its textContent replaced.
 * Any element with a [data-i18n-placeholder] attribute will have its
 * placeholder attribute replaced.
 */
(function () {
    'use strict';

    const STORAGE_KEY = 'glideplan_lang';
    const FALLBACK_LANG = 'en';
    const SUPPORTED = ['en', 'pl', 'de', 'cs'];

    let _translations = {};
    let _languages = [];
    let _currentLang = FALLBACK_LANG;
    let _ready = false;
    const _readyCallbacks = [];

    // ── Language detection ────────────────────────────────────────────────────

    function _detectLang() {
        // 1. localStorage preference
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored && SUPPORTED.includes(stored)) return stored;
        // 2. Browser language (first 2 chars)
        const browser = (navigator.language || navigator.userLanguage || '').slice(0, 2).toLowerCase();
        if (SUPPORTED.includes(browser)) return browser;
        return FALLBACK_LANG;
    }

    // ── Data loading ──────────────────────────────────────────────────────────

    async function _fetchLanguages() {
        try {
            const res = await fetch('/api/i18n/languages');
            if (!res.ok) return;
            const data = await res.json();
            if (data.success) _languages = data.languages;
        } catch (_) { /* non-fatal */ }
    }

    async function _fetchTranslations(lang) {
        try {
            const res = await fetch(`/api/i18n/${lang}`);
            if (!res.ok) return false;
            const data = await res.json();
            if (data.success) {
                _translations = data.translations;
                return true;
            }
        } catch (_) { /* non-fatal */ }
        return false;
    }

    // ── DOM application ───────────────────────────────────────────────────────

    function _applyToDOM() {
        // Text content
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            const val = _translations[key];
            if (val !== undefined) el.textContent = val;
        });
        // Placeholder attributes
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            const key = el.getAttribute('data-i18n-placeholder');
            const val = _translations[key];
            if (val !== undefined) el.setAttribute('placeholder', val);
        });
        // Title attributes
        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const key = el.getAttribute('data-i18n-title');
            const val = _translations[key];
            if (val !== undefined) el.setAttribute('title', val);
        });
        // Label attributes (sl-dialog, sl-input, sl-select, sl-radio-group, etc.)
        document.querySelectorAll('[data-i18n-label]').forEach(el => {
            const key = el.getAttribute('data-i18n-label');
            const val = _translations[key];
            if (val !== undefined) el.setAttribute('label', val);
        });
        // Summary attributes (sl-details)
        document.querySelectorAll('[data-i18n-summary]').forEach(el => {
            const key = el.getAttribute('data-i18n-summary');
            const val = _translations[key];
            if (val !== undefined) el.setAttribute('summary', val);
        });
        // HTML content (innerHTML — use for trusted pre-translated markup only)
        document.querySelectorAll('[data-i18n-html]').forEach(el => {
            const key = el.getAttribute('data-i18n-html');
            const val = _translations[key];
            if (val !== undefined) el.innerHTML = val;
        });
        // HTML lang attribute
        document.documentElement.lang = _currentLang;
    }

    // ── Language selector UI ──────────────────────────────────────────────────

    async function _populateSelector() {
        const sel = document.getElementById('lang-selector');
        if (!sel || _languages.length === 0) return;

        // Wait until Shoelace has fully defined and upgraded both components.
        // This is the key step — without it, setting .value or appending sl-option
        // elements has no effect when the component hasn't upgraded yet.
        if ('customElements' in window) {
            await Promise.all([
                customElements.whenDefined('sl-select'),
                customElements.whenDefined('sl-option'),
            ]);
        }

        sel.innerHTML = '';
        _languages.forEach(lang => {
            const opt = document.createElement('sl-option');
            opt.value = lang.code;
            opt.textContent = `${lang.flag_emoji || ''} ${lang.native_name}`.trim();
            sel.appendChild(opt);
        });

        // Wait for the sl-select component to finish its own internal update cycle
        // before assigning .value, so it can reflect the correct selected option.
        try { await sel.updateComplete; } catch (_) { /* not a Lit component */ }
        sel.value = _currentLang;
    }

    function _bindSelector() {
        const sel = document.getElementById('lang-selector');
        if (!sel) return;
        sel.addEventListener('sl-change', () => {
            setLanguage(sel.value);
        });
    }

    // ── Public API ────────────────────────────────────────────────────────────

    /**
     * Translate a key, returning the translated string or a fallback.
     * @param {string} key
     * @param {string} [fallback] - default returned when key not found
     * @returns {string}
     */
    function t(key, fallback) {
        return _translations[key] !== undefined
            ? _translations[key]
            : (fallback !== undefined ? fallback : key);
    }

    /**
     * Switch to a different language, persist the choice, re-apply DOM.
     * @param {string} lang - language code e.g. 'pl'
     */
    async function setLanguage(lang) {
        if (!SUPPORTED.includes(lang)) return;
        const ok = await _fetchTranslations(lang);
        if (!ok && lang !== FALLBACK_LANG) {
            // Degrade gracefully — keep current translations
            console.warn(`[i18n] failed to load language: ${lang}`);
            return;
        }
        _currentLang = lang;
        localStorage.setItem(STORAGE_KEY, lang);
        _applyToDOM();
        // Sync selector if it exists
        const sel = document.getElementById('lang-selector');
        if (sel && sel.value !== lang) sel.value = lang;
        // Notify listeners
        window.dispatchEvent(new CustomEvent('languagechange', { detail: { lang } }));
    }

    /**
     * Register a callback to fire once translations are initially loaded.
     * @param {Function} cb
     */
    function onReady(cb) {
        if (_ready) {
            cb();
        } else {
            _readyCallbacks.push(cb);
        }
    }

    // ── Initialisation ────────────────────────────────────────────────────────

    async function _init() {
        _currentLang = _detectLang();
        // Run language list and translations in parallel
        await Promise.all([
            _fetchLanguages(),
            _fetchTranslations(_currentLang),
        ]);
        await _populateSelector();
        _bindSelector();
        _applyToDOM();
        _ready = true;
        _readyCallbacks.forEach(cb => cb());

        // Re-apply after Shoelace custom elements upgrade (dynamic tab labels etc.)
        if ('customElements' in window) {
            customElements.whenDefined('sl-tab').then(() => _applyToDOM());
        }
    }

    // Expose global
    window.i18n = { t, setLanguage, onReady, get currentLang() { return _currentLang; } };

    // Boot when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _init);
    } else {
        _init();
    }
})();
