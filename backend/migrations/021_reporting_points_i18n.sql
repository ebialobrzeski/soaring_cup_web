-- Migration 021: i18n keys for reporting points checkbox

INSERT INTO translation_keys (key, default_value, category, description) VALUES
    ('wpgen.reporting_points', 'Reporting Points', 'wpgen', 'Reporting points checkbox label')
ON CONFLICT (key) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Polish
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'pl', val FROM (VALUES
    ('wpgen.reporting_points', 'Punkty raportowania')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- German
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'de', val FROM (VALUES
    ('wpgen.reporting_points', 'Meldepunkte')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Czech
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'cs', val FROM (VALUES
    ('wpgen.reporting_points', 'Hlásné body')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;
