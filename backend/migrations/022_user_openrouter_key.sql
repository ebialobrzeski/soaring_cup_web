-- Migration 022: User OpenRouter API key (BYOK)
-- Allows premium users to supply their own OpenRouter API key for AI Planner,
-- shifting inference costs to the user.  The key is stored encrypted (Fernet).

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS openrouter_key_enc TEXT;

-- ─────────────────────────────────────────────────────────────────────────────
-- i18n keys
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translation_keys (key, default_value, category, description) VALUES
    ('settings.api_key_title',    'API Key Settings',                                'settings', 'API key settings dialog title'),
    ('settings.openrouter_label', 'OpenRouter API Key',                              'settings', 'Label for OpenRouter key input'),
    ('settings.openrouter_help',  'Provide your own OpenRouter key to use AI Planner. Get one at openrouter.ai/keys', 'settings', 'Help text for key input'),
    ('settings.key_saved',        'API key saved successfully.',                     'settings', 'Success toast after saving key'),
    ('settings.key_removed',      'API key removed.',                                'settings', 'Toast after removing key'),
    ('settings.key_invalid',      'Invalid API key format.',                         'settings', 'Validation error'),
    ('settings.save_key_btn',     'Save Key',                                        'settings', 'Save key button'),
    ('settings.remove_key_btn',   'Remove Key',                                      'settings', 'Remove key button'),
    ('settings.key_status_set',   'Your own API key is configured.',                 'settings', 'Status when key is set'),
    ('settings.key_status_unset', 'No API key configured.',                          'settings', 'Status when no key is set'),
    ('aip.byok_required',         'An OpenRouter API key is required to use the AI Planner. Add one in Settings.', 'aip', 'Notice when no key and no server key'),
    ('header.settings',           'Settings',                                        'header',   'Settings button tooltip'),
    ('aip.key_missing_title',     'API Key Required',                                'aip',      'Title for missing key notice'),
    ('settings.key_mask',         'Key configured (ending …{0})',                    'settings', 'Masked key display with last 4 chars')
ON CONFLICT (key) DO NOTHING;

-- Polish
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'pl', val FROM (VALUES
    ('settings.api_key_title',    'Ustawienia klucza API'),
    ('settings.openrouter_label', 'Klucz API OpenRouter'),
    ('settings.openrouter_help',  'Podaj własny klucz OpenRouter, aby korzystać z AI Planner. Uzyskaj go na openrouter.ai/keys'),
    ('settings.key_saved',        'Klucz API został zapisany.'),
    ('settings.key_removed',      'Klucz API został usunięty.'),
    ('settings.key_invalid',      'Nieprawidłowy format klucza API.'),
    ('settings.save_key_btn',     'Zapisz klucz'),
    ('settings.remove_key_btn',   'Usuń klucz'),
    ('settings.key_status_set',   'Twój klucz API jest skonfigurowany.'),
    ('settings.key_status_unset', 'Brak skonfigurowanego klucza API.'),
    ('aip.byok_required',         'Klucz API OpenRouter jest wymagany do korzystania z AI Planner. Dodaj go w Ustawieniach.'),
    ('header.settings',           'Ustawienia'),
    ('aip.key_missing_title',     'Wymagany klucz API'),
    ('settings.key_mask',         'Klucz skonfigurowany (kończy się na …{0})')
) AS t(k, val)
JOIN translation_keys ON translation_keys.key = t.k
ON CONFLICT DO NOTHING;

-- German
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'de', val FROM (VALUES
    ('settings.api_key_title',    'API-Schlüssel Einstellungen'),
    ('settings.openrouter_label', 'OpenRouter API-Schlüssel'),
    ('settings.openrouter_help',  'Geben Sie Ihren eigenen OpenRouter-Schlüssel ein, um den AI Planner zu verwenden. Erhalten Sie einen unter openrouter.ai/keys'),
    ('settings.key_saved',        'API-Schlüssel erfolgreich gespeichert.'),
    ('settings.key_removed',      'API-Schlüssel entfernt.'),
    ('settings.key_invalid',      'Ungültiges API-Schlüssel-Format.'),
    ('settings.save_key_btn',     'Schlüssel speichern'),
    ('settings.remove_key_btn',   'Schlüssel entfernen'),
    ('settings.key_status_set',   'Ihr eigener API-Schlüssel ist konfiguriert.'),
    ('settings.key_status_unset', 'Kein API-Schlüssel konfiguriert.'),
    ('aip.byok_required',         'Ein OpenRouter API-Schlüssel ist erforderlich, um den AI Planner zu verwenden. Fügen Sie einen in den Einstellungen hinzu.'),
    ('header.settings',           'Einstellungen'),
    ('aip.key_missing_title',     'API-Schlüssel erforderlich'),
    ('settings.key_mask',         'Schlüssel konfiguriert (endet auf …{0})')
) AS t(k, val)
JOIN translation_keys ON translation_keys.key = t.k
ON CONFLICT DO NOTHING;

-- Czech
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'cs', val FROM (VALUES
    ('settings.api_key_title',    'Nastavení API klíče'),
    ('settings.openrouter_label', 'API klíč OpenRouter'),
    ('settings.openrouter_help',  'Zadejte svůj vlastní klíč OpenRouter pro použití AI Planner. Získejte ho na openrouter.ai/keys'),
    ('settings.key_saved',        'API klíč byl úspěšně uložen.'),
    ('settings.key_removed',      'API klíč byl odstraněn.'),
    ('settings.key_invalid',      'Neplatný formát API klíče.'),
    ('settings.save_key_btn',     'Uložit klíč'),
    ('settings.remove_key_btn',   'Odstranit klíč'),
    ('settings.key_status_set',   'Váš vlastní API klíč je nakonfigurován.'),
    ('settings.key_status_unset', 'Žádný API klíč není nakonfigurován.'),
    ('aip.byok_required',         'Pro použití AI Planner je vyžadován API klíč OpenRouter. Přidejte ho v Nastavení.'),
    ('header.settings',           'Nastavení'),
    ('aip.key_missing_title',     'Vyžadován API klíč'),
    ('settings.key_mask',         'Klíč nakonfigurován (končí na …{0})')
) AS t(k, val)
JOIN translation_keys ON translation_keys.key = t.k
ON CONFLICT DO NOTHING;
