-- Migration 019: i18n keys for waypoint generator, map tools, wind/speed, confirm dialog,
--                My Content gliders table, and common Yes/No values.

-- ─────────────────────────────────────────────────────────────────────────────
-- New translation keys
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translation_keys (key, default_value, category, description) VALUES
    -- Map sidebar card headers / tool buttons
    ('map.file_ops',              'File',                                        'map',     'File operations card header'),
    ('map.tools_card',            'Map Tools',                                   'map',     'Map Tools card header'),
    ('map.fit_view',              'Fit View',                                    'map',     'Fit all waypoints in view button'),
    ('map.fit_view_title',        'Fit all waypoints in view',                   'map',     'Tooltip for Fit View button'),
    ('map.legend',                'Legend',                                      'map',     'Show legend button'),
    ('map.legend_title',          'Show waypoint icons legend',                  'map',     'Tooltip for Legend button'),
    -- Common button labels
    ('btn.collapse',              'Collapse',                                    'btn',     'Collapse toggle button label'),
    -- Waypoint generator card
    ('wpgen.card_header',         'Generate Waypoints',                          'wpgen',   'Generate Waypoints card header'),
    ('wpgen.select_area',         'Select Area',                                 'wpgen',   'Select area button text'),
    ('wpgen.change_area',         'Change Area',                                 'wpgen',   'Change area button text (after selection)'),
    ('wpgen.select_area_title',   'Draw a rectangle on the map to select an area', 'wpgen', 'Select area button tooltip'),
    ('wpgen.clear_area',          'Clear selection',                             'wpgen',   'Clear selection icon button tooltip'),
    ('wpgen.aviation',            'Aviation',                                    'wpgen',   'Aviation section label'),
    ('wpgen.airports',            'Airports & Airfields',                        'wpgen',   'Airports checkbox label'),
    ('wpgen.outlandings',         'Outlanding fields',                           'wpgen',   'Outlanding fields checkbox label'),
    ('wpgen.obstacles',           'Obstacles',                                   'wpgen',   'Obstacles checkbox label'),
    ('wpgen.navaids',             'Nav aids (VOR/NDB)',                          'wpgen',   'Nav aids checkbox label'),
    ('wpgen.hotspots',            'Thermal hotspots',                            'wpgen',   'Thermal hotspots checkbox label'),
    ('wpgen.hang_glidings',       'Hang gliding sites',                          'wpgen',   'Hang gliding sites checkbox label'),
    ('wpgen.populated_places',    'Populated Places',                            'wpgen',   'Populated Places section label'),
    ('wpgen.cities',              'Cities',                                      'wpgen',   'Cities checkbox label'),
    ('wpgen.towns',               'Towns',                                       'wpgen',   'Towns checkbox label'),
    ('wpgen.villages',            'Villages',                                    'wpgen',   'Villages checkbox label'),
    ('wpgen.generate',            'Generate',                                    'wpgen',   'Generate button label'),
    -- Task planner: wind / speed inputs
    ('task.wind_dir',             'Wind °',                                      'task',    'Wind direction input label'),
    ('task.wind_speed',           'Speed kt',                                    'task',    'Wind speed input label'),
    ('task.tas',                  'TAS km/h',                                    'task',    'TAS input label'),
    ('task.wp_search_placeholder','Search by name or code...',                   'task',    'Waypoint search input placeholder'),
    ('task.task_name_placeholder','Task name',                                   'task',    'Task name input placeholder'),
    -- Confirmation dialog
    ('confirm.title',             'Confirm',                                     'confirm', 'Confirm dialog title'),
    ('confirm.ok',                'OK',                                          'confirm', 'Confirm dialog OK button'),
    ('confirm.clear_waypoints',   'This will clear all current waypoints. Continue?', 'confirm', 'Clear waypoints confirmation message'),
    ('confirm.delete_n_waypoints','Delete {n} waypoint(s)?',                    'confirm', 'Delete N waypoints confirmation; {n} = count'),
    ('confirm.delete_waypoint',   'Delete waypoint "{name}"?',                  'confirm', 'Delete single waypoint confirmation; {name} = waypoint name'),
    -- My Content: glider table headers / empty state
    ('mc.col_speed_range',        'Speed Range',                                 'my_content', 'Glider table: speed range column'),
    ('mc.col_max_gross',          'Max Gross',                                   'my_content', 'Glider table: max gross weight column'),
    ('mc.no_gliders_action',      'No custom gliders. Click \u201cAdd Glider\u201d to create one.', 'my_content', 'Empty gliders table message with action hint'),
    -- Common boolean display values
    ('common.yes',                'Yes',                                         'common',  'Boolean Yes'),
    ('common.no',                 'No',                                          'common',  'Boolean No')
ON CONFLICT (key) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Polish
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'pl', val FROM (VALUES
    ('map.file_ops',              'Plik'),
    ('map.tools_card',            'Narzędzia mapy'),
    ('map.fit_view',              'Dopasuj widok'),
    ('map.fit_view_title',        'Dopasuj widok do wszystkich punktów'),
    ('map.legend',                'Legenda'),
    ('map.legend_title',          'Pokaż legendę ikon punktów nawigacyjnych'),
    ('btn.collapse',              'Zwiń'),
    ('wpgen.card_header',         'Generuj punkty'),
    ('wpgen.select_area',         'Wybierz obszar'),
    ('wpgen.change_area',         'Zmień obszar'),
    ('wpgen.select_area_title',   'Narysuj prostokąt na mapie, aby wybrać obszar'),
    ('wpgen.clear_area',          'Wyczyść zaznaczenie'),
    ('wpgen.aviation',            'Lotnictwo'),
    ('wpgen.airports',            'Lotniska i lądowiska'),
    ('wpgen.outlandings',         'Pola do przymusowego lądowania'),
    ('wpgen.obstacles',           'Przeszkody'),
    ('wpgen.navaids',             'Pomoce nawigacyjne (VOR/NDB)'),
    ('wpgen.hotspots',            'Termiczne punkty wyżowe'),
    ('wpgen.hang_glidings',       'Miejsca lotniowe (paralotniarstwo)'),
    ('wpgen.populated_places',    'Miejscowości'),
    ('wpgen.cities',              'Miasta'),
    ('wpgen.towns',               'Miasteczka'),
    ('wpgen.villages',            'Wsie'),
    ('wpgen.generate',            'Generuj'),
    ('task.wind_dir',             'Wiatr °'),
    ('task.wind_speed',           'Prędkość kn'),
    ('task.tas',                  'TAS km/h'),
    ('task.wp_search_placeholder','Szukaj po nazwie lub kodzie...'),
    ('task.task_name_placeholder','Nazwa zadania'),
    ('confirm.title',             'Potwierdzenie'),
    ('confirm.ok',                'OK'),
    ('confirm.clear_waypoints',   'Spowoduje to wyczyszczenie wszystkich bieżących punktów. Kontynuować?'),
    ('confirm.delete_n_waypoints','Usunąć {n} punkt(ów)?'),
    ('confirm.delete_waypoint',   'Usunąć punkt \u201e{name}\u201d?'),
    ('mc.col_speed_range',        'Zakres prędkości'),
    ('mc.col_max_gross',          'Maks. masa'),
    ('mc.no_gliders_action',      'Brak własnych szybowców. Kliknij \u201eDodaj szybowiec\u201d, aby go utworzyć.'),
    ('common.yes',                'Tak'),
    ('common.no',                 'Nie')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- German
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'de', val FROM (VALUES
    ('map.file_ops',              'Datei'),
    ('map.tools_card',            'Kartentools'),
    ('map.fit_view',              'Ansicht anpassen'),
    ('map.fit_view_title',        'Alle Wegpunkte einpassen'),
    ('map.legend',                'Legende'),
    ('map.legend_title',          'Wegpunkt-Legende anzeigen'),
    ('btn.collapse',              'Einklappen'),
    ('wpgen.card_header',         'Wegpunkte generieren'),
    ('wpgen.select_area',         'Bereich wählen'),
    ('wpgen.change_area',         'Bereich ändern'),
    ('wpgen.select_area_title',   'Rechteck auf der Karte zeichnen, um einen Bereich auszuwählen'),
    ('wpgen.clear_area',          'Auswahl löschen'),
    ('wpgen.aviation',            'Luftfahrt'),
    ('wpgen.airports',            'Flughäfen & Flugfelder'),
    ('wpgen.outlandings',         'Außenlandefelder'),
    ('wpgen.obstacles',           'Hindernisse'),
    ('wpgen.navaids',             'Navigationshilfen (VOR/NDB)'),
    ('wpgen.hotspots',            'Thermik-Hotspots'),
    ('wpgen.hang_glidings',       'Hängegleiter-Standorte'),
    ('wpgen.populated_places',    'Ortschaften'),
    ('wpgen.cities',              'Städte'),
    ('wpgen.towns',               'Kleinstädte'),
    ('wpgen.villages',            'Dörfer'),
    ('wpgen.generate',            'Generieren'),
    ('task.wind_dir',             'Wind °'),
    ('task.wind_speed',           'Geschw. kt'),
    ('task.tas',                  'TAS km/h'),
    ('task.wp_search_placeholder','Nach Name oder Code suchen...'),
    ('task.task_name_placeholder','Aufgabenname'),
    ('confirm.title',             'Bestätigung'),
    ('confirm.ok',                'OK'),
    ('confirm.clear_waypoints',   'Alle aktuellen Wegpunkte werden gelöscht. Fortfahren?'),
    ('confirm.delete_n_waypoints','{n} Wegpunkt(e) löschen?'),
    ('confirm.delete_waypoint',   'Wegpunkt \u201e{name}\u201c löschen?'),
    ('mc.col_speed_range',        'Geschwindigkeitsbereich'),
    ('mc.col_max_gross',          'Max. Gesamtmasse'),
    ('mc.no_gliders_action',      'Keine eigenen Segler. Klicken Sie auf \u201eSegler hinzufügen\u201c.'),
    ('common.yes',                'Ja'),
    ('common.no',                 'Nein')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Czech
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO translations (key_id, language_code, value)
SELECT id, 'cs', val FROM (VALUES
    ('map.file_ops',              'Soubor'),
    ('map.tools_card',            'Nástroje mapy'),
    ('map.fit_view',              'Přizpůsobit pohled'),
    ('map.fit_view_title',        'Přizpůsobit pohled všem trasovým bodům'),
    ('map.legend',                'Legenda'),
    ('map.legend_title',          'Zobrazit legendu ikon trasových bodů'),
    ('btn.collapse',              'Sbalit'),
    ('wpgen.card_header',         'Generovat trasové body'),
    ('wpgen.select_area',         'Vybrat oblast'),
    ('wpgen.change_area',         'Změnit oblast'),
    ('wpgen.select_area_title',   'Nakreslete obdélník na mapě pro výběr oblasti'),
    ('wpgen.clear_area',          'Zrušit výběr'),
    ('wpgen.aviation',            'Letectví'),
    ('wpgen.airports',            'Letiště a letecké plochy'),
    ('wpgen.outlandings',         'Přistávací plochy'),
    ('wpgen.obstacles',           'Překážky'),
    ('wpgen.navaids',             'Navigační pomůcky (VOR/NDB)'),
    ('wpgen.hotspots',            'Termické hotspoty'),
    ('wpgen.hang_glidings',       'Stanové letecké plochy'),
    ('wpgen.populated_places',    'Sídla'),
    ('wpgen.cities',              'Města'),
    ('wpgen.towns',               'Maloměsta'),
    ('wpgen.villages',            'Vesnice'),
    ('wpgen.generate',            'Generovat'),
    ('task.wind_dir',             'Vítr °'),
    ('task.wind_speed',           'Rychlost kt'),
    ('task.tas',                  'TAS km/h'),
    ('task.wp_search_placeholder','Hledat podle názvu nebo kódu...'),
    ('task.task_name_placeholder','Název úlohy'),
    ('confirm.title',             'Potvrzení'),
    ('confirm.ok',                'OK'),
    ('confirm.clear_waypoints',   'Tím se vymažou všechny aktuální trasové body. Pokračovat?'),
    ('confirm.delete_n_waypoints','Smazat {n} trasový(é) bod(y)?'),
    ('confirm.delete_waypoint',   'Smazat trasový bod \u201e{name}\u201c?'),
    ('mc.col_speed_range',        'Rozsah rychlosti'),
    ('mc.col_max_gross',          'Max. celk. hmotnost'),
    ('mc.no_gliders_action',      'Žádné vlastní větroně. Klikněte na \u201ePřidat větroň\u201c.'),
    ('common.yes',                'Ano'),
    ('common.no',                 'Ne')
) AS t(key, val)
JOIN translation_keys tk ON tk.key = t.key
ON CONFLICT (key_id, language_code) DO NOTHING;
