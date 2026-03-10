-- Migration 016: Translate sidebar card headers (Wind & Speed, Task Details)

INSERT INTO translation_keys (key, default_value, category, description) VALUES
    ('task.wind_speed_card', 'Wind & Speed', 'task', 'Wind & Speed card header'),
    ('task.details_card',    'Task Details', 'task', 'Task Details card header')
ON CONFLICT (key) DO NOTHING;

-- Polish
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'pl', val FROM (VALUES
    ('task.wind_speed_card', 'Wiatr i prędkość'),
    ('task.details_card',    'Szczegóły zadania')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;

-- German
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'de', val FROM (VALUES
    ('task.wind_speed_card', 'Wind & Geschwindigkeit'),
    ('task.details_card',    'Aufgabendetails')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;

-- Czech
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'cs', val FROM (VALUES
    ('task.wind_speed_card', 'Vítr a rychlost'),
    ('task.details_card',    'Detaily úlohy')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;
