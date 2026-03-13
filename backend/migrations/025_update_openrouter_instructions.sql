-- Migration 025: Updated OpenRouter API key instructions with accurate steps

-- Insert new i18n key for the HTML tooltip instructions
INSERT INTO translation_keys (key, default_value, category, description) VALUES
    ('settings.apikey_instructions',
     '<strong>How to get your API key:</strong><br>1. Go to <a href="https://openrouter.ai" target="_blank" rel="noopener">openrouter.ai</a> and create a free account<br>2. Go to <strong>Settings → API Keys</strong><br>3. Click <strong>Create Key</strong> and name it (e.g. <em>gliding_forecast</em>)<br>4. Copy the key (starts with <code>sk-or-v1-</code>) and paste it here<br>5. Add credits — $5 is enough for hundreds of flight plans<br><br><em>Your key is encrypted and stored securely. You control your own AI costs directly through OpenRouter.</em>',
     'settings', 'HTML tooltip with step-by-step instructions for getting an OpenRouter API key')
ON CONFLICT (key) DO NOTHING;

-- Update help text (short version under the input)
UPDATE translation_keys SET default_value = 'Provide your own OpenRouter key to use AI Planner. Get one free at openrouter.ai → Settings → API Keys.'
WHERE key = 'settings.openrouter_help';

-- ── English ──────────────────────────────────────────────────────────────────
-- (English uses default_value from translation_keys as fallback, but add explicit row)

-- Update short help text
UPDATE translations SET value = 'Provide your own OpenRouter key to use AI Planner. Get one free at openrouter.ai → Settings → API Keys.'
FROM translation_keys
WHERE translations.key_id = translation_keys.id
  AND translation_keys.key = 'settings.openrouter_help'
  AND translations.language_code = 'en';

-- ── Polish ───────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'pl', val FROM (VALUES
    ('settings.apikey_instructions',
     '<strong>Jak uzyskać klucz API:</strong><br>1. Przejdź na <a href="https://openrouter.ai" target="_blank" rel="noopener">openrouter.ai</a> i załóż darmowe konto<br>2. Przejdź do <strong>Settings → API Keys</strong><br>3. Kliknij <strong>Create Key</strong> i nadaj mu nazwę (np. <em>gliding_forecast</em>)<br>4. Skopiuj klucz (zaczyna się od <code>sk-or-v1-</code>) i wklej go tutaj<br>5. Doładuj konto — $5 wystarczy na setki planów lotów<br><br><em>Twój klucz jest szyfrowany i przechowywany bezpiecznie. Kontrolujesz koszty AI bezpośrednio przez OpenRouter.</em>')
) AS t(k, val)
JOIN translation_keys ON translation_keys.key = t.k
ON CONFLICT DO NOTHING;

UPDATE translations SET value = 'Podaj własny klucz OpenRouter, aby korzystać z AI Planner. Uzyskaj go za darmo na openrouter.ai → Settings → API Keys.'
FROM translation_keys
WHERE translations.key_id = translation_keys.id
  AND translation_keys.key = 'settings.openrouter_help'
  AND translations.language_code = 'pl';

-- ── German ───────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'de', val FROM (VALUES
    ('settings.apikey_instructions',
     '<strong>So erhalten Sie Ihren API-Schlüssel:</strong><br>1. Gehen Sie zu <a href="https://openrouter.ai" target="_blank" rel="noopener">openrouter.ai</a> und erstellen Sie ein kostenloses Konto<br>2. Gehen Sie zu <strong>Settings → API Keys</strong><br>3. Klicken Sie auf <strong>Create Key</strong> und vergeben Sie einen Namen (z.B. <em>gliding_forecast</em>)<br>4. Kopieren Sie den Schlüssel (beginnt mit <code>sk-or-v1-</code>) und fügen Sie ihn hier ein<br>5. Guthaben aufladen — $5 reichen für Hunderte von Flugplänen<br><br><em>Ihr Schlüssel wird verschlüsselt und sicher gespeichert. Sie kontrollieren Ihre KI-Kosten direkt über OpenRouter.</em>')
) AS t(k, val)
JOIN translation_keys ON translation_keys.key = t.k
ON CONFLICT DO NOTHING;

UPDATE translations SET value = 'Geben Sie Ihren eigenen OpenRouter-Schlüssel ein, um den AI Planner zu verwenden. Erhalten Sie einen kostenlos unter openrouter.ai → Settings → API Keys.'
FROM translation_keys
WHERE translations.key_id = translation_keys.id
  AND translation_keys.key = 'settings.openrouter_help'
  AND translations.language_code = 'de';

-- ── Czech ────────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'cs', val FROM (VALUES
    ('settings.apikey_instructions',
     '<strong>Jak získat API klíč:</strong><br>1. Přejděte na <a href="https://openrouter.ai" target="_blank" rel="noopener">openrouter.ai</a> a vytvořte si bezplatný účet<br>2. Přejděte do <strong>Settings → API Keys</strong><br>3. Klikněte na <strong>Create Key</strong> a pojmenujte ho (např. <em>gliding_forecast</em>)<br>4. Zkopírujte klíč (začíná na <code>sk-or-v1-</code>) a vložte ho sem<br>5. Dobijte kredit — $5 stačí na stovky letových plánů<br><br><em>Váš klíč je šifrován a bezpečně uložen. Náklady na AI kontrolujete přímo přes OpenRouter.</em>')
) AS t(k, val)
JOIN translation_keys ON translation_keys.key = t.k
ON CONFLICT DO NOTHING;

UPDATE translations SET value = 'Zadejte svůj vlastní klíč OpenRouter pro použití AI Planner. Získejte ho zdarma na openrouter.ai → Settings → API Keys.'
FROM translation_keys
WHERE translations.key_id = translation_keys.id
  AND translation_keys.key = 'settings.openrouter_help'
  AND translations.language_code = 'cs';
