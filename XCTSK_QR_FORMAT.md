# XCTSK QR Code Standard

**Reference:** [XCTrack Competition Interfaces – Task Definition Format 2 (QR codes)](https://xctrack.org/Competition_Interfaces.html#task-definition-format-2---for-qr-codes)

## Overview

The XCTSK QR format allows soaring/paragliding tasks to be shared as scannable QR codes, typically used with the [XCTrack](https://xctrack.org/) app. A QR code encodes a compact JSON payload prefixed with `XCTSK:`.

There are two versions:

| Version | Use case | File extension |
|---------|----------|----------------|
| v1 | `.xctsk` file download (verbose JSON) | `.xctsk` |
| v2 | QR code (compact, polyline-encoded coords) | — (QR only) |

---

## QR String Format

The raw string encoded into the QR image is:

```
XCTSK:<compact JSON>
```

The JSON is serialized **without whitespace** (`separators=(',', ':')` in Python / `JSON.stringify` with no indent in JS).

---

## XCTSK v2 JSON Schema (QR)

```json
{
  "taskType": "CLASSIC",
  "version": 2,
  "t": [ /* array of turnpoints */ ],
  "s": {
    "g": [],        // start time gates, e.g. ["10:00:00Z"]
    "d": 1,         // start direction: 1 = ENTRY
    "t": 1          // start type: 1 = RACE
  },
  "g": {
    "t": 2          // goal type: 1 = LINE, 2 = CYLINDER
  }
}
```

### Top-level fields

| Field | Type | Description |
|-------|------|-------------|
| `taskType` | string | Always `"CLASSIC"` |
| `version` | integer | Always `2` for QR format |
| `t` | array | Ordered list of turnpoints (see below) |
| `s` | object | Start settings |
| `s.g` | array of strings | Start time gates in `"HH:MM:SSZ"` format (empty = open start) |
| `s.d` | integer | Start direction: `1` = ENTRY |
| `s.t` | integer | Start type: `1` = RACE |
| `g` | object | Goal settings |
| `g.t` | integer | Goal type: `1` = LINE, `2` = CYLINDER |

---

## Turnpoint Object

Each entry in the `t` array:

```json
{
  "z": "<polyline-encoded string>",
  "n": "Waypoint Name",
  "d": "WPT_CODE",
  "t": 2,
  "o": {
    "l": 1,
    "a1": 90
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `z` | string | Yes | Polyline-encoded (longitude, latitude, altitude, radius) |
| `n` | string | Yes | Waypoint name |
| `d` | string | No | Waypoint description/code (omit if empty to keep QR compact) |
| `t` | integer | First/last only | Point type: `2` = SSS (start), `3` = ESS (finish) |
| `o` | object | No | Observation zone overrides (omit if all defaults) |

### Observation zone overrides (`o`)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `l` | integer | 0 | `1` = observation zone is a line |
| `a1` | integer | 180 | Half-angle of the outer sector in degrees (`180` = full cylinder) |

Only include `o` (and only include the relevant sub-fields) when values differ from defaults, to keep the QR code as compact as possible.

> **Important limitation:** The v2 QR format encodes only `r1` (outer radius, via `z`), `a1` (sector half-angle), and the line flag. There are **no fields for inner radius (`r2`) or inner half-angle (`a2`)**. Complex composite shapes such as keyholes are therefore approximated — only their outer sector geometry survives the QR round-trip.

---

## Supported Observation Zone Shapes

The XCTSK v2 QR format defines two OZ override fields. However their actual uptake by receiving apps is very limited — see the [App Compatibility](#app-compatibility-xcsoar--lk8000) section below for what each app actually reads.

| Shape | CUP params | `z` radius | `o.a1` | `o.l` | Format fidelity |
|-------|-----------|-----------|--------|-------|----------|
| **Cylinder** | R1=any, A1=180, R2=0 | R1 | *(omit – default)* | — | ✅ Full |
| **FAI Sector** | R1=3000, A1=45, R2=500, A2=180 | 3000 m | `45` | — | ⚠️ Outer sector angle encoded; inner 500 m cylinder **not representable** |
| **BGA Keyhole** | R1=10000, A1=45, R2=500, A2=180 | 10000 m | `45` | — | ⚠️ Same — outer sector only |
| **BGA Enhanced** | R1=10000, A1=90, R2=500, A2=180 | 10000 m | `90` | — | ⚠️ Outer sector only |
| **Start Line** | R1=half-width, A1=90, Line=1 | half-width | *(omit)* | `1` | ⚠️ See note on `o.l` vs `g.t` |
| **Finish Line** | R1=half-width, A1=90, Line=1 | half-width | *(omit)* | `1` | ✅ Signal via `g.t=1` — respected by LK8000 |
| **Custom sector** | R1=any, A1=any | R1 | A1 value | — | ⚠️ Outer sector only |

> **Critical:** There are **no fields for `r2` or `a2`** in the XCTSK v2 format. Complex composite shapes (keyholes, FAI sectors) lose their inner cylinder entirely. There is no workaround — use the `.cup` or `.tsk` file formats if full OZ fidelity is required.

---

## App Compatibility: XCSoar & LK8000

This section documents exactly how XCSoar and LK8000 parse the XCTSK v2 QR format and the `.cup` task file format, based on reading their source code directly.

### XCTSK v2 QR — XCSoar

**Source:** [`src/Task/XCTrackTaskDecoder.cpp`](https://github.com/XCSoar/XCSoar/blob/master/src/Task/XCTrackTaskDecoder.cpp)

XCSoar reads:
- `z` field → location (lon/lat) + radius → creates **`CylinderZone` for every turnpoint**
- `n` field → waypoint name
- Position in `t` array: first = Start, last = Finish, rest = Intermediate

XCSoar **ignores**:
- The entire `o` field (`o.a1` and `o.l`) — all zones become cylinders
- `g.t` (goal type) — marked `TODO` in source; no LINE finish support via QR
- `s.g` (time gates) — marked `TODO`
- `s.d`, `s.t`, `g.d` — all marked `TODO`

> **Result:** When XCSoar scans an XCTSK v2 QR code, it produces a pure cylinder task. Sector angles, line OZs, and time gates are ignored entirely.

---

### XCTSK v2 QR — LK8000

**Source:** [`Common/Source/SaveLoadTask/LoadXCTrackTask.cpp`](https://github.com/LK8000/LK8000/blob/master/Common/Source/SaveLoadTask/LoadXCTrackTask.cpp)

LK8000 reads:
- `z` field → location (lon/lat) + radius (element `[3]`) → all turnpoints set to `sector_type_t::CIRCLE`
- Point type `t=2` (SSS) → start; `t=3` (ESS) → `sector_type_t::ESS_CIRCLE`
- `g.t = 1` → `FinishLine = sector_type_t::LINE` ✅
- `g.t = 2` (or absent) → `FinishLine = sector_type_t::CIRCLE`
- `s.g` (time gates) → PG time gates (open time, gate count, interval) ✅

LK8000 **ignores**:
- The entire `o` field (`o.a1` and `o.l`) — all intermediate/start zones become circles
- `s.d`, `s.t`, `g.d` — not used

> **Result:** LK8000 creates a cylinder task with correct radii and time gates. If the finish is a **line** (`g.t=1`), LK8000 honours that. Start/intermediate OZ shapes are all plain cylinders.

---

### OZ shape behaviour summary (XCTSK v2 QR)

| OZ Type | XCSoar | LK8000 |
|---------|--------|--------|
| Cylinder (any radius) | ✅ Cylinder with correct radius | ✅ Circle with correct radius |
| FAI Sector (R1=3000, A1=45) | ❌ Cylinder R=3000 (sector lost) | ❌ Circle R=3000 (sector lost) |
| BGA Keyhole | ❌ Cylinder with outer radius | ❌ Circle with outer radius |
| Start Line (`o.l=1`) | ❌ Cylinder (o field ignored) | ❌ Circle (o field ignored) |
| Finish Line (`o.l=1` + `g.t=1`) | ❌ Cylinder (g.t TODO) | ✅ LINE finish (`g.t` read) |
| Time gates (`s.g`) | ❌ Ignored (TODO) | ✅ PG time gates applied |

---

### CUP task files — XCSoar

**Source:** [`src/Task/TaskFileSeeYou.cpp`](https://github.com/XCSoar/XCSoar/blob/master/src/Task/TaskFileSeeYou.cpp)

XCSoar reads all `ObsZone=` parameters from `.cup` task files and maps them to internal OZ types:

| CUP OZ parameters | XCSoar OZ type |
|---|---|
| A1=180 | `CylinderZone` |
| A1<180, Style=any (racing task, non-intermediate) | `LineSectorZone` if Line=1; else `CylinderZone` |
| R1=3000, A1=45, R2=500, A2=180 (racing, intermediate) | `KeyholeZone::CreateCustomKeyholeZone(R1=3000, A1=45°)` with inner 500 m |
| R1=10000, A1=45, R2=500, A2=180 | `KeyholeZone::CreateCustomKeyholeZone` (BGA keyhole) |
| R1=20000, A1=45, R2=500, A2=180 | `KeyholeZone::CreateBGAFixedCourseZone` |
| R1=10000, A1=90, R2=500, A2=180 | `KeyholeZone::CreateBGAEnhancedOptionZone` |
| A1<180, Style=Symmetrical | `SymmetricSectorZone` / FAI sector |
| Line=1 (start or finish only) | `LineSectorZone` (length = R1 × 2) |

> XCSoar matches the exact parameter combinations above. For a racing task, intermediate line OZs are not supported and fall back to sectors or cylinders.

---

### CUP task files — LK8000

**Source:** [`Common/Source/SaveLoadTask/LoadCupTask.cpp`](https://github.com/LK8000/LK8000/blob/master/Common/Source/SaveLoadTask/LoadCupTask.cpp)

LK8000 reads all `ObsZone=` parameters and maps them using these rules in order of priority:

| Priority | Condition | LK8000 sector type |
|----------|-----------|-------------------|
| 1st | `Line=1` | `LINE` (start/finish only; intermediate line logs a warning and falls back) |
| 2nd | `R1 > 0` **and** `R2 > 0` | `sector_type_t::DAe` (DAeC/Keyhole — LK8000's only composite zone type) |
| 3rd | `A1 ≈ 180` | `CIRCLE` |
| 4th | `A1 < 180`, `Style=0` (Fixed) | `SECTOR` with fixed bearing from `A12` ± `A1` |
| 4th | `A1 < 180`, `Style=1` (Symmetrical) | `SECTOR` with auto bisector bearing |
| 4th | `A1 < 180`, `Style=2` (To next) | `SECTOR` pointing toward next TP |
| 4th | `A1 < 180`, `Style=3` (To prev) | `SECTOR` pointing toward previous TP |
| 4th | `A1 < 180`, `Style=4` (To start) | `SECTOR` pointing toward start TP |

> **Note:** LK8000 treats **any turnpoint with both R1 and R2 defined** as a `DAe`-style (keyhole-like) sector, regardless of the specific radii values. This means FAI sectors (R2=500, A2=180), BGA keyholes (R2=500, A2=180), and custom composite zones all receive the same treatment.

---

### OZ shape behaviour summary (CUP task files)

| OZ Type | XCSoar result | LK8000 result |
|---------|---------------|---------------|
| Cylinder (A1=180) | ✅ CylinderZone | ✅ CIRCLE |
| FAI Sector (R1=3000, A1=45, R2=500, A2=180) | ✅ Custom KeyholeZone (3000/45°/500m inner) | ✅ DAe sector (R1+R2 both set) |
| BGA Keyhole (R1=10000, A1=45, R2=500, A2=180) | ✅ Custom KeyholeZone | ✅ DAe sector |
| BGA Fixed Course (R1=20000, A1=45, R2=500) | ✅ BGAFixedCourseZone | ✅ DAe sector |
| BGA Enhanced (R1=10000, A1=90, R2=500) | ✅ BGAEnhancedOptionZone | ✅ DAe sector |
| Start/Finish Line (Line=1) | ✅ LineSectorZone (length=2×R1) | ✅ LINE |
| Symmetrical Sector (A1<180, Style=1) | ✅ SymmetricSectorZone (auto-bisected) | ✅ SECTOR (bisected) |
| Fixed Sector (A1<180, Style=0, A12=bearing) | Cylinder (racing; fixed not supported) | ✅ SECTOR (fixed bearing) |
| Intermediate Line | Falls back to sector or cylinder | ⚠️ Warning logged; falls back |

> **Takeaway:** For full OZ fidelity, always distribute tasks as `.cup` files. Both apps reconstruct keyholes and sectors correctly from CUP ObsZone parameters, with the only difference being XCSoar's named zone types vs LK8000's `DAe` catch-all.

---

## Coordinate Encoding (`z` field)

The `z` field encodes four values using **Google's Polyline Algorithm**, concatenated in this order:

1. `round(longitude × 10⁵)`
2. `round(latitude × 10⁵)`
3. `round(altitude_m)`
4. `round(radius_m)`

### Google Polyline Algorithm (per number)

```
1. Left-shift the value by 1.
2. If the original value was negative, invert all bits (~).
3. Split into 5-bit chunks, least-significant first.
4. OR each chunk (except the last) with 0x20 to signal "more follows".
5. Add 63 to each chunk and output as a Unicode character.
```

#### Python implementation

```python
def _polyline_encode_num(num):
    pnum = (num << 1) if num >= 0 else ~(num << 1)
    result = []
    while pnum > 0x1f:
        result.append(chr(((pnum & 0x1f) | 0x20) + 63))
        pnum >>= 5
    result.append(chr(pnum + 63))
    return ''.join(result)

def encode_z(lon, lat, alt, radius):
    return (_polyline_encode_num(round(lon * 1e5)) +
            _polyline_encode_num(round(lat * 1e5)) +
            _polyline_encode_num(round(alt)) +
            _polyline_encode_num(round(radius)))
```

#### JavaScript implementation

```js
_encodePolylineNum(num) {
    let pnum = num << 1;
    if (num < 0) pnum = ~pnum;
    let result = '';
    while (pnum > 0x1f) {
        result += String.fromCharCode(((pnum & 0x1f) | 0x20) + 63);
        pnum >>>= 5;
    }
    result += String.fromCharCode(63 + pnum);
    return result;
}

_encodeXctskZ(lon, lat, alt, radius) {
    return this._encodePolylineNum(Math.round(lon * 1e5)) +
           this._encodePolylineNum(Math.round(lat * 1e5)) +
           this._encodePolylineNum(Math.round(alt)) +
           this._encodePolylineNum(Math.round(radius));
}
```

---

## QR Code Parameters

Recommended QR generation settings for maximum compatibility:

| Parameter | Value |
|-----------|-------|
| Error correction | L (lowest) — keeps QR smaller |
| Encoding | UTF-8 bytes |
| Version | Auto (fit to data) |
| Box size | 6–8 px (for on-screen display) |
| Border | 2 modules |

---

## Complete Example

A 3-turnpoint task (start → TP → finish/line):

```json
XCTSK:{"taskType":"CLASSIC","version":2,"t":[{"z":"_~`jHsdofBoCgN","n":"Gawler","d":"GAWL","t":2},{"z":"yvpjHiqrfBcBgN","n":"Kapunda","d":"KAPN"},{"z":"m_qjHunrfBcBwJ","n":"Gawler Finish","d":"GAWF","t":3,"o":{"l":1}}],"s":{"g":["10:00:00Z"],"d":1,"t":1},"g":{"t":1}}
```

Decoded:

- **Start (SSS):** Gawler, code `GAWL`, 500 m radius cylinder, race start with gate at 10:00 UTC
- **Turnpoint:** Kapunda, code `KAPN`, 500 m radius cylinder
- **Finish (ESS):** Gawler Finish, code `GAWF`, line goal → `"o":{"l":1}`, goal type `"g":{"t":1}`

---

## XCTSK v1 JSON Schema (file download)

The `.xctsk` file format uses v1 — a verbose, human-readable JSON structure with no polyline encoding. It is **not** used for QR codes.

```json
{
  "taskType": "CLASSIC",
  "version": 1,
  "turnpoints": [
    {
      "radius": 3000,
      "type": "SSS",
      "waypoint": {
        "name": "Gawler",
        "description": "GAWL",
        "lat": -34.6,
        "lon": 138.75,
        "altSmoothed": 100
      }
    },
    {
      "radius": 500,
      "waypoint": { "name": "Kapunda", "description": "KAPN", "lat": -34.33, "lon": 138.91, "altSmoothed": 280 }
    },
    {
      "radius": 500,
      "type": "ESS",
      "waypoint": { "name": "Gawler Finish", "description": "GAWF", "lat": -34.6, "lon": 138.75, "altSmoothed": 100 }
    }
  ],
  "sss": {
    "type": "RACE",
    "direction": "EXIT",
    "timeGates": ["10:00:00"]
  },
  "goal": {
    "type": "LINE"
  }
}
```

### v1 field reference

| Field | Values | Description |
|-------|--------|-------------|
| `version` | `1` | V1 file format |
| `turnpoints[].type` | `"SSS"`, `"ESS"` | Present only on first and last points |
| `turnpoints[].radius` | integer (metres) | Observation zone radius |
| `sss.type` | `"RACE"` | Start type |
| `sss.direction` | `"EXIT"`, `"ENTRY"` | Start crossing direction |
| `sss.timeGates` | array of `"HH:MM:SS"` strings | Start time gate(s) |
| `goal.type` | `"LINE"`, `"CYLINDER"` | Goal observation zone shape |

---

## Implementation in This Project

| Location | Purpose |
|----------|---------|
| [app.py](app.py#L529) – `_polyline_encode_num`, `_xctsk_encode_z`, `build_xctsk_payload` | Server-side v2 payload builder |
| [app.py](app.py#L597) – `/api/task/xctsk-qr` | API endpoint: returns PNG QR as base64 data URL |
| [app.py](app.py#L838) – `_build_xctsk_from_stored` | Rebuilds v2 payload from saved share data |
| [backend/file_io.py](backend/file_io.py#L569) – `write_task_xctsk` | Generates v1 `.xctsk` file content |
| [static/js/task-planner.js](static/js/task-planner.js#L1068) – `_encodePolylineNum`, `_encodeXctskZ`, `buildXctskPayload` | Client-side v2 payload builder (mirrors server) |
