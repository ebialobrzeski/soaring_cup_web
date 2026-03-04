# Soaring CUP Web — Development Session Notes

> Last updated: March 4, 2026

## Project Overview

Flask-based web app for editing soaring/gliding CUP waypoint files with an interactive map, task planner, and list view. Deployed via Docker with Cloudflare tunnel support.

## Tech Stack

- **Backend**: Flask 3.1.2, Python 3.14
- **Frontend**: Vanilla JS, Leaflet 1.9.4 + MarkerCluster 1.4.1, qrcodejs@1.0.0
- **CDNs**: unpkg (leaflet, markercluster), jsdelivr (qrcodejs), FontAwesome
- **Icons**: XCSoar-style waypoint icons via `icon-mapping.js`
- **Session**: UUID-based JSON files in `data/` folder

## File Structure (Key Files)

| File | Purpose |
|------|---------|
| `app.py` | Flask routes: waypoint CRUD, file upload/download, elevation API, task export/import/QR/save/load |
| `backend/file_io.py` | CUP/CSV parsing & writing, `write_task_cup()`, `parse_task_cup()` |
| `backend/models.py` | `Waypoint` class with `to_dict()`, `from_dict()`, `to_cup_string()` |
| `backend/config.py` | `STYLE_OPTIONS` (22 waypoint types) |
| `templates/index.html` | 3 tabs (Map View, Task Planner, List View), OZ modal, QR modal |
| `static/js/app.js` | `SoaringCupEditor` class — main app, map markers, tab switching |
| `static/js/task-planner.js` | `TaskPlanner` class — task creation, OZ editing, bearing rotation, import/export, session persistence |
| `static/js/icon-mapping.js` | `WAYPOINT_ICONS`, `createWaypointIcon()`, `getWaypointIcon()` |
| `static/css/style.css` | All styling |
| `sample/waypoints_epbk_100km.cup` | 61 waypoints merged from national + EPBK files, within 100km of EPBK |

## Features Implemented

### Core
- CUP/CSV file upload, parse, edit, download
- Interactive Leaflet map with clustered waypoint markers (XCSoar icons)
- List view with sortable waypoint table
- Elevation lookup via Open Elevation API
- Session persistence (waypoints survive page reload)

### Task Planner
- **Task creation**: Search waypoints, add to task, reorder with drag/move buttons
- **Observation Zones**: Per-point OZ editing modal with presets (Cylinder, FAI Sector, BGA Keyhole, Start/Finish Line)
- **Default OZ**: Start = Line (5km half-width), Turn points = FAI Sector (R1=3000, A1=45, R2=500, A2=180)
- **Interactive bearing rotation**: Click "Change Bearing" on a task point → mouse-rotate sector direction on map → click to confirm
- **Task point popups**: Click markers for Edit OZ, Change Bearing, Auto bearing, Add Again (reuse as finish), Remove
- **Waypoint markers on task map**: XCSoar icons at 18px, skipping points already in task
- **Export**: Download as CUP file (SeeYou/XCSoar/LK8000 compatible) with `-----Related Tasks-----` section
- **QR Code**: Generates standardized XCTSK v2 QR code (scannable by XCTrack, XCSoar, LK8000) — encodes task data directly, no server needed
- **Import**: Open .cup task files — matches waypoints by name then coordinates, loads OZ settings
- **Session persistence**: Task state auto-saves on every change, restores on page load

### UI Extras
- "Buy me a coffee" banner (top-right, links to buymeacoffee.com/emil.b)
- Performance optimizations: `removeOutsideVisibleBounds: true`, `disableClusteringAtZoom: 13`, `chunkedLoading: true`

## Key API Endpoints

| Method | Route | Purpose |
|--------|-------|---------|
| POST | `/api/task/export` | Export task as JSON with CUP content |
| POST | `/api/task/download` | Download task as .cup file |
| POST | `/api/task/qr` | Save CUP file, return download token for QR |
| GET | `/dl/<token>` | Serve task file by QR download token |
| POST | `/api/task/import` | Upload & parse a .cup task file |
| POST | `/api/task/save` | Save task state to session |
| GET | `/api/task/load` | Load saved task state from session |

## Key Code Details

### TaskPlanner class (`task-planner.js`)
- `taskPoints[]` — array of `{waypointIndex, waypoint, obsZone}`
- `addPoint(idx)` — adds waypoint with default OZ (FAI sector for TPs, line for start)
- `refreshUI()` — renders list + map + summary + buttons + saves session
- `showQR()` — calls `/api/task/qr`, encodes download URL in QR code
- `importTask(file)` — uploads file to `/api/task/import`, populates task
- `saveTaskState()` / `loadTaskState()` — session persistence (fire-and-forget save, async load on init)
- `startBearingEdit(idx)` / `stopBearingEdit(confirm)` — interactive mouse rotation
- `drawObsZone()` — respects `directionMode: 'fixed'` with `fixedBearing`
- `bisectorBearing()` — XCSoar convention (outside the turn)

### Session storage (`app.py`)
- `get_session_data_file()` — returns `data/session_{uuid}.json`
- Session JSON contains: `{waypoints: [...], current_filename: "", task: {name, noStart, taskTime, points: [{waypointIndex, obsZone}]}}`
- `set_session_waypoints()` preserves task data when updating waypoints
- `set_session_task()` preserves waypoint data when updating task

### CUP Task Format (`file_io.py`)
```
name,code,country,lat,lon,elev,style,rwdir,rwlen,rwwidth,freq,desc
"WP1","CODE",...
-----Related Tasks-----
"Task Name","WP1","WP2","WP3","WP1"
Options,NoStart=12:00:00,TaskTime=03:00:00,WpDis=True
ObsZone=0,Style=0,R1=5000m,A1=90,R2=0m,A2=180,A12=0.0,Line=1,Move=True,Reduce=False
ObsZone=1,Style=1,R1=3000m,A1=45,R2=500m,A2=180,A12=0.0,Line=0,Move=True,Reduce=False
```

## Recent Changes (This Session)

1. **FAI Sector default for turn points** — Changed from cylinder (R1=500, A1=180) to FAI sector (R1=3000, A1=45, R2=500, A2=180)
2. **QR code fix** — Now generates a server-side download link instead of encoding file content; always works regardless of file size
3. **Removed "Add Turnpoint on Map" and "Fit All" buttons** — Cleaned up HTML, JS event listeners, `addOnMapMode` property, and CSS
4. **Task file import** — New `parse_task_cup()` in backend, `/api/task/import` endpoint, "Open Task File" button in sidebar
5. **Task session persistence** — Auto-saves task state to session JSON; restores on page load via `saveTaskState()`/`loadTaskState()`
6. **XCTSK v2 QR code** — Replaced server-download-link QR with standardized XCTSK v2 format; polyline-encoded coordinates, OZ overrides (`o` field), start/goal settings; entirely client-side generation

## Known Considerations

- QR download tokens are stored in-memory (`_qr_downloads` dict in `app.py`) — lost on server restart
- The `/api/task/export` endpoint (returns CUP content as JSON) is still present but no longer used by the QR flow
- Task import matches waypoints by name first, then by coordinate proximity (~500m threshold)
- If imported task waypoints aren't in the session, they're loaded from the file's waypoint section

## How to Run

```bash
pip install -r requirements.txt
python app.py
# Opens on http://localhost:5000
```
