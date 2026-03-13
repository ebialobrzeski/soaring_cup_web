-- Migration 024: i18n keys for AI Planner custom instructions textarea

INSERT INTO translation_keys (key, default_value, category, description) VALUES
    ('aip.custom_instructions',             'Custom instructions',                                                           'ai_planner', 'Label for custom instructions textarea'),
    ('aip.custom_instructions_placeholder', 'e.g. Avoid flying over large forests, prefer turnpoints near landing options…', 'ai_planner', 'Placeholder for custom instructions textarea')
ON CONFLICT (key) DO NOTHING;

-- Polish
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'pl', val FROM (VALUES
    ('aip.custom_instructions',             'Własne instrukcje'),
    ('aip.custom_instructions_placeholder', 'np. Unikaj przelotów nad dużymi lasami, preferuj punkty zwrotne blisko lądowisk…')
) AS t(k, val)
JOIN translation_keys ON translation_keys.key = t.k
ON CONFLICT DO NOTHING;

-- German
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'de', val FROM (VALUES
    ('aip.custom_instructions',             'Eigene Anweisungen'),
    ('aip.custom_instructions_placeholder', 'z.B. Flüge über große Wälder vermeiden, Wendepunkte in der Nähe von Landemöglichkeiten bevorzugen…')
) AS t(k, val)
JOIN translation_keys ON translation_keys.key = t.k
ON CONFLICT DO NOTHING;

-- Czech
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'cs', val FROM (VALUES
    ('aip.custom_instructions',             'Vlastní pokyny'),
    ('aip.custom_instructions_placeholder', 'např. Vyhněte se přeletu velkých lesů, preferujte otočné body poblíž možností přistání…')
) AS t(k, val)
JOIN translation_keys ON translation_keys.key = t.k
ON CONFLICT DO NOTHING;
