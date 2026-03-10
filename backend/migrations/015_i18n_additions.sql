-- Migration 015: Additional i18n translation keys
-- Covers: app subtitle, login/register dialogs, My Content columns/settings,
-- admin panel columns, map popup labels.

-- ─────────────────────────────────────────────────────────────────────────────
-- New translation keys (default values are English)
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translation_keys (key, default_value, category, description) VALUES
    -- App header
    ('header.subtitle',     'Soaring Task & Waypoint Editor',          'header', 'App subtitle below logo'),
    -- Login / Register dialogs
    ('dlg.login_title',     'Log in to GlidePlan',                     'dlg',    'Login dialog title'),
    ('dlg.register_title',  'Create Account',                          'dlg',    'Register dialog title'),
    -- Form field labels
    ('form.email',          'Email',                                   'form',   'Email field label'),
    ('form.password',       'Password',                                'form',   'Password field label'),
    ('form.display_name',   'Display Name',                            'form',   'Display name field label'),
    ('form.confirm_password','Confirm Password',                       'form',   'Confirm password field label'),
    ('form.password_hint',  '(min 8 chars)',                           'form',   'Password minimum length hint'),
    -- Auth links
    ('auth.no_account',     'Don''t have an account?',                 'auth',   'Link to register from login'),
    ('auth.have_account',   'Already have an account?',                'auth',   'Link to login from register'),
    -- My Content settings tab
    ('mc.settings',         'Settings',                                'my_content', 'My Content: settings sub-tab'),
    ('mc.language_pref',    'Preferred Language',                      'my_content', 'Preferred language label'),
    ('mc.language_pref_desc','Applied automatically when you log in.', 'my_content', 'Preferred language description'),
    ('mc.save_settings',    'Save Settings',                           'my_content', 'Save settings button'),
    ('mc.settings_saved',   'Settings saved.',                         'my_content', 'Settings saved confirmation'),
    -- My Content table column headers
    ('mc.col_name',         'Name',                                    'my_content', 'Column: file/task name'),
    ('mc.col_waypoints',    'Waypoints',                               'my_content', 'Column: waypoint count'),
    ('mc.col_countries',    'Countries',                               'my_content', 'Column: country codes'),
    ('mc.col_visibility',   'Visibility',                              'my_content', 'Column: public/private badge'),
    ('mc.col_saved',        'Saved',                                   'my_content', 'Column: save date'),
    ('mc.col_points',       'Points',                                  'my_content', 'Column: task point count'),
    -- Admin column headers (re-used where possible)
    ('admin.col_tier',      'Tier',                                    'admin', 'Column: user tier'),
    ('admin.col_active',    'Active',                                  'admin', 'Column: is user active'),
    ('admin.col_files',     'Files',                                   'admin', 'Column: file count'),
    ('admin.col_registered','Registered',                              'admin', 'Column: registration date'),
    ('admin.select_user_hint', 'Select a user from the Users tab to view their content here.', 'admin', 'Hint in content sub-tab'),
    ('admin.back_to_users', 'Back to users',                           'admin', 'Back to users button'),
    -- Map popup labels
    ('popup.type',          'Type',          'popup', 'Popup: waypoint type label'),
    ('popup.identification','Identification','popup', 'Popup: identification section heading'),
    ('popup.position',      'Position',      'popup', 'Popup: position section heading'),
    ('popup.decimal',       'Decimal',       'popup', 'Popup: decimal coordinates label'),
    ('popup.airfield_info', 'Airfield Information', 'popup', 'Popup: airfield section heading'),
    ('popup.runway_direction','Runway Direction','popup', 'Popup: runway direction label'),
    ('popup.runway_length', 'Runway Length', 'popup', 'Popup: runway length label'),
    ('popup.runway_width',  'Runway Width',  'popup', 'Popup: runway width label'),
    ('popup.radio_frequency','Radio Frequency','popup','Popup: radio frequency label'),
    ('popup.description',   'Description',   'popup', 'Popup: description section heading')
ON CONFLICT (key) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Polish translations
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'pl', val FROM (VALUES
    ('header.subtitle',      'Edytor zadań i punktów nawigacyjnych'),
    ('dlg.login_title',      'Zaloguj się do GlidePlan'),
    ('dlg.register_title',   'Utwórz konto'),
    ('form.email',           'Email'),
    ('form.password',        'Hasło'),
    ('form.display_name',    'Nazwa wyświetlana'),
    ('form.confirm_password','Potwierdź hasło'),
    ('form.password_hint',   '(min. 8 znaków)'),
    ('auth.no_account',      'Nie masz konta?'),
    ('auth.have_account',    'Masz już konto?'),
    ('mc.settings',          'Ustawienia'),
    ('mc.language_pref',     'Preferowany język'),
    ('mc.language_pref_desc','Stosowany automatycznie po zalogowaniu.'),
    ('mc.save_settings',     'Zapisz ustawienia'),
    ('mc.settings_saved',    'Ustawienia zapisane.'),
    ('mc.col_name',          'Nazwa'),
    ('mc.col_waypoints',     'Punkty'),
    ('mc.col_countries',     'Kraje'),
    ('mc.col_visibility',    'Widoczność'),
    ('mc.col_saved',         'Zapisano'),
    ('mc.col_points',        'Punkty zadania'),
    ('admin.col_tier',       'Poziom'),
    ('admin.col_active',     'Aktywny'),
    ('admin.col_files',      'Pliki'),
    ('admin.col_registered', 'Rejestracja'),
    ('admin.select_user_hint','Wybierz użytkownika z zakładki Użytkownicy, aby zobaczyć jego treści.'),
    ('admin.back_to_users',  'Powrót do użytkowników'),
    ('popup.type',           'Typ'),
    ('popup.identification', 'Identyfikacja'),
    ('popup.position',       'Pozycja'),
    ('popup.decimal',        'Dziesiętnie'),
    ('popup.airfield_info',  'Informacje o lotnisku'),
    ('popup.runway_direction','Kierunek pasa startowego'),
    ('popup.runway_length',  'Długość pasa startowego'),
    ('popup.runway_width',   'Szerokość pasa startowego'),
    ('popup.radio_frequency','Częstotliwość radiowa'),
    ('popup.description',    'Opis')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- German translations
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'de', val FROM (VALUES
    ('header.subtitle',      'Strecken- und Wegpunkteditor'),
    ('dlg.login_title',      'Bei GlidePlan anmelden'),
    ('dlg.register_title',   'Konto erstellen'),
    ('form.email',           'E-Mail'),
    ('form.password',        'Passwort'),
    ('form.display_name',    'Anzeigename'),
    ('form.confirm_password','Passwort bestätigen'),
    ('form.password_hint',   '(mind. 8 Zeichen)'),
    ('auth.no_account',      'Noch kein Konto?'),
    ('auth.have_account',    'Bereits ein Konto?'),
    ('mc.settings',          'Einstellungen'),
    ('mc.language_pref',     'Bevorzugte Sprache'),
    ('mc.language_pref_desc','Wird nach der Anmeldung automatisch angewendet.'),
    ('mc.save_settings',     'Einstellungen speichern'),
    ('mc.settings_saved',    'Einstellungen gespeichert.'),
    ('mc.col_name',          'Name'),
    ('mc.col_waypoints',     'Wegpunkte'),
    ('mc.col_countries',     'Länder'),
    ('mc.col_visibility',    'Sichtbarkeit'),
    ('mc.col_saved',         'Gespeichert'),
    ('mc.col_points',        'Aufgabenpunkte'),
    ('admin.col_tier',       'Stufe'),
    ('admin.col_active',     'Aktiv'),
    ('admin.col_files',      'Dateien'),
    ('admin.col_registered', 'Registriert'),
    ('admin.select_user_hint','Benutzer im Tab Benutzer auswählen, um Inhalte anzuzeigen.'),
    ('admin.back_to_users',  'Zurück zu Benutzern'),
    ('popup.type',           'Typ'),
    ('popup.identification', 'Identifikation'),
    ('popup.position',       'Position'),
    ('popup.decimal',        'Dezimal'),
    ('popup.airfield_info',  'Flugplatzinformationen'),
    ('popup.runway_direction','Pistenrichtung'),
    ('popup.runway_length',  'Pistenlänge'),
    ('popup.runway_width',   'Pistenbreite'),
    ('popup.radio_frequency','Funkfrequenz'),
    ('popup.description',    'Beschreibung')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Czech translations
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'cs', val FROM (VALUES
    ('header.subtitle',      'Editor letových tras a navigačních bodů'),
    ('dlg.login_title',      'Přihlásit se do GlidePlan'),
    ('dlg.register_title',   'Vytvořit účet'),
    ('form.email',           'E-mail'),
    ('form.password',        'Heslo'),
    ('form.display_name',    'Zobrazované jméno'),
    ('form.confirm_password','Potvrdit heslo'),
    ('form.password_hint',   '(min. 8 znaků)'),
    ('auth.no_account',      'Nemáte účet?'),
    ('auth.have_account',    'Již máte účet?'),
    ('mc.settings',          'Nastavení'),
    ('mc.language_pref',     'Preferovaný jazyk'),
    ('mc.language_pref_desc','Použije se automaticky po přihlášení.'),
    ('mc.save_settings',     'Uložit nastavení'),
    ('mc.settings_saved',    'Nastavení uloženo.'),
    ('mc.col_name',          'Název'),
    ('mc.col_waypoints',     'Body'),
    ('mc.col_countries',     'Země'),
    ('mc.col_visibility',    'Viditelnost'),
    ('mc.col_saved',         'Uloženo'),
    ('mc.col_points',        'Body trasy'),
    ('admin.col_tier',       'Úroveň'),
    ('admin.col_active',     'Aktivní'),
    ('admin.col_files',      'Soubory'),
    ('admin.col_registered', 'Registrace'),
    ('admin.select_user_hint','Vyberte uživatele ze záložky Uživatelé pro zobrazení jeho obsahu.'),
    ('admin.back_to_users',  'Zpět na uživatele'),
    ('popup.type',           'Typ'),
    ('popup.identification', 'Identifikace'),
    ('popup.position',       'Poloha'),
    ('popup.decimal',        'Desetinně'),
    ('popup.airfield_info',  'Informace o letišti'),
    ('popup.runway_direction','Směr dráhy'),
    ('popup.runway_length',  'Délka dráhy'),
    ('popup.runway_width',   'Šířka dráhy'),
    ('popup.radio_frequency','Radiofrekvence'),
    ('popup.description',    'Popis')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;
