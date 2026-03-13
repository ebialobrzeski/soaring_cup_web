-- Migration 023: Rename "My Content" → "My Account" in nav tab label
-- Update all four language translations for nav.my_content

-- Update the base English value in translation_keys
UPDATE translation_keys SET default_value = 'My Account'
WHERE key = 'nav.my_content';

-- Update per-language translations via key_id join
UPDATE translations SET value = 'My Account'
FROM translation_keys
WHERE translations.key_id = translation_keys.id
  AND translation_keys.key = 'nav.my_content'
  AND translations.language_code = 'en';

UPDATE translations SET value = 'Moje konto'
FROM translation_keys
WHERE translations.key_id = translation_keys.id
  AND translation_keys.key = 'nav.my_content'
  AND translations.language_code = 'pl';

UPDATE translations SET value = 'Mein Konto'
FROM translation_keys
WHERE translations.key_id = translation_keys.id
  AND translation_keys.key = 'nav.my_content'
  AND translations.language_code = 'de';

UPDATE translations SET value = 'Můj účet'
FROM translation_keys
WHERE translations.key_id = translation_keys.id
  AND translation_keys.key = 'nav.my_content'
  AND translations.language_code = 'cs';
