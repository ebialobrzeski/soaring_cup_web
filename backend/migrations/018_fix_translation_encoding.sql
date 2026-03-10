-- Migration 018: Fix UTF-8 encoding corruption in migration 016 translations (PL, CS)

-- Polish
UPDATE translations SET value = 'Wiatr i prędkość'
WHERE key_id = (SELECT id FROM translation_keys WHERE key = 'task.wind_speed_card')
  AND language_code = 'pl';

UPDATE translations SET value = 'Szczegóły zadania'
WHERE key_id = (SELECT id FROM translation_keys WHERE key = 'task.details_card')
  AND language_code = 'pl';

-- Czech
UPDATE translations SET value = 'Vítr a rychlost'
WHERE key_id = (SELECT id FROM translation_keys WHERE key = 'task.wind_speed_card')
  AND language_code = 'cs';

UPDATE translations SET value = 'Detaily úlohy'
WHERE key_id = (SELECT id FROM translation_keys WHERE key = 'task.details_card')
  AND language_code = 'cs';
