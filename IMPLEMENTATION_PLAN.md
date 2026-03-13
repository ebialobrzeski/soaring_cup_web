# Flight Simulator — Implementation Plan

## Overview

A flight simulator embedded inside the Task Planner tab. The glider flies the active task on the
existing Leaflet map, with realistic polar-based sink, MacCready speed-to-fly, wind drift, and
LK8000-style thermal bubbles.

---

## Architecture

| Layer | File | Notes |
|---|---|---|
| Simulator engine | `static/js/task-simulator.js` | New file — pure JS, no backend dependency |
| UI controls | `templates/index.html` | Simulate button + collapsible control bar added to task panel |
| Styling | `static/css/task-simulator.css` | New file |
| i18n strings | `backend/models/i18n.py` + translation JSON files | All new labels use `data-i18n` |

The engine references the `TaskPlanner` instance already on the page to get:
- `taskPlanner.taskPoints` — the task waypoints and OZs
- `taskPlanner.map` — the Leaflet map instance
- Wind/TAS values already on the page (`task-wind-dir`, `task-wind-speed`, `task-tas`)
- Glider polar (`polar_a`, `polar_b`, `polar_c`) passed from the glider selector

No new backend routes are needed for the basic simulator.

---

## Phase 1 — Core Movement Engine

**File:** `static/js/task-simulator.js`

### SimulatorEngine class

```
state = {
  lat, lon,          // current position (degrees)
  altitude,          // m MSL
  heading,           // degrees
  groundSpeed,       // m/s
  tas,               // m/s true airspeed
  vario,             // m/s (total-energy variometer)
  nettoVario,        // m/s (air mass, = vario - polar_sink)
  time,              // seconds elapsed
  circling,          // bool — derived from turn rate
  turnRate,          // deg/s
}
```

### Position integration (1-second tick)

Dead-reckoning with wind drift — identical to LK8000's `FindLatitudeLongitude` + XCSoar's
`AircraftSim::Integrate`:

```
// 1. TAS vector along heading
refLat, refLon = destPoint(lat, lon, tas * dt, heading)
// 2. Apply wind drift vector
newLat, newLon = destPoint(refLat, refLon, windSpeed * dt, windDir + 180°)
// 3. Ground track = bearing from old to new position
// 4. Ground speed = distance / dt
```

`destPoint()` already exists in `task-planner.js` — the engine will call it via the shared
`TaskPlanner` utility or define its own copy (∼10 lines).

### Sink rate from polar

Using the quadratic polar already stored on the glider object (`polar_a`, `polar_b`, `polar_c`
in SI units, speeds in m/s):

```
polarSinkRate(v_ms) = polar_a * v² + polar_b * v + polar_c   // negative value (sink)
```

Air-density correction for altitude (ISA model, same as LK8000's `AirDensitySinkRate`):

```
densityRatio(alt) = (1 - 2.2558e-5 * alt) ^ 5.2559
correctedSink = polarSinkRate(ias) * densityRatio(alt)
```

### Altitude update per tick

```
// 1. Polar sink (always applied)
vario = thermalLift - abs(correctedSink)
altitude += vario * dt
if altitude < 0: altitude = 0  // ground
```

---

## Phase 2 — MacCready Speed-to-Fly

This is the key pilot-facing setting. A slider/input (`0.0` to `5.0` m/s, default `1.0`)
acts as the MacCready setting (Mc).

### What Mc controls

| Mode | Effect |
|---|---|
| **Cruise** | Speed-to-fly (STF) — how fast to fly between thermals |
| **Thermal** | Threshold — leave the thermal when average lift drops below Mc |

### STF analytical formula (same as LK8000's `GlidePolar::STF`)

```
// Solve d(glide_ratio)/dV = 0 accounting for Mc, headwind, and netto vario
// From the polar: w_total = polar_a*V² + polar_b*V + polar_c - Mc + nettoVario
// STF = headWind - sqrt( a * (nettoVario - Mc + a*hw² + b*hw + c) ) / a
// where hw = headwind component on current leg (m/s)

stf(Mc, netto, hw) {
  const disc = polar_a * (netto - Mc + polar_a*hw*hw + polar_b*hw + polar_c);
  if (disc <= 0) return vminsink;
  return Math.max(vminsink, hw - Math.sqrt(disc) / polar_a);
}
```

The STF value is displayed as a "Speed to Fly" readout in the simulator HUD alongside
the current IAS, so the pilot can see the difference.

### Circling decision (auto-pilot assist, optional)

In manual mode the user steers with keyboard. In auto mode:
- Climb in thermal when lift > 0
- Leave thermal when average lift < Mc (or time in thermal > configurable max)

---

## Phase 3 — Thermal Simulation Model

LK8000-style physics: one thermal bubble at a time, user-placeable, with a realistic
lift/sink profile.

### Thermal object

```javascript
{
  lat, lon,           // center position
  radius: 200,        // m — lift core  (ThermalRadius in LK8000)
  strength: 3.0,      // m/s lift at center
  sinkRadius: 150,    // m — annular sink ring outside core (SinkRadius)
  sinkStrength: 1.5,  // m/s sink at outer edge of ring
  base: null,         // AGL base (null = auto from altitude when marked)
  top: null,          // AGL top (null = unlimited during sim)
}
```

### Lift/sink at a given distance from thermal center

```javascript
thermalEffect(distance, thermal) {
  if (distance < thermal.radius) {
    // Lift zone: parabolic falloff — strongest at center
    const t = 1 - (distance / thermal.radius);
    return thermal.strength * t;   // +m/s
  }
  const outerEdge = thermal.radius + thermal.sinkRadius;
  if (distance < outerEdge) {
    // Sink ring: linear falloff
    const t = 1 - (distance - thermal.radius) / thermal.sinkRadius;
    return -thermal.sinkStrength * t;  // -m/s
  }
  return 0;
}
```

This is the direct JS translation of `LKSimulator.cpp` lines 206–232.

### Circling detection

Turn rate is computed from successive headings:
```
turnRate = angleDiff(heading_now, heading_1s_ago)   // deg/s
circling = (abs(turnRate) > 4°/s) sustained for > 5 seconds
```

When circling begins, the nearest thermal is "activated" (the one the glider drifted into).

### Multiple thermals

Unlike LK8000 which has one thermal at a time, we support an array of up to 10 thermals.
The user can:
- **Click the map** to place a thermal bubble (shown as a translucent circle on the Leaflet map)
- **Drag** existing thermals to reposition them
- **Auto-seed** thermals: a set of thermals spread around the task area is generated on
  Simulate start (positions randomised from task turnpoints with ±3 km offset)

---

## Phase 4 — Task Progress & Sector Detection

### OZ crossing detection

At each tick, check if the glider position is inside the active task point's observation zone.
Reuses the `drawObsZone` geometry logic already in `task-planner.js`:

- **Cylinder**: `distance(glider, oz_center) <= oz_radius`
- **FAI Sector / BGA Fixed**: angle check within half-angle and within inner/outer radius
- **Line**: perpendicular crossing-detection (same as XCSoar's `TaskZone`)

On crossing:
- Play a sound cue
- Advance `activeTaskPointIndex`
- Draw a timestamp on the snail-trail

### Snail trail

Array of `{lat, lon, altitude, time}` recorded every second.
Rendered as a Leaflet polyline coloured by vario value (green = climb, red = sink).

---

## Phase 5 — UI Controls

### Simulator control bar (slides in above the Leaflet map when active)

```
[ ▶ Play ] [ ⏸ Pause ] [ ⏹ Stop ]   Speed: [1×] [2×] [5×] [10×]
Alt: 1245m   Vario: +2.1 m/s   IAS: 108 km/h   STF: 115 km/h
Mc: [──●──] 1.5 m/s   Netto: +3.6 m/s   Task: TP1 → TP2  12.3 km
```

### Simulator sidebar card (same sidebar as task planner)

Shows a small collapsible card above the wind card with:
- **Start Altitude** input (m MSL) — default 600 m
- **Start Position** dropdown: Task Start point / First TP / Custom
- **Thermal Controls**: Add Thermal button, list of placed thermals with delete
- **MacCready**: range slider 0.0–5.0 (step 0.1) with numeric readout

### Keyboard controls (when simulator is active)

| Key | Action |
|---|---|
| `←` / `→` | Turn left / right (±3°/s added to heading) |
| `↑` / `↓` | Speed +/-5 km/h |
| `PageUp` / `PageDown` | Mc +0.1 / -0.1 |
| `Space` | Toggle pause |
| `T` | Place thermal at current position |

### Glider marker

A small SVG glider icon (rotated to current heading) placed as a Leaflet `DivIcon`.
Updates every animation frame via `requestAnimationFrame` (interpolating between 1-second
physics ticks for smooth rendering).

---

## Phase 6 — Files to Create / Modify

### New files

| File | Purpose |
|---|---|
| `static/js/task-simulator.js` | Simulator engine + Leaflet integration |
| `static/css/task-simulator.css` | Control bar, HUD, thermal circles, glider icon |

### Modified files

| File | Change |
|---|---|
| `templates/index.html` | Add Simulate button in task sidebar; add simulator control bar `<div>`; add thermal placement modal |
| `static/js/task-planner.js` | Expose `map`, `taskPoints`, polar data on the `TaskPlanner` instance for the simulator to reference |
| `backend/models/i18n.py` | Register new i18n key group `sim.*` |
| `backend/translations/en.json` (+ other locales) | Add `sim.*` strings |

---

## Phase 7 — i18n Keys Required

```json
"sim.simulate":          "Simulate",
"sim.stop":              "Stop Simulation",
"sim.pause":             "Pause",
"sim.resume":            "Resume",
"sim.speed":             "Speed",
"sim.altitude":          "Altitude",
"sim.vario":             "Vario",
"sim.netto":             "Netto",
"sim.ias":               "IAS",
"sim.stf":               "Speed to Fly",
"sim.maccready":         "MacCready",
"sim.start_altitude":    "Start Altitude",
"sim.start_position":    "Start Position",
"sim.add_thermal":       "Add Thermal",
"sim.thermal_strength":  "Lift Strength",
"sim.thermal_radius":    "Core Radius",
"sim.thermals":          "Thermals",
"sim.no_task":           "No task loaded",
"sim.task_complete":     "Task complete!",
"sim.landed":            "Landed out"
```

---

## Implementation Order

1. **`task-simulator.js`** — `SimulatorEngine` class with position integration + polar sink
2. **Glider marker + tick loop** — render glider on map, 1-Hz physics + 60-Hz visual
3. **MacCready input + STF calculation** — slider in sidebar, STF readout in HUD
4. **Thermal simulation** — single thermal first, then multi-thermal + map placement
5. **OZ/sector crossing detection** — advance task on crossing
6. **Snail trail** — vario-coloured polyline
7. **Keyboard steering** — heading/speed/Mc keys
8. **Simulator control bar HTML + CSS** — play/pause/stop, HUD values
9. **i18n strings** — all `sim.*` keys in all translation files
10. **Auto-seed thermals** — scatter thermals around task on start

Each step is independently testable in the browser before moving to the next.
