-- Migration 013: Internationalisation (i18n) — languages, keys, translations

-- Supported languages
CREATE TABLE IF NOT EXISTS languages (
    code        VARCHAR(10)  PRIMARY KEY,            -- 'en', 'pl', 'de', 'cs'
    name        VARCHAR(100) NOT NULL,               -- 'English', 'Polish' …
    native_name VARCHAR(100) NOT NULL,               -- 'English', 'Polski' …
    flag_emoji  VARCHAR(10),
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    sort_order  INTEGER      NOT NULL DEFAULT 0
);

-- Canonical translation keys with English fallback
CREATE TABLE IF NOT EXISTS translation_keys (
    id            SERIAL       PRIMARY KEY,
    key           VARCHAR(255) UNIQUE NOT NULL,      -- 'nav.map_view', 'btn.save' …
    default_value TEXT         NOT NULL,             -- English string (fallback)
    category      VARCHAR(100),                      -- 'nav', 'btn', 'dialog', 'form' …
    description   TEXT                               -- context hint for translators
);

-- Per-language translation values
CREATE TABLE IF NOT EXISTS translations (
    id            SERIAL       PRIMARY KEY,
    key_id        INTEGER      NOT NULL REFERENCES translation_keys(id) ON DELETE CASCADE,
    language_code VARCHAR(10)  NOT NULL REFERENCES languages(code)      ON DELETE CASCADE,
    value         TEXT         NOT NULL,
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (key_id, language_code)
);

CREATE INDEX IF NOT EXISTS idx_translations_lang     ON translations(language_code);
CREATE INDEX IF NOT EXISTS idx_transl_keys_category  ON translation_keys(category);

-- Optional: store preferred language on the user account
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(10) REFERENCES languages(code);

-- ─────────────────────────────────────────────────────────────────────────────
-- Seed: languages
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO languages (code, name, native_name, flag_emoji, sort_order) VALUES
    ('en', 'English', 'English',  '🇬🇧', 1),
    ('pl', 'Polish',  'Polski',   '🇵🇱', 2),
    ('de', 'German',  'Deutsch',  '🇩🇪', 3),
    ('cs', 'Czech',   'Čeština',  '🇨🇿', 4)
ON CONFLICT (code) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Seed: translation keys + English defaults
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translation_keys (key, default_value, category, description) VALUES
    -- Navigation tabs
    ('nav.map_view',       'Map View',       'nav', 'Main tab: map view'),
    ('nav.list_view',      'List View',      'nav', 'Main tab: waypoint list'),
    ('nav.task_planner',   'Task Planner',   'nav', 'Main tab: task planner'),
    ('nav.ai_planner',     'AI Planner',     'nav', 'Main tab: AI planner'),
    ('nav.my_content',     'My Content',     'nav', 'Main tab: user content manager'),
    ('nav.admin',          'Admin',          'nav', 'Main tab: admin panel'),
    -- Header / auth
    ('header.login',       'Log in',         'header', 'Login button'),
    ('header.signup',      'Sign up',        'header', 'Register button'),
    ('header.logout',      'Log out',        'header', 'Logout button'),
    ('header.language',    'Language',       'header', 'Language selector label'),
    -- Common buttons
    ('btn.save',           'Save',           'btn', NULL),
    ('btn.cancel',         'Cancel',         'btn', NULL),
    ('btn.delete',         'Delete',         'btn', NULL),
    ('btn.close',          'Close',          'btn', NULL),
    ('btn.load',           'Load',           'btn', NULL),
    ('btn.upload',         'Upload',         'btn', NULL),
    ('btn.download',       'Download',       'btn', NULL),
    ('btn.search',         'Search',         'btn', NULL),
    ('btn.browse',         'Browse',         'btn', NULL),
    ('btn.add',            'Add',            'btn', NULL),
    ('btn.edit',           'Edit',           'btn', NULL),
    ('btn.import',         'Import',         'btn', NULL),
    ('btn.export',         'Export',         'btn', NULL),
    ('btn.refresh',        'Refresh',        'btn', NULL),
    ('btn.generate',       'Generate Task',  'btn', 'AI planner generate button'),
    -- My Content sub-tabs
    ('mc.waypoint_files',  'Waypoint Files', 'my_content', NULL),
    ('mc.tasks',           'Tasks',          'my_content', NULL),
    ('mc.custom_gliders',  'Custom Gliders', 'my_content', NULL),
    ('mc.add_glider',      'Add Glider',     'my_content', NULL),
    ('mc.no_files',        'No waypoint files yet.',   'my_content', 'Empty state message'),
    ('mc.no_tasks',        'No saved tasks yet.',       'my_content', 'Empty state message'),
    ('mc.no_gliders',      'No custom gliders yet.',    'my_content', 'Empty state message'),
    -- Browse dialog
    ('browse.title_waypoints', 'Browse Waypoint Files', 'browse', NULL),
    ('browse.title_tasks',     'Browse Tasks',          'browse', NULL),
    ('browse.search_placeholder', 'Search…',           'browse', NULL),
    ('browse.no_results',        'No results found.',  'browse', NULL),
    -- Task planner
    ('task.new_task',      'New Task',       'task', NULL),
    ('task.save_task',     'Save Task',      'task', NULL),
    ('task.load_task',     'Load Task',      'task', NULL),
    ('task.total_distance','Total distance', 'task', NULL),
    -- AI planner
    ('aip.title',              'AI Task Planner',    'aip', NULL),
    ('aip.target_distance',    'Target Distance',    'aip', NULL),
    ('aip.safety_profile',     'Safety Profile',     'aip', NULL),
    ('aip.safety_conservative','Conservative',       'aip', NULL),
    ('aip.safety_standard',    'Standard',           'aip', NULL),
    ('aip.safety_aggressive',  'Aggressive',         'aip', NULL),
    ('aip.soaring_mode',       'Soaring Mode',       'aip', NULL),
    ('aip.soaring_thermal',    'Thermal',            'aip', NULL),
    ('aip.soaring_ridge',      'Ridge',              'aip', NULL),
    ('aip.soaring_wave',       'Wave',               'aip', NULL),
    -- Map
    ('map.add_waypoint',   'Add Waypoint',   'map', NULL),
    ('map.search_places',  'Search places…', 'map', NULL),
    -- Confirm/status messages
    ('confirm.delete',     'Are you sure you want to delete this?',  'confirm', NULL),
    ('status.loading',     'Loading…',       'status', NULL),
    ('status.saving',      'Saving…',        'status', NULL),
    ('status.saved',       'Saved',          'status', NULL),
    ('status.error',       'An error occurred.', 'status', NULL),
    ('status.success',     'Success',        'status', NULL)
ON CONFLICT (key) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Seed: Polish translations
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'pl', val FROM (VALUES
    ('nav.map_view',           'Widok mapy'),
    ('nav.list_view',          'Widok listy'),
    ('nav.task_planner',       'Planista zadań'),
    ('nav.ai_planner',         'Planista AI'),
    ('nav.my_content',         'Moje treści'),
    ('nav.admin',              'Admin'),
    ('header.login',           'Zaloguj się'),
    ('header.signup',          'Zarejestruj się'),
    ('header.logout',          'Wyloguj się'),
    ('header.language',        'Język'),
    ('btn.save',               'Zapisz'),
    ('btn.cancel',             'Anuluj'),
    ('btn.delete',             'Usuń'),
    ('btn.close',              'Zamknij'),
    ('btn.load',               'Wczytaj'),
    ('btn.upload',             'Prześlij'),
    ('btn.download',           'Pobierz'),
    ('btn.search',             'Szukaj'),
    ('btn.browse',             'Przeglądaj'),
    ('btn.add',                'Dodaj'),
    ('btn.edit',               'Edytuj'),
    ('btn.import',             'Importuj'),
    ('btn.export',             'Eksportuj'),
    ('btn.refresh',            'Odśwież'),
    ('btn.generate',           'Generuj zadanie'),
    ('mc.waypoint_files',      'Pliki punktów nawigacyjnych'),
    ('mc.tasks',               'Zadania'),
    ('mc.custom_gliders',      'Własne szybowce'),
    ('mc.add_glider',          'Dodaj szybowiec'),
    ('mc.no_files',            'Brak plików punktów nawigacyjnych.'),
    ('mc.no_tasks',            'Brak zapisanych zadań.'),
    ('mc.no_gliders',          'Brak własnych szybowców.'),
    ('browse.title_waypoints', 'Przeglądaj pliki punktów'),
    ('browse.title_tasks',     'Przeglądaj zadania'),
    ('browse.search_placeholder', 'Szukaj…'),
    ('browse.no_results',      'Brak wyników.'),
    ('task.new_task',          'Nowe zadanie'),
    ('task.save_task',         'Zapisz zadanie'),
    ('task.load_task',         'Wczytaj zadanie'),
    ('task.total_distance',    'Łączna odległość'),
    ('aip.title',              'Planista zadań AI'),
    ('aip.target_distance',    'Docelowa odległość'),
    ('aip.safety_profile',     'Profil bezpieczeństwa'),
    ('aip.safety_conservative','Konserwatywny'),
    ('aip.safety_standard',    'Standardowy'),
    ('aip.safety_aggressive',  'Agresywny'),
    ('aip.soaring_mode',       'Tryb szybowania'),
    ('aip.soaring_thermal',    'Kominy termiczne'),
    ('aip.soaring_ridge',      'Zbocza'),
    ('aip.soaring_wave',       'Fala'),
    ('map.add_waypoint',       'Dodaj punkt'),
    ('map.search_places',      'Szukaj miejsc…'),
    ('confirm.delete',         'Czy na pewno chcesz to usunąć?'),
    ('status.loading',         'Ładowanie…'),
    ('status.saving',          'Zapisywanie…'),
    ('status.saved',           'Zapisano'),
    ('status.error',           'Wystąpił błąd.'),
    ('status.success',         'Sukces')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Seed: German translations
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'de', val FROM (VALUES
    ('nav.map_view',           'Kartenansicht'),
    ('nav.list_view',          'Listenansicht'),
    ('nav.task_planner',       'Aufgabenplaner'),
    ('nav.ai_planner',         'KI-Planer'),
    ('nav.my_content',         'Meine Inhalte'),
    ('nav.admin',              'Admin'),
    ('header.login',           'Anmelden'),
    ('header.signup',          'Registrieren'),
    ('header.logout',          'Abmelden'),
    ('header.language',        'Sprache'),
    ('btn.save',               'Speichern'),
    ('btn.cancel',             'Abbrechen'),
    ('btn.delete',             'Löschen'),
    ('btn.close',              'Schließen'),
    ('btn.load',               'Laden'),
    ('btn.upload',             'Hochladen'),
    ('btn.download',           'Herunterladen'),
    ('btn.search',             'Suchen'),
    ('btn.browse',             'Durchsuchen'),
    ('btn.add',                'Hinzufügen'),
    ('btn.edit',               'Bearbeiten'),
    ('btn.import',             'Importieren'),
    ('btn.export',             'Exportieren'),
    ('btn.refresh',            'Aktualisieren'),
    ('btn.generate',           'Aufgabe generieren'),
    ('mc.waypoint_files',      'Wegpunktdateien'),
    ('mc.tasks',               'Aufgaben'),
    ('mc.custom_gliders',      'Eigene Segler'),
    ('mc.add_glider',          'Segler hinzufügen'),
    ('mc.no_files',            'Keine Wegpunktdateien vorhanden.'),
    ('mc.no_tasks',            'Keine gespeicherten Aufgaben.'),
    ('mc.no_gliders',          'Keine eigenen Segler vorhanden.'),
    ('browse.title_waypoints', 'Wegpunktdateien durchsuchen'),
    ('browse.title_tasks',     'Aufgaben durchsuchen'),
    ('browse.search_placeholder', 'Suchen…'),
    ('browse.no_results',      'Keine Ergebnisse.'),
    ('task.new_task',          'Neue Aufgabe'),
    ('task.save_task',         'Aufgabe speichern'),
    ('task.load_task',         'Aufgabe laden'),
    ('task.total_distance',    'Gesamtdistanz'),
    ('aip.title',              'KI-Aufgabenplaner'),
    ('aip.target_distance',    'Zieldistanz'),
    ('aip.safety_profile',     'Sicherheitsprofil'),
    ('aip.safety_conservative','Konservativ'),
    ('aip.safety_standard',    'Standard'),
    ('aip.safety_aggressive',  'Aggressiv'),
    ('aip.soaring_mode',       'Segelflugmodus'),
    ('aip.soaring_thermal',    'Thermik'),
    ('aip.soaring_ridge',      'Hang'),
    ('aip.soaring_wave',       'Welle'),
    ('map.add_waypoint',       'Wegpunkt hinzufügen'),
    ('map.search_places',      'Orte suchen…'),
    ('confirm.delete',         'Soll dieser Eintrag wirklich gelöscht werden?'),
    ('status.loading',         'Wird geladen…'),
    ('status.saving',          'Wird gespeichert…'),
    ('status.saved',           'Gespeichert'),
    ('status.error',           'Ein Fehler ist aufgetreten.'),
    ('status.success',         'Erfolgreich')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Seed: Czech translations
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'cs', val FROM (VALUES
    ('nav.map_view',           'Zobrazení mapy'),
    ('nav.list_view',          'Zobrazení seznamu'),
    ('nav.task_planner',       'Plánovač úloh'),
    ('nav.ai_planner',         'AI Plánovač'),
    ('nav.my_content',         'Můj obsah'),
    ('nav.admin',              'Admin'),
    ('header.login',           'Přihlásit se'),
    ('header.signup',          'Registrovat'),
    ('header.logout',          'Odhlásit se'),
    ('header.language',        'Jazyk'),
    ('btn.save',               'Uložit'),
    ('btn.cancel',             'Zrušit'),
    ('btn.delete',             'Smazat'),
    ('btn.close',              'Zavřít'),
    ('btn.load',               'Načíst'),
    ('btn.upload',             'Nahrát'),
    ('btn.download',           'Stáhnout'),
    ('btn.search',             'Hledat'),
    ('btn.browse',             'Procházet'),
    ('btn.add',                'Přidat'),
    ('btn.edit',               'Upravit'),
    ('btn.import',             'Importovat'),
    ('btn.export',             'Exportovat'),
    ('btn.refresh',            'Obnovit'),
    ('btn.generate',           'Generovat úlohu'),
    ('mc.waypoint_files',      'Soubory trasových bodů'),
    ('mc.tasks',               'Úlohy'),
    ('mc.custom_gliders',      'Vlastní větroně'),
    ('mc.add_glider',          'Přidat větroň'),
    ('mc.no_files',            'Žádné soubory trasových bodů.'),
    ('mc.no_tasks',            'Žádné uložené úlohy.'),
    ('mc.no_gliders',          'Žádné vlastní větroně.'),
    ('browse.title_waypoints', 'Procházet soubory trasových bodů'),
    ('browse.title_tasks',     'Procházet úlohy'),
    ('browse.search_placeholder', 'Hledat…'),
    ('browse.no_results',      'Žádné výsledky.'),
    ('task.new_task',          'Nová úloha'),
    ('task.save_task',         'Uložit úlohu'),
    ('task.load_task',         'Načíst úlohu'),
    ('task.total_distance',    'Celková vzdálenost'),
    ('aip.title',              'AI Plánovač úloh'),
    ('aip.target_distance',    'Cílová vzdálenost'),
    ('aip.safety_profile',     'Bezpečnostní profil'),
    ('aip.safety_conservative','Konzervativní'),
    ('aip.safety_standard',    'Standardní'),
    ('aip.safety_aggressive',  'Agresivní'),
    ('aip.soaring_mode',       'Režim létání'),
    ('aip.soaring_thermal',    'Termika'),
    ('aip.soaring_ridge',      'Svah'),
    ('aip.soaring_wave',       'Vlna'),
    ('map.add_waypoint',       'Přidat bod trasy'),
    ('map.search_places',      'Hledat místa…'),
    ('confirm.delete',         'Opravdu chcete toto smazat?'),
    ('status.loading',         'Načítání…'),
    ('status.saving',          'Ukládání…'),
    ('status.saved',           'Uloženo'),
    ('status.error',           'Došlo k chybě.'),
    ('status.success',         'Úspěch')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;
