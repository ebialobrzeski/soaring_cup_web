# Example AI Model Input for Task Generation

This document shows the exact messages sent to the LLM (via OpenRouter) when a
pilot requests a task plan. The API call uses `response_format: json_object`,
`temperature: 0.3`, and `max_tokens: 4096`.

Model fallback chain: `google/gemini-2.5-flash` → `meta-llama/llama-3.3-70b-instruct` → `deepseek/deepseek-chat-v3-0324`

---

## Message 1: System Prompt

```
You are an expert gliding meteorologist and cross-country flight planner with 20+ years soaring experience in Central Europe (Poland).

ROLE: Analyze weather data and candidate routes to select the best route and write an actionable pilot briefing. You receive routes PRE-SCORED by an optimizer. Your job is primarily to provide NARRATIVE and WEATHER ANALYSIS, not to second-guess the optimizer's scoring. Only override the top-scored route if you identify a specific meteorological danger the optimizer missed.

TEMPORAL AWARENESS: Weather data is labeled by time window:
- [morning] = 09:00-12:00 — thermal development, cumulus forming
- [midday] = 12:00-15:00 — peak thermal strength
- [afternoon] = 15:00-18:00 — thermal decay, overdevelopment risk
Your narrative MUST describe how conditions evolve through the day and advise the pilot accordingly (e.g., "complete the furthest leg by 14:00 before afternoon overdevelopment").

ROUTE TYPE GUIDANCE:
- For conservative/standard safety: STRONGLY prefer triangle routes. Triangle routes keep the pilot within glide range of the takeoff airport. Out-and-return routes leave the pilot far from base on a single leg. Only recommend O&R if no viable triangle exists.
- For aggressive safety: pilot accepts more risk, O&R is acceptable.

SCORING CRITERIA (total 100 pts):
- Thermal Strength: 40 pts
- Cloud Base: 30 pts
- Wind: 20 pts
- Thermal Index: 10 pts

CAPE interpretation:
- >2000 J/kg = excellent thermals
- 1500-2000 = strong
- 1000-1500 = good
- 700-1000 = moderate
- 400-700 = weak
- <400 = very weak

Lapse rate thresholds:
- >3°C/1000ft = very unstable, excellent thermals
- 2-3 = unstable, good thermals
- 1-2 = neutral, weak thermals
- <1 = stable, no thermals

Cloud base scoring:
- >6000ft = excellent (+30)
- 4000-6000ft = very good (+25)
- 2500-4000ft = moderate (+20)
- 1500-2500ft = marginal (+10)
- <1500ft = poor (+0)

Wind scoring:
- 0-8 kts = ideal (+20)
- 8-12 kts = very good (+16)
- 12-18 kts = acceptable (+10)
- 18-25 kts = challenging (+5)
- >25 kts = dangerous (+0); gusts >15 kts = -20 pts

Return ONLY valid JSON. No commentary outside the JSON.

ADDITIONAL INSTRUCTIONS:
# AI Planner Custom Instructions

These instructions are injected into every AI Planner request as additional
system-level guidance. Edit this file to change how the AI planner behaves.

## General Rules

- Always prioritize pilot safety over ambitious task distance.
- When in doubt, suggest a shorter, safer route.
- You MUST respect the optimizer's pre-computed scores. Only override the top-scored route if you identify a specific weather hazard the numeric scorer could not detect (e.g., thunderstorm development along the route, rapidly deteriorating conditions in afternoon).

## Route Selection Rules

- For Conservative and Standard profiles: You MUST select a triangle or multi-leg route. Do NOT select an out-and-return route unless every triangle candidate has a blocking issue.
- The optimizer already penalises out-and-return routes and rewards triangles — trust its scoring.
- If the top-scored route is a triangle that starts into the wind, always select it.

## Route Preferences

- Prefer routes that stay within glide range of take off point in conservative profile, secondary landable airports.
- Prefer at least 3-leg routes for Conservative and Standard safety profiles to maximise staying within gliding range to a safe landing.
- Prefer flying parallel to the wind direction, starting the journey upwind for Conservative and Standard safety profiles.

## Temporal Weather Analysis

- Weather data includes time-window labels: [morning], [midday], [afternoon].
- Your narrative MUST describe how conditions evolve through the day.
- Recommend completing the furthest-from-home leg during peak thermal hours (12:00-15:00).
- Warn if afternoon overdevelopment or thermal decay could trap a pilot far from base.

## Narrative Style

- Be concise but thorough in weather analysis.
- Mention key decision factors (cloud base, wind, thermal strength) and how they change through the day.
- Include practical tips for the specific conditions.
- Include per-leg tactical advice (e.g., "Leg 2 has 12kt headwind — consider dolphin flying").
```

---

## Message 2: User Prompt

```
TASK REQUEST: 150km thermal flight from Leszno (EPLS)
DATE: 2026-06-15
SAFETY PROFILE: standard
SAFETY GUIDANCE: Balanced safety. Prefer triangle routes over out-and-return. Starting into wind is recommended but not mandatory.

WEATHER CONDITIONS (grid cell summaries, time-bucketed where available):
  51.84°N 16.58°E thermal=2.8m/s CAPE=1420J/kg BL=1850m wind=220°/12kt gust=18kt lapse=2.4°C/km CuBase=1780m precip=0.0mm
  51.90°N 16.70°E thermal=2.6m/s CAPE=1350J/kg BL=1800m wind=215°/11kt gust=17kt lapse=2.3°C/km CuBase=1720m precip=0.0mm
  51.78°N 16.50°E thermal=2.9m/s CAPE=1480J/kg BL=1900m wind=225°/13kt gust=19kt lapse=2.5°C/km CuBase=1820m precip=0.0mm
  51.96°N 16.80°E thermal=2.4m/s CAPE=1280J/kg BL=1750m wind=210°/10kt gust=16kt lapse=2.2°C/km CuBase=1680m precip=0.0mm
  51.72°N 16.40°E thermal=3.0m/s CAPE=1520J/kg BL=1950m wind=230°/14kt gust=20kt lapse=2.6°C/km CuBase=1860m precip=0.0mm
  52.00°N 16.90°E thermal=2.3m/s CAPE=1200J/kg BL=1700m wind=205°/9kt gust=15kt lapse=2.1°C/km CuBase=1640m precip=0.0mm
  51.66°N 16.30°E thermal=3.1m/s CAPE=1550J/kg BL=1980m wind=235°/15kt gust=21kt lapse=2.7°C/km CuBase=1900m precip=0.0mm
  52.06°N 17.00°E thermal=2.2m/s CAPE=1150J/kg BL=1680m wind=200°/8kt gust=14kt lapse=2.0°C/km CuBase=1600m precip=0.0mm
  51.84°N 16.58°E thermal=2.5m/s CAPE=1300J/kg BL=1780m wind=218°/11kt gust=17kt lapse=2.3°C/km CuBase=1700m precip=0.0mm
  51.60°N 16.20°E thermal=3.2m/s CAPE=1600J/kg BL=2020m wind=240°/16kt gust=22kt lapse=2.8°C/km CuBase=1940m precip=0.2mm
  52.10°N 16.40°E thermal=2.7m/s CAPE=1380J/kg BL=1830m wind=210°/11kt gust=16kt lapse=2.4°C/km CuBase=1760m precip=0.0mm
  51.70°N 17.00°E thermal=2.4m/s CAPE=1250J/kg BL=1730m wind=220°/10kt gust=15kt lapse=2.2°C/km CuBase=1660m precip=0.0mm
  52.00°N 16.30°E thermal=2.8m/s CAPE=1430J/kg BL=1870m wind=215°/12kt gust=18kt lapse=2.5°C/km CuBase=1790m precip=0.0mm
  51.60°N 16.80°E thermal=2.6m/s CAPE=1320J/kg BL=1810m wind=225°/13kt gust=19kt lapse=2.3°C/km CuBase=1730m precip=0.0mm
  52.10°N 17.00°E thermal=2.1m/s CAPE=1100J/kg BL=1650m wind=200°/8kt gust=13kt lapse=1.9°C/km CuBase=1580m precip=0.0mm
  51.50°N 16.50°E thermal=3.0m/s CAPE=1500J/kg BL=1920m wind=230°/14kt gust=20kt lapse=2.6°C/km CuBase=1850m precip=0.0mm
  51.84°N 17.20°E thermal=2.3m/s CAPE=1180J/kg BL=1710m wind=205°/9kt gust=15kt lapse=2.1°C/km CuBase=1630m precip=0.0mm
  52.20°N 16.58°E thermal=2.5m/s CAPE=1270J/kg BL=1760m wind=212°/10kt gust=16kt lapse=2.2°C/km CuBase=1690m precip=0.0mm
  51.84°N 15.90°E thermal=3.3m/s CAPE=1650J/kg BL=2050m wind=245°/17kt gust=23kt lapse=2.9°C/km CuBase=1960m precip=0.3mm
  51.50°N 17.20°E thermal=2.0m/s CAPE=1050J/kg BL=1620m wind=200°/7kt gust=12kt lapse=1.8°C/km CuBase=1550m precip=0.0mm
  [morning] 51.84°N 16.58°E thermal=1.8m/s CAPE=900J/kg BL=1400m wind=210°/8kt gust=12kt lapse=2.0°C/km CuBase=1350m precip=0.0mm
  [morning] 51.78°N 16.50°E thermal=1.9m/s CAPE=950J/kg BL=1450m wind=215°/9kt gust=13kt lapse=2.1°C/km CuBase=1380m precip=0.0mm
  [morning] 51.90°N 16.70°E thermal=1.7m/s CAPE=850J/kg BL=1380m wind=208°/7kt gust=11kt lapse=1.9°C/km CuBase=1320m precip=0.0mm
  [morning] 51.72°N 16.40°E thermal=2.0m/s CAPE=980J/kg BL=1480m wind=220°/10kt gust=14kt lapse=2.2°C/km CuBase=1400m precip=0.0mm
  [morning] 52.00°N 16.90°E thermal=1.5m/s CAPE=780J/kg BL=1320m wind=200°/6kt gust=10kt lapse=1.8°C/km CuBase=1280m precip=0.0mm
  [morning] 51.96°N 16.80°E thermal=1.6m/s CAPE=820J/kg BL=1350m wind=205°/7kt gust=11kt lapse=1.9°C/km CuBase=1300m precip=0.0mm
  [morning] 52.06°N 17.00°E thermal=1.4m/s CAPE=720J/kg BL=1280m wind=195°/5kt gust=9kt lapse=1.7°C/km CuBase=1240m precip=0.0mm
  [midday] 51.84°N 16.58°E thermal=3.2m/s CAPE=1650J/kg BL=2100m wind=225°/14kt gust=20kt lapse=2.7°C/km CuBase=2020m precip=0.0mm
  [midday] 51.78°N 16.50°E thermal=3.3m/s CAPE=1700J/kg BL=2150m wind=230°/15kt gust=21kt lapse=2.8°C/km CuBase=2060m precip=0.0mm
  [midday] 51.90°N 16.70°E thermal=3.0m/s CAPE=1580J/kg BL=2050m wind=220°/13kt gust=19kt lapse=2.6°C/km CuBase=1980m precip=0.0mm
  [midday] 51.72°N 16.40°E thermal=3.4m/s CAPE=1750J/kg BL=2200m wind=235°/16kt gust=22kt lapse=2.9°C/km CuBase=2100m precip=0.0mm
  [midday] 52.00°N 16.90°E thermal=2.8m/s CAPE=1500J/kg BL=1980m wind=215°/12kt gust=18kt lapse=2.5°C/km CuBase=1920m precip=0.0mm
  [midday] 51.96°N 16.80°E thermal=2.9m/s CAPE=1530J/kg BL=2000m wind=218°/12kt gust=18kt lapse=2.5°C/km CuBase=1950m precip=0.0mm
  [midday] 52.06°N 17.00°E thermal=2.6m/s CAPE=1400J/kg BL=1920m wind=208°/10kt gust=16kt lapse=2.3°C/km CuBase=1850m precip=0.0mm
  [afternoon] 51.84°N 16.58°E thermal=2.4m/s CAPE=1200J/kg BL=1700m wind=220°/11kt gust=17kt lapse=2.3°C/km CuBase=1650m precip=0.0mm
  [afternoon] 51.78°N 16.50°E thermal=2.5m/s CAPE=1250J/kg BL=1750m wind=225°/12kt gust=18kt lapse=2.4°C/km CuBase=1680m precip=0.0mm
  [afternoon] 51.90°N 16.70°E thermal=2.2m/s CAPE=1120J/kg BL=1650m wind=215°/10kt gust=16kt lapse=2.1°C/km CuBase=1600m precip=0.0mm
  [afternoon] 51.72°N 16.40°E thermal=2.6m/s CAPE=1300J/kg BL=1780m wind=230°/13kt gust=19kt lapse=2.5°C/km CuBase=1720m precip=0.1mm
  [afternoon] 52.00°N 16.90°E thermal=2.0m/s CAPE=1050J/kg BL=1600m wind=210°/9kt gust=15kt lapse=2.0°C/km CuBase=1540m precip=0.0mm
  [afternoon] 51.96°N 16.80°E thermal=2.1m/s CAPE=1080J/kg BL=1620m wind=212°/9kt gust=15kt lapse=2.0°C/km CuBase=1560m precip=0.0mm
  [afternoon] 52.06°N 17.00°E thermal=1.8m/s CAPE=950J/kg BL=1550m wind=202°/7kt gust=13kt lapse=1.8°C/km CuBase=1480m precip=0.0mm

AIRSPACE OVERVIEW: 12 zones in area, 2 conflicts detected
  ⚠ BLOCKING CONFLICTS DETECTED — some routes cross restricted airspace

TERRAIN: max elevation 187m ASL

TOP 3 CANDIDATE ROUTES (pre-scored by optimizer):
  Route 1: Triangle NE-SW (upwind-biased)
    Distance: 152.3km, Optimizer Score: 74/100
    Leg 1: EPLS → TP1 (51.62°N 16.22°E) (48.2km, 225°) thermal=3.1 headwind=13kt
    Leg 2: TP1 → TP2 (52.08°N 16.38°E) (52.8km, 008°) thermal=2.8 tailwind=4kt
    Leg 3: TP2 → EPLS (51.84°N 16.58°E) (51.3km, 142°) thermal=2.5 tailwind=6kt ⚠1 airspace conflicts

  Route 2: Triangle E-NW (upwind-biased)
    Distance: 148.7km, Optimizer Score: 71/100
    Leg 1: EPLS → TP1 (51.70°N 16.96°E) (46.5km, 210°) thermal=2.4 headwind=10kt
    Leg 2: TP1 → TP2 (52.14°N 16.30°E) (55.1km, 330°) thermal=2.7 tailwind=8kt
    Leg 3: TP2 → EPLS (51.84°N 16.58°E) (47.1km, 155°) thermal=2.6 tailwind=5kt

  Route 3: Out-and-Return NE
    Distance: 154.0km, Optimizer Score: 65/100
    Leg 1: EPLS → TP1 (52.52°N 17.20°E) (77.0km, 040°) thermal=2.3 headwind=6kt
    Leg 2: TP1 → EPLS (51.84°N 16.58°E) (77.0km, 220°) thermal=2.6 tailwind=6kt

IMPORTANT: You MUST select the route with the highest optimizer score unless you have a specific meteorological reason to override it (e.g., weather deterioration along that route). If you override, explain why in the narrative.

Analyze these routes. Return JSON with this structure:
{
  "selected_route": <1-based index of best route>,
  "score": <0-100 integer>,
  "explanation_en": "<Detailed English narrative: weather analysis by time window (morning/midday/afternoon conditions), route justification, safety notes, thermal strategy, wind strategy, estimated XC speed>",
  "explanation_pl": "<Same in Polish>",
  "weather_summary_en": "<Brief weather overview including how conditions change through the day (morning→midday→afternoon)>",
  "weather_summary_pl": "<Brief weather overview in Polish>",
  "recommended_takeoff_time": "<HH:MM>",
  "estimated_duration_hours": <float>,
  "estimated_speed_kmh": <float>,
  "safety_notes": ["<note1>", "<note2>"]
}
```

---

## Expected JSON Response (example)

```json
{
  "selected_route": 1,
  "score": 74,
  "explanation_en": "Route 1 (Triangle NE-SW) is the best choice for today's conditions at Leszno. The optimizer scores it highest at 74/100, and the meteorological analysis confirms this selection.\n\n**Weather Evolution:**\nMorning (09-12): Thermals developing slowly with 1.5-2.0 m/s climbs and cloud base around 1350-1480m. CAPE values 780-980 J/kg indicate moderate instability building. Southwest winds 5-10 kt.\n\nMidday (12-15): Peak conditions with thermals reaching 3.0-3.4 m/s. CAPE surges to 1500-1750 J/kg — strong thermal activity. Cloud bases lift to 1980-2200m AGL. Wind strengthens to 225°/12-16 kt.\n\nAfternoon (15-18): Gradual thermal decay. Climbs weaken to 2.0-2.6 m/s, cloud base drops to 1480-1720m. Some cumulus overdevelopment possible in the southwest sector (0.1mm precip signal at 51.72°N).\n\n**Route Strategy:**\nLeg 1 (EPLS→SW, 48km, 225°): Launch into the strengthening SW wind during late morning. You'll face 13kt headwind but this is deliberate — the hardest leg is closest to home. Work thermals aggressively in the excellent SW sector (CAPE 1520-1600 J/kg). Target TP1 by 12:30.\n\nLeg 2 (SW→N, 53km, 008°): The longest leg coincides with peak midday thermals (3.2-3.4 m/s). You'll have a 4kt tailwind component. Cloud bases above 2000m give excellent working altitude. Complete by 14:30.\n\nLeg 3 (N→EPLS, 51km, 142°): Final glide with 6kt tailwind. Note 1 airspace conflict — check NOTAM for the restricted zone near EPLS approach. Thermals still workable at 2.5 m/s but weakening. Plan to be overhead by 16:00.\n\n**XC Speed:** Expect 55-65 km/h average given the moderate headwind on Leg 1 and strong midday thermals.",
  "explanation_pl": "Trasa 1 (Trójkąt NE-SW) jest najlepszym wyborem na dzisiejsze warunki w Lesznie. Optymalizator ocenił ją najwyżej — 74/100, a analiza meteorologiczna potwierdza ten wybór.\n\n**Ewolucja pogody:**\nPoranek (09-12): Termika rozwija się powoli, wznoszenia 1.5-2.0 m/s, podstawa chmur ok. 1350-1480m. CAPE 780-980 J/kg wskazuje na narastającą niestabilność. Wiatr SW 5-10 kt.\n\nPołudnie (12-15): Szczytowe warunki — termika do 3.0-3.4 m/s. CAPE rośnie do 1500-1750 J/kg. Podstawa chmur podnosi się do 1980-2200m AGL. Wiatr wzmaga się do 225°/12-16 kt.\n\nPopołudnie (15-18): Stopniowe słabnięcie termiki do 2.0-2.6 m/s, podstawa opada do 1480-1720m. Możliwy przerost cumulus w sektorze SW.\n\n**Strategia trasy:**\nOdcinek 1 (EPLS→SW, 48km): Start pod wiatr w późny poranek. 13kt czołowego wiatru, ale najtrudniejszy odcinek jest najbliżej domu. TP1 do 12:30.\n\nOdcinek 2 (SW→N, 53km): Najdłuższy odcinek w szczytowej termice (3.2-3.4 m/s). 4kt wiatru w plecy. Ukończ do 14:30.\n\nOdcinek 3 (N→EPLS, 51km): Dolot końcowy z 6kt wiatru w plecy. Uwaga: 1 konflikt przestrzeni powietrznej — sprawdź NOTAM. Plan przybycia do 16:00.\n\n**Prędkość XC:** 55-65 km/h średnia.",
  "weather_summary_en": "Good soaring day at Leszno. Morning thermals 1.5-2.0 m/s developing to strong 3.0-3.4 m/s by midday with cloud bases reaching 2000-2200m. CAPE 1500-1750 J/kg at peak. SW wind 12-16 kt. Afternoon decay from 15:00, possible overdevelopment in SW sector. Best window: 11:00-15:00.",
  "weather_summary_pl": "Dobry dzień szybowcowy w Lesznie. Poranna termika 1.5-2.0 m/s rozwija się do silnych 3.0-3.4 m/s w południe, podstawa chmur do 2000-2200m. CAPE 1500-1750 J/kg w szczycie. Wiatr SW 12-16 kt. Osłabnienie od 15:00, możliwy przerost Cu w sektorze SW. Najlepsze okno: 11:00-15:00.",
  "recommended_takeoff_time": "10:30",
  "estimated_duration_hours": 3.2,
  "estimated_speed_kmh": 58,
  "safety_notes": [
    "Airspace conflict on Leg 3 near EPLS — verify NOTAMs before flight",
    "SW wind gusts up to 23kt forecast west of task area — avoid westernmost cells",
    "Afternoon overdevelopment risk in SW sector after 15:00 — maintain altitude reserve on Leg 3",
    "Cloud base drops below 1500m after 16:00 — be back before decay"
  ]
}
```

---

## Notes

- The **system prompt** is built at module load time by combining the hardcoded
  `_SYSTEM_PROMPT` with the contents of `ai_planner_instructions.md`.
- The **user prompt** is built dynamically by `_build_task_prompt()` for each request.
- Weather cells without a `[time_window]` prefix are day-averaged (06:00-21:00).
- The first 20 weather cells are day-averaged; then up to 7 per time window
  (morning + midday + afternoon = up to 21 more) are appended.
- Candidate routes include per-leg weather details (thermal quality, wind component)
  and airspace conflict counts when available.
- The model is instructed to return **only valid JSON** with `response_format: json_object`.
