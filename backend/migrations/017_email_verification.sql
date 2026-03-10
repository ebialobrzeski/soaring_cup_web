-- Migration 017: Email verification
-- Adds OTP-based email verification to user accounts.
-- Existing users are pre-marked as verified so they are not affected.

-- ─────────────────────────────────────────────────────────────────────────────
-- Schema changes
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS email_verified            BOOLEAN      NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS verification_code_hash    TEXT,
    ADD COLUMN IF NOT EXISTS verification_code_expires TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS verification_attempts     INTEGER      NOT NULL DEFAULT 0;

-- All existing accounts are considered already verified
UPDATE users SET email_verified = TRUE WHERE email_verified = FALSE;

-- ─────────────────────────────────────────────────────────────────────────────
-- i18n keys
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translation_keys (key, default_value, category, description) VALUES
    ('dlg.verify_title',       'Verify your email',                              'dlg',  'Verify email dialog title'),
    ('auth.verify_sent',       'We sent a 6-digit code to',                      'auth', 'Verification code sent prefix'),
    ('auth.verify_enter',      'Enter the 6-digit code',                         'auth', 'Enter code label'),
    ('auth.verify_btn',        'Verify',                                         'auth', 'Verify button'),
    ('auth.resend_code',       'Resend code',                                    'auth', 'Resend code link'),
    ('auth.code_invalid',      'Invalid code. Please try again.',               'auth', 'Invalid code error'),
    ('auth.code_expired',      'The code has expired. Please request a new one.','auth', 'Expired code error'),
    ('auth.too_many_attempts', 'Too many attempts. Please request a new code.',  'auth', 'Too many attempts error'),
    ('admin.col_verified',     'Verified',                                       'admin','Column: email verified status')
ON CONFLICT (key) DO NOTHING;

-- Polish
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'pl', val FROM (VALUES
    ('dlg.verify_title',       'Zweryfikuj swój email'),
    ('auth.verify_sent',       'Wysłaliśmy 6-cyfrowy kod na adres'),
    ('auth.verify_enter',      'Wpisz 6-cyfrowy kod'),
    ('auth.verify_btn',        'Zweryfikuj'),
    ('auth.resend_code',       'Wyślij kod ponownie'),
    ('auth.code_invalid',      'Nieprawidłowy kod. Spróbuj ponownie.'),
    ('auth.code_expired',      'Kod wygasł. Poproś o nowy.'),
    ('auth.too_many_attempts', 'Zbyt wiele prób. Poproś o nowy kod.')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;

-- German
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'de', val FROM (VALUES
    ('dlg.verify_title',       'E-Mail verifizieren'),
    ('auth.verify_sent',       'Wir haben einen 6-stelligen Code gesendet an'),
    ('auth.verify_enter',      'Gib den 6-stelligen Code ein'),
    ('auth.verify_btn',        'Verifizieren'),
    ('auth.resend_code',       'Code erneut senden'),
    ('auth.code_invalid',      'Ungültiger Code. Bitte erneut versuchen.'),
    ('auth.code_expired',      'Der Code ist abgelaufen. Bitte neuen Code anfordern.'),
    ('auth.too_many_attempts', 'Zu viele Versuche. Bitte neuen Code anfordern.')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;

-- Czech
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'cs', val FROM (VALUES
    ('dlg.verify_title',       'Ověřte svůj e-mail'),
    ('auth.verify_sent',       'Zaslali jsme 6místný kód na adresu'),
    ('auth.verify_enter',      'Zadejte 6místný kód'),
    ('auth.verify_btn',        'Ověřit'),
    ('auth.resend_code',       'Znovu odeslat kód'),
    ('auth.code_invalid',      'Neplatný kód. Zkuste to znovu.'),
    ('auth.code_expired',      'Platnost kódu vypršela. Požádejte o nový.'),
    ('auth.too_many_attempts', 'Příliš mnoho pokusů. Požádejte o nový kód.')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;
