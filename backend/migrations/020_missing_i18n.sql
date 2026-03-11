-- Migration 020: Missing translations — popup Edit/Delete buttons, browse-dialog
--                confirm messages, task No-start/Task-time labels.

-- ─────────────────────────────────────────────────────────────────────────────
-- New translation keys
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translation_keys (key, default_value, category, description) VALUES
    -- Generic action buttons (used in JS-built popups)
    ('btn.edit',                     'Edit',                                                            'btn',     'Edit button label'),
    ('btn.delete',                   'Delete',                                                          'btn',     'Delete button label'),
    -- Browse-dialog confirm messages
    ('confirm.replace_waypoints',    'This will replace your current waypoints with the selected file. Continue?', 'confirm', 'Replace waypoints confirm message'),
    ('confirm.replace_task',         'This will replace your current task. Continue?',                 'confirm', 'Replace task confirm message'),
    -- Task details advanced panel
    ('task.no_start_before',         'No start before (UTC)',                                          'task',    'No start before label'),
    ('task.task_time',               'Task time',                                                      'task',    'Task time label')
ON CONFLICT (key) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Polish
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'pl', val FROM (VALUES
    ('btn.edit',                  'Edytuj'),
    ('btn.delete',                'Usuń'),
    ('confirm.replace_waypoints', 'Spowoduje to zastąpienie aktualnych punktów wybranym plikiem. Kontynuować?'),
    ('confirm.replace_task',      'Spowoduje to zastąpienie bieżącego zadania. Kontynuować?'),
    ('task.no_start_before',      'Nie startuj przed (UTC)'),
    ('task.task_time',            'Czas zadania')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- German
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'de', val FROM (VALUES
    ('btn.edit',                  'Bearbeiten'),
    ('btn.delete',                'Löschen'),
    ('confirm.replace_waypoints', 'Dadurch werden die aktuellen Wegpunkte durch die ausgewählte Datei ersetzt. Fortfahren?'),
    ('confirm.replace_task',      'Dadurch wird die aktuelle Aufgabe ersetzt. Fortfahren?'),
    ('task.no_start_before',      'Nicht vor Start (UTC)'),
    ('task.task_time',            'Aufgabenzeit')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Czech
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'cs', val FROM (VALUES
    ('btn.edit',                  'Upravit'),
    ('btn.delete',                'Smazat'),
    ('confirm.replace_waypoints', 'Tím se nahradí aktuální trasové body vybraným souborem. Pokračovat?'),
    ('confirm.replace_task',      'Tím se nahradí aktuální úloha. Pokračovat?'),
    ('task.no_start_before',      'Nestartovat před (UTC)'),
    ('task.task_time',            'Čas úlohy')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;
