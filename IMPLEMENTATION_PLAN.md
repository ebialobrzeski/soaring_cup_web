# Soaring Cup Web — Implementation Plan

> **Scope**: Authentication, user tiers, persistent storage, public/private data sharing, and AI Planner gating.
> The AI Planner itself (weather, polars, optimization) is specified separately in [`AI_TASK_PLANNER.md`](AI_TASK_PLANNER.md) and will only be implemented **after** everything in this document is complete.

---

## Table of Contents

1. [Current State](#1-current-state)
2. [Goals](#2-goals)
3. [Architecture Overview](#3-architecture-overview)
4. [Phase 1 — Database Foundation](#4-phase-1--database-foundation)
5. [Phase 2 — Authentication](#5-phase-2--authentication)
6. [Phase 3 — User Tiers](#6-phase-3--user-tiers)
7. [Phase 4 — Persistent Waypoints & Tasks](#7-phase-4--persistent-waypoints--tasks)
8. [Phase 5 — Public/Private Visibility & Browsing](#8-phase-5--publicprivate-visibility--browsing)
9. [Phase 6 — AI Planner Gating](#9-phase-6--ai-planner-gating)
10. [Database Schema](#10-database-schema)
11. [API Endpoints](#11-api-endpoints)
12. [Frontend Changes](#12-frontend-changes)
13. [File Inventory](#13-file-inventory)
14. [Dependencies](#14-dependencies)
15. [Configuration Changes](#15-configuration-changes)
16. [Migration Strategy](#16-migration-strategy)
17. [Security Considerations](#17-security-considerations)
18. [Implementation Order — Step by Step](#18-implementation-order--step-by-step)

---

## 1. Current State

> **Last verified: March 2026.** Phases 1 and 2 (backend) are substantially complete. Frontend auth UI (Phase 2 step 3) and Phases 3–6 remain to be done.

| Aspect | Status |
|--------|--------|
| **Framework** | Flask 3.1.2 — `app.py` is thin; blueprints already registered |
| **Frontend** | Vanilla JS + Shoelace 2 web components + Leaflet maps, no build step |
| **Storage** | Anonymous session JSON files in `data/` directory (still in use) |
| **Database** | ✅ PostgreSQL connected — `backend/db.py`, scoped session, `init_db()` in `app.py` |
| **Authentication** | ✅ Backend complete — `Flask-Login`, `auth_bp`, `auth_service`, user loader in `app.py` |
| **User model** | ✅ `backend/models/user.py` — `User` SQLAlchemy model, migration `001` applied |
| **Authorization** | ✅ `backend/utils/auth_decorators.py` — `@login_required`, `@premium_required`, `@admin_required` |
| **Architecture rules** | ✅ Enforced — blueprints in `backend/routes/`, services in `backend/services/`, models in `backend/models/` |
| **Existing models** | ✅ `WaypointFile`, `WaypointEntry`, `SavedTask`, `User` — all SQLAlchemy ORM models created |
| **Config** | ✅ `backend/config.py` — loads `.ai.env` then `.env`, exports `DATABASE_URL`, AI keys, `TIER_LIMITS` |
| **Migration runner** | ✅ `backend/migrate.py` + `backend/migrations/` — 001–003 SQL files exist |
| **Task storage** | `localStorage` in browser + session JSON on server (DB routes not yet wired) |
| **Deployment** | Docker + gunicorn, Cloudflare tunnel |
| **AI gliding forecast DB** | ✅ Existing PostgreSQL instance already has tables from [`AI_gliding_forecast`](https://github.com/ebialobrzeski/AI_gliding_forecast): `airports`, `forecast_models`, `forecast_requests`, `forecasts`, `ai_descriptions` (and possibly `glider_polars`, `weather_cache`) — **do not re-create; detect and reuse** |

### Key Constraints

- **No React or build tooling** — all frontend changes are vanilla JS + Jinja2 templates.
- **Shoelace 2** is the component library — use `<sl-dialog>`, `<sl-input>`, `<sl-button>`, `<sl-badge>`, etc. for all new UI.
- **Architecture instructions** require: Flask Blueprints for each feature, services for business logic, models for data only, parameterized queries or ORM.
- The `app.py` monolith has already been thinned — new code continues to go into `backend/routes/`, `backend/services/`, etc.
- **AI gliding forecast tables already exist in the DB** — before running any migration that creates `airports`, `forecast_models`, `glider_polars`, or `weather_cache`, check with `IF NOT EXISTS` guards and verify the existing schema matches expectations. Do not drop and recreate.

---

## 2. Goals

In priority order:

1. **Connect to PostgreSQL** — establish DB layer, config, migrations
2. **Authentication** — registration, login, logout, session management
3. **User tiers** — free vs. premium, enforced server-side
4. **Persistent storage** — save waypoint files and tasks to the database, owned by users
5. **Visibility rules** — free users: public only; premium users: public or private
6. **Browse & discover** — popup dialogs to browse public waypoints/tasks and user's own private data
7. **AI Planner gate** — premium-only access to the AI Planner tab (implemented later per `AI_TASK_PLANNER.md`)

---

## 3. Architecture Overview

```
app.py                          ← registers blueprints, middleware, error handlers (thin)
backend/
  config.py                     ← env vars, DB URL, tier limits, feature flags
  db.py                         ← SQLAlchemy engine + session factory
  models/
    __init__.py
    user.py                     ← User, UserTier
    waypoint_file.py            ← WaypointFile, WaypointFileEntry
    task.py                     ← SavedTask
    base.py                     ← declarative base, common mixins
  routes/
    __init__.py
    auth.py                     ← Blueprint: /auth/*
    waypoints.py                ← Blueprint: /api/waypoints/* (refactored from app.py)
    tasks.py                    ← Blueprint: /api/tasks/*
    browse.py                   ← Blueprint: /api/browse/*
  services/
    auth_service.py             ← registration, login, password hashing, token management
    user_service.py             ← tier checks, profile management
    waypoint_service.py         ← CRUD for waypoint files in DB
    task_service.py             ← CRUD for saved tasks in DB
    browse_service.py           ← search/filter public + user-owned data
  migrations/
    001_initial_schema.sql      ← users, tiers
    002_waypoint_files.sql      ← waypoint file storage
    003_saved_tasks.sql         ← task storage
  utils/
    auth_decorators.py          ← @login_required, @premium_required
static/
  js/
    auth.js                     ← login/register/logout UI logic
    browse-dialog.js            ← browse waypoints/tasks popup logic
templates/
  index.html                    ← add auth header, browse dialogs, tier badges
```

---

## 4. Phase 1 — Database Foundation ✅ COMPLETE

### 4.1 Install Dependencies ✅

All packages are already in `requirements.txt`:

```
SQLAlchemy>=2.0
psycopg2-binary>=2.9
python-dotenv>=1.0
Flask-Login>=0.6
```

### 4.2 Environment Configuration ✅

`backend/config.py` loads `.ai.env` first, then `.env` (override). Exports: `DATABASE_URL`, `SECRET_KEY`, `BASE_URL`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `DEEPSEEK_API_KEY`, `IMGW_API_BASE_URL`, `WINDY_API_KEY`, `OPENWEATHER_API_KEY`, `TIER_LIMITS`.

### 4.3 Database Connection Layer ✅

`backend/db.py` is complete: `create_engine`, scoped session, `init_db(app)`, `get_db()`, teardown on request end.

### 4.4 Migration Runner ✅

`backend/migrate.py` exists. Migration files `001_initial_schema.sql`, `002_waypoint_files.sql`, `003_saved_tasks.sql` all exist. Runner tracks applied migrations in `schema_migrations`.

> **Note on existing AI gliding forecast tables**: The PostgreSQL database already contains tables created by the [`AI_gliding_forecast`](https://github.com/ebialobrzeski/AI_gliding_forecast) project (`airports`, `forecast_models`, `forecast_requests`, `forecasts`, `ai_descriptions`, and possibly `glider_polars`, `weather_cache`). Before writing AI Planner migrations 004+, run `\dt` against the live DB to inventory what already exists. Use `IF NOT EXISTS` on every `CREATE TABLE`. If the existing schema is compatible, skip creation; if it diverges, add an `ALTER TABLE` migration rather than dropping and recreating.

---

## 5. Phase 2 — Authentication ✅ BACKEND COMPLETE / Frontend pending

### 5.1 User Model ✅

`backend/models/user.py` — `User` SQLAlchemy model exists. Migration `001_initial_schema.sql` creates the `users` table. Flask-Login interface (`is_authenticated`, `is_active`, `get_id()`) is implemented.

### 5.2 Auth Blueprint ✅

`backend/routes/auth.py` — `auth_bp` registered in `app.py`. Endpoints implemented: `/auth/register`, `/auth/login`, `/auth/logout`, `/auth/me`, `/auth/change-password`, `/auth/admin/set-tier`.

### 5.3 Auth Service ✅

`backend/services/auth_service.py` — `register_user()`, `authenticate()`, `change_password()`, `get_user_by_id()` all implemented with validation rules.

### 5.4 Auth Decorators ✅

`backend/utils/auth_decorators.py` — `@login_required`, `@premium_required`, `@admin_required` all implemented.

### 5.5 Frontend Auth UI ❌ TODO

All auth UI uses Shoelace dialogs within the existing `index.html` — **no separate login page**. The app loads as-is (anonymous mode) and the user can optionally log in.

**New UI elements in the header:**
- **Logged out**: "Log in" button → opens login dialog; "Sign up" link inside the dialog
- **Logged in**: User avatar/name badge + tier indicator + "Log out" button

**Dialogs:**
- `#login-dialog` — email + password fields, submit, "Create account" link
- `#register-dialog` — email + display name + password + confirm password, submit

**Behavior:**
- The app remains fully functional for anonymous users (current behavior preserved)
- Logging in unlocks: saving to DB, loading from DB, seeing private items
- Anonymous users can still upload CUP files, edit waypoints, plan tasks, and export — all via the existing session JSON system

### 5.6 Anonymous-to-Authenticated Transition

When a user logs in and has existing anonymous session data:
- Prompt: "You have unsaved waypoints in your session. Save them to your account?"
- If yes: create a new WaypointFile from the session data, owned by the user
- If no: discard session data and start with user's saved files

---

## 6. Phase 3 — User Tiers ✅ BACKEND COMPLETE / Frontend pending

### 6.1 Tier Definitions

| Feature | Free | Premium | Admin |
|---------|------|---------|-------|
| Upload/edit/export waypoints & tasks | ✅ | ✅ | ✅ |
| Save waypoint files to DB | ✅ (public only) | ✅ (public or private) | ✅ |
| Save tasks to DB | ✅ (public only) | ✅ (public or private) | ✅ |
| Browse public waypoints/tasks | ✅ | ✅ | ✅ |
| Max saved waypoint files | 5 | 50 | Unlimited |
| Max saved tasks | 10 | 100 | Unlimited |
| AI Planner tab | ❌ | ✅ | ✅ |
| Share links (24h expiry) | ✅ | ✅ (permanent) | ✅ |
| Manage users | ❌ | ❌ | ✅ |

### 6.2 Tier Enforcement ✅

`backend/services/user_service.py` — `can_save_file()`, `can_save_task()`, `can_set_private()`, `can_access_ai_planner()`, `get_tier_limits()`, `set_user_tier()` all implemented. `TIER_LIMITS` dict is in `backend/config.py`.

### 6.3 Tier Management ✅

`/auth/admin/set-tier` endpoint implemented in `auth_bp`.

---

## 7. Phase 4 — Persistent Waypoints & Tasks

### 7.1 Waypoint File Model ✅

`backend/models/waypoint_file.py` — `WaypointFile`, `WaypointEntry` ORM models exist. `backend/migrations/002_waypoint_files.sql` applied.

Schema (implemented):

```
waypoint_files — UUID pk, owner_id FK, name, description, is_public, waypoint_count, timestamps, UNIQUE(owner_id, name)
waypoint_entries — UUID pk, file_id FK, name, code, country, lat/lon, elevation, style, runway fields, frequency, description, sort_order
```

### 7.2 Saved Task Model ✅

`backend/models/task.py` — `SavedTask` ORM model exists with `JSONB task_data`. `backend/migrations/003_saved_tasks.sql` applied.

Schema (implemented):

```
saved_tasks — UUID pk, owner_id FK, name, description, is_public, task_data JSONB, waypoint_file_id FK, total_distance, timestamps, UNIQUE(owner_id, name)
```

### 7.3 Waypoint API — Refactored ❌ TODO

`backend/routes/waypoints.py` does not yet exist. Existing waypoint routes are still in `app.py`. Move them into a blueprint and add save/load endpoints:

| Endpoint | Method | Auth | Status |
|----------|--------|------|--------|
| `/api/waypoints` | GET | No | Exists in app.py — move to blueprint |
| `/api/waypoints` | POST | No | Exists in app.py — move to blueprint |
| `/api/waypoints/<idx>` | PUT | No | Exists in app.py — move to blueprint |
| `/api/waypoints/<idx>` | DELETE | No | Exists in app.py — move to blueprint |
| `/api/waypoints/files` | GET | Login | ❌ To implement |
| `/api/waypoints/files` | POST | Login | ❌ To implement |
| `/api/waypoints/files/<file_id>` | GET | Login | ❌ To implement |
| `/api/waypoints/files/<file_id>` | PUT | Login | ❌ To implement |
| `/api/waypoints/files/<file_id>` | DELETE | Login | ❌ To implement |
| `/api/waypoints/files/<file_id>/visibility` | PATCH | Login+Premium | ❌ To implement |

Also needs: `backend/services/waypoint_service.py` (CRUD + tier limit checks) — ❌ TODO

### 7.4 Task API ❌ TODO

`backend/routes/tasks.py` does not yet exist. Existing task-export routes are still in `app.py`.

| Endpoint | Method | Auth | Status |
|----------|--------|------|--------|
| `/api/tasks` | GET | Login | ❌ To implement |
| `/api/tasks` | POST | Login | ❌ To implement |
| `/api/tasks/<task_id>` | GET | Login | ❌ To implement |
| `/api/tasks/<task_id>` | PUT | Login | ❌ To implement |
| `/api/tasks/<task_id>` | DELETE | Login | ❌ To implement |
| `/api/tasks/<task_id>/visibility` | PATCH | Login+Premium | ❌ To implement |
| `/api/task/export` | POST | No | Exists in app.py — move to blueprint |
| `/api/task/download` | POST | No | Exists in app.py — move to blueprint |
| `/api/task/qr` | POST | No | Exists in app.py — move to blueprint |

Also needs: `backend/services/task_service.py` (CRUD + tier limit checks) — ❌ TODO

---

## 8. Phase 5 — Public/Private Visibility & Browsing

### 8.1 Visibility Rules

| User Type | Save | Default Visibility | Can Set Private |
|-----------|------|--------------------|-----------------|
| Anonymous | ❌ (session only) | N/A | N/A |
| Free | ✅ | Public (forced) | ❌ |
| Premium | ✅ | Public | ✅ (can toggle) |
| Admin | ✅ | Public | ✅ |

When a free user saves a file/task, `is_public` is forced to `TRUE` at the service layer regardless of any client-sent value.

### 8.2 Browse API

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/browse/waypoints` | GET | No* | Search public waypoint files |
| `/api/browse/tasks` | GET | No* | Search public saved tasks |

*Anonymous users can browse public data. Logged-in users also see their own private items in results.

**Query parameters:**
- `q` — text search (matches name, description, waypoint names)
- `country` — filter by country code
- `owner` — filter by owner display name
- `mine` — `true` to show only current user's files (requires login)
- `page`, `per_page` — pagination (default 20 per page, max 100)
- `sort` — `newest`, `name`, `waypoint_count` / `distance`

**Response format (waypoint files):**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Polish Gliding Sites 2025",
      "description": "All glider-friendly airfields in Poland",
      "owner_name": "Jan Kowalski",
      "is_public": true,
      "is_mine": false,
      "waypoint_count": 47,
      "created_at": "2026-01-15T10:30:00Z"
    }
  ],
  "total": 128,
  "page": 1,
  "per_page": 20
}
```

### 8.3 Browse Popup — Waypoints

A new Shoelace `<sl-dialog>` added to `index.html`:

**`#browse-waypoints-dialog`:**
- Search input with debounced filtering
- Toggle: "Public" / "My Files" (if logged in)
- Scrollable results list — each row shows: name, owner, waypoint count, date
- Click row → loads that waypoint file into the session for editing
- "Load" button confirmation: "This will replace your current waypoints. Continue?"

Accessible from:
- **Map View** toolbar: new "Browse" button next to "Open File"
- **List View** toolbar: new "Browse" button

### 8.4 Browse Popup — Tasks

**`#browse-tasks-dialog`:**
- Same search/filter pattern as waypoint browser
- Results show: task name, owner, distance, turnpoint count, date
- Click row → loads task into the Task Planner
- "Load" button confirmation: "This will replace your current task. Continue?"

Accessible from:
- **Task Planner** sidebar: new "Browse Tasks" button next to "Load Task"

---

## 9. Phase 6 — AI Planner Gating

This phase only adds the **access gate** — the actual AI Planner implementation follows `AI_TASK_PLANNER.md`.

### 9.1 Frontend Gate

- The AI Planner tab (4th tab in the tab group) is visible to all users
- When a non-premium user clicks it, show an overlay: "AI Planner is a premium feature. Upgrade to access intelligent task planning with weather analysis."
- Premium users see the full AI Planner UI (to be built later)

### 9.2 Backend Gate

- All `/api/ai-planner/*` endpoints use the `@premium_required` decorator
- Returns `403 {"error": "Premium subscription required"}` for free users

### 9.3 Placeholder Tab

Add a 4th tab with placeholder content:
- Feature description with screenshots/mockups
- "Coming soon" messaging for premium users
- "Upgrade" CTA for free users

---

## 10. Database Schema

### Complete SQL — Migration 001: Core Tables

```sql
-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users table
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    display_name    VARCHAR(100) NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    tier            VARCHAR(20) NOT NULL DEFAULT 'free'
                    CHECK (tier IN ('free', 'premium', 'admin')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);

CREATE INDEX idx_users_email ON users (LOWER(email));
CREATE INDEX idx_users_tier ON users (tier);

-- Schema migration tracking
CREATE TABLE schema_migrations (
    id          SERIAL PRIMARY KEY,
    filename    VARCHAR(255) UNIQUE NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Migration 002: Waypoint Files

```sql
CREATE TABLE waypoint_files (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    is_public       BOOLEAN NOT NULL DEFAULT TRUE,
    waypoint_count  INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (owner_id, name)
);

CREATE INDEX idx_waypoint_files_owner ON waypoint_files (owner_id);
CREATE INDEX idx_waypoint_files_public ON waypoint_files (is_public)
    WHERE is_public = TRUE;

CREATE TABLE waypoint_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id         UUID NOT NULL REFERENCES waypoint_files(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    code            VARCHAR(50),
    country         VARCHAR(10),
    latitude        NUMERIC(10,7) NOT NULL,
    longitude       NUMERIC(10,7) NOT NULL,
    elevation       INTEGER,
    style           INTEGER NOT NULL DEFAULT 1,
    runway_direction INTEGER,
    runway_length   INTEGER,
    runway_width    INTEGER,
    frequency       VARCHAR(20),
    description     TEXT,
    sort_order      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_waypoint_entries_file ON waypoint_entries (file_id);
```

### Migration 003: Saved Tasks

```sql
CREATE TABLE saved_tasks (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name              VARCHAR(255) NOT NULL,
    description       TEXT,
    is_public         BOOLEAN NOT NULL DEFAULT TRUE,
    task_data         JSONB NOT NULL,
    waypoint_file_id  UUID REFERENCES waypoint_files(id) ON DELETE SET NULL,
    total_distance    NUMERIC(8,2),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (owner_id, name)
);

CREATE INDEX idx_saved_tasks_owner ON saved_tasks (owner_id);
CREATE INDEX idx_saved_tasks_public ON saved_tasks (is_public)
    WHERE is_public = TRUE;
CREATE INDEX idx_saved_tasks_distance ON saved_tasks (total_distance);
```

---

## 11. API Endpoints

### Complete endpoint reference

#### Auth (`backend/routes/auth.py`)

| Method | Path | Auth | Request Body | Response |
|--------|------|------|-------------|----------|
| POST | `/auth/register` | No | `{email, display_name, password}` | `{user}` 201 |
| POST | `/auth/login` | No | `{email, password}` | `{user}` 200 |
| POST | `/auth/logout` | Yes | — | 204 |
| GET | `/auth/me` | Yes | — | `{user, tier, limits}` 200 |
| POST | `/auth/change-password` | Yes | `{old_password, new_password}` | 204 |
| POST | `/auth/admin/set-tier` | Admin | `{email, tier}` | `{user}` 200 |

#### Waypoint Files (`backend/routes/waypoints.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/waypoints` | No | Session waypoints (existing) |
| POST | `/api/waypoints` | No | Add to session (existing) |
| PUT | `/api/waypoints/<idx>` | No | Update in session (existing) |
| DELETE | `/api/waypoints/<idx>` | No | Delete from session (existing) |
| GET | `/api/waypoints/files` | Login | List my saved files |
| POST | `/api/waypoints/files` | Login | Save session → new file |
| GET | `/api/waypoints/files/<id>` | Login | Load file → session |
| PUT | `/api/waypoints/files/<id>` | Login | Overwrite file from session |
| DELETE | `/api/waypoints/files/<id>` | Login | Delete saved file |
| PATCH | `/api/waypoints/files/<id>/visibility` | Premium | `{is_public: bool}` |

#### Tasks (`backend/routes/tasks.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/tasks` | Login | List my saved tasks |
| POST | `/api/tasks` | Login | Save task |
| GET | `/api/tasks/<id>` | Login | Load task |
| PUT | `/api/tasks/<id>` | Login | Update task |
| DELETE | `/api/tasks/<id>` | Login | Delete task |
| PATCH | `/api/tasks/<id>/visibility` | Premium | `{is_public: bool}` |
| POST | `/api/task/export` | No | Export (existing) |
| POST | `/api/task/download` | No | Download (existing) |
| POST | `/api/task/qr` | No | QR (existing) |

#### Browse (`backend/routes/browse.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/browse/waypoints` | No | Search public waypoint files |
| GET | `/api/browse/tasks` | No | Search public tasks |

---

## 12. Frontend Changes

### 12.1 `templates/index.html`

| Change | Location | Details |
|--------|----------|---------|
| Auth header controls | `<header>` bar, right side | Login/register buttons (logged out) or user badge + logout (logged in) |
| Login dialog | New `<sl-dialog id="login-dialog">` | Email + password fields, submit, register link |
| Register dialog | New `<sl-dialog id="register-dialog">` | Email + display name + password + confirm, submit |
| Save/Load buttons | Map View toolbar | "Save to Account" / "Load from Account" (visible when logged in) |
| Save/Load buttons | Task Planner sidebar | "Save Task" / "Load Task" buttons (visible when logged in) |
| Browse Waypoints dialog | New `<sl-dialog id="browse-waypoints-dialog">` | Search, filter, paginated results, load action |
| Browse Tasks dialog | New `<sl-dialog id="browse-tasks-dialog">` | Search, filter, paginated results, load action |
| Browse buttons | Map View toolbar + Task Planner sidebar | "Browse" buttons to open dialogs |
| AI Planner tab | New 4th `<sl-tab panel="ai-planner">` | Placeholder with upgrade CTA |
| Tier badge | Header, next to user name | `<sl-badge variant="primary">FREE</sl-badge>` or `<sl-badge variant="success">PREMIUM</sl-badge>` |
| Visibility toggle | Save dialog | `<sl-switch>` for public/private (premium only, disabled for free) |

### 12.2 `static/js/auth.js` (new file)

```
class AuthManager {
    constructor(app)
    
    // State
    currentUser = null
    isAuthenticated = false
    
    // API calls
    async login(email, password)
    async register(email, displayName, password)
    async logout()
    async fetchCurrentUser()
    
    // UI
    updateHeaderUI()
    showLoginDialog()
    showRegisterDialog()
    handleSessionMigration()    // prompt to save anonymous data
    
    // Tier helpers
    isPremium()
    canSetPrivate()
    getRemainingQuota(type)     // 'files' or 'tasks'
}
```

### 12.3 `static/js/browse-dialog.js` (new file)

```
class BrowseDialog {
    constructor(type, app)      // type = 'waypoints' | 'tasks'
    
    // API
    async search(query, filters, page)
    
    // UI
    open()
    close()
    renderResults(items)
    renderPagination(total, page, perPage)
    
    // Actions
    async loadItem(itemId)      // load selected file/task into session
}
```

### 12.4 `static/js/app.js` (modify)

- Initialize `AuthManager` in `initializeApp()`
- Conditionally show "Save to Account" / "Browse" buttons based on auth state
- Add event listeners for new buttons
- Pass auth state to `TaskPlanner` constructor

### 12.5 `static/js/task-planner.js` (modify)

- Add "Save Task" button handler → calls task service
- Add "Browse Tasks" button handler → opens browse dialog
- Replace `localStorage` persistence with DB persistence when logged in (keep localStorage as fallback for anonymous users)
- Add AI Planner tab visibility logic based on tier

---

## 13. File Inventory

### Backend Files

| File | Status | Notes |
|------|--------|-------|
| `backend/__init__.py` | ✅ EXISTS | Package init |
| `backend/config.py` | ✅ EXISTS | Loads `.ai.env` then `.env`; exports DATABASE_URL, SECRET_KEY, TIER_LIMITS, all AI/weather keys |
| `backend/db.py` | ✅ EXISTS | SQLAlchemy engine, scoped session, `init_db(app)`, `get_db()` |
| `backend/migrate.py` | ✅ EXISTS | SQL migration runner |
| `backend/migrations/001_initial_schema.sql` | ✅ EXISTS | pgcrypto, users, schema_migrations |
| `backend/migrations/002_waypoint_files.sql` | ✅ EXISTS | waypoint_files, waypoint_entries with indexes |
| `backend/migrations/003_saved_tasks.sql` | ✅ EXISTS | saved_tasks table |
| `backend/models/__init__.py` | ✅ EXISTS | |
| `backend/models/base.py` | ✅ EXISTS | Declarative base, TimestampMixin |
| `backend/models/user.py` | ✅ EXISTS | User model with Flask-Login interface |
| `backend/models/waypoint_file.py` | ✅ EXISTS | WaypointFile, WaypointEntry ORM models |
| `backend/models/task.py` | ✅ EXISTS | SavedTask ORM model |
| `backend/models/legacy.py` | ✅ EXISTS | Waypoint dataclass for CUP format |
| `backend/routes/__init__.py` | ✅ EXISTS | |
| `backend/routes/auth.py` | ✅ EXISTS | Auth blueprint — register, login, logout, me, change-password, admin/set-tier |
| `backend/routes/waypoints.py` | ❌ TODO | Waypoints blueprint (refactor from app.py + add save/load) |
| `backend/routes/tasks.py` | ❌ TODO | Tasks blueprint |
| `backend/routes/browse.py` | ❌ TODO | Browse/search blueprint |
| `backend/services/__init__.py` | ✅ EXISTS | |
| `backend/services/auth_service.py` | ✅ EXISTS | register_user, authenticate, change_password, AuthError |
| `backend/services/user_service.py` | ✅ EXISTS | can_save_file, can_save_task, can_set_private, can_access_ai_planner, set_user_tier |
| `backend/services/waypoint_service.py` | ❌ TODO | Waypoint file CRUD with tier limit checks |
| `backend/services/task_service.py` | ❌ TODO | Task CRUD with tier limit checks |
| `backend/services/browse_service.py` | ❌ TODO | Search/filter logic with pagination |
| `backend/utils/__init__.py` | ✅ EXISTS | |
| `backend/utils/auth_decorators.py` | ✅ EXISTS | @login_required, @premium_required, @admin_required |

### Frontend Files

| File | Status | Notes |
|------|--------|-------|
| `static/js/auth.js` | ❌ TODO | AuthManager class |
| `static/js/browse-dialog.js` | ❌ TODO | BrowseDialog class |
| `static/js/app.js` | Modify | Init AuthManager, wire new buttons |
| `static/js/task-planner.js` | Modify | Save/load from DB, browse tasks button |
| `templates/index.html` | Modify | Auth header, login/register dialogs, browse dialogs, AI tab, save/load buttons |

### Config / Infra Files

| File | Status | Notes |
|------|--------|-------|
| `app.py` | ✅ EXISTS (thin) | Registers auth_bp, calls init_db, configures Flask-Login |
| `requirements.txt` | ✅ UP TO DATE | All Phase 1-3 deps already installed |
| `docker-compose.yaml` | Modify | Add `env_file: .env` |
| `.env` / `.ai.env` | ✅ EXISTS | `.ai.env` is the primary secrets file; do not commit either |
| `.env.example` | Update | Add DATABASE_URL, AI keys (redacted), tier config |

---

## 14. Dependencies

### New Python Packages

| Package | Version | Purpose |
|---------|---------|---------|
| `SQLAlchemy` | ≥2.0 | ORM and database toolkit |
| `psycopg2-binary` | ≥2.9 | PostgreSQL driver |
| `python-dotenv` | ≥1.0 | Load `.env` file |
| `Flask-Login` | ≥0.6 | User session management |

### Already Available (no changes)

| Package | Used For |
|---------|----------|
| `Werkzeug` | Password hashing (`generate_password_hash` / `check_password_hash`) |
| `Flask` | Web framework, sessions, blueprints |
| `flask-cors` | CORS headers |

### Frontend (no new dependencies)

All new UI uses existing Shoelace 2 components (already loaded via CDN in `index.html`). No npm/build step changes needed.

---

## 15. Configuration Changes

### Updated `.env.example`

```bash
# Flask
SECRET_KEY=your_very_secure_random_secret_key_here
BASE_URL=

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/gliding_forecast

# AI Services (premium feature — leave empty to disable)
GEMINI_API_KEY=
GROQ_API_KEY=
DEEPSEEK_API_KEY=

# Weather APIs (AI Planner — leave empty to disable)
IMGW_API_BASE_URL=https://danepubliczne.imgw.pl/api/data
WINDY_API_KEY=
OPENWEATHERMAP_API_KEY=
```

### Updated `backend/config.py`

```python
import os
from dotenv import load_dotenv

load_dotenv()

# Flask
SECRET_KEY = os.environ.get("SECRET_KEY", "CHANGE-ME")
BASE_URL = os.environ.get("BASE_URL", "")

# Database
DATABASE_URL = os.environ["DATABASE_URL"]

# Tier limits
TIER_LIMITS = {
    "free": {"max_waypoint_files": 5, "max_saved_tasks": 10, "can_set_private": False},
    "premium": {"max_waypoint_files": 50, "max_saved_tasks": 100, "can_set_private": True},
    "admin": {"max_waypoint_files": None, "max_saved_tasks": None, "can_set_private": True},
}

# XCSoar waypoint styles (existing)
STYLE_OPTIONS = (...)  # unchanged
```

---

## 16. Migration Strategy

### From Anonymous Sessions to User-Owned Data

The existing anonymous session system (`data/session_*.json`) is preserved for non-logged-in users. No data migration is needed for existing sessions — they continue to work as-is.

When a user **first logs in**:
1. Check if the current anonymous session has waypoints
2. If yes, offer to save them as the user's first waypoint file
3. The anonymous session file remains on disk (for other anonymous visitors on the same browser session)

### Database Migrations

Migrations are applied manually or at app startup:

```bash
python -m backend.migrate          # runs all pending migrations
python -m backend.migrate --dry    # preview only
```

Migration files are numbered SQL scripts in `backend/migrations/`. The `schema_migrations` table tracks which have been applied.

### Phased Rollout

| Phase | What ships | Backward compatible? |
|-------|-----------|---------------------|
| Phase 1 | DB connection, migrations tables | ✅ Existing app works without DB if `DATABASE_URL` is not set |
| Phase 2 | Auth endpoints, login UI | ✅ Anonymous mode still works |
| Phase 3 | Tier model on user table | ✅ Default tier = free |
| Phase 4 | Save/load endpoints, UI buttons | ✅ Session fallback for anonymous |
| Phase 5 | Browse dialogs, visibility toggles | ✅ Public data visible to all |
| Phase 6 | AI tab placeholder + gate | ✅ Non-premium sees upgrade CTA |

---

## 17. Security Considerations

### Authentication

- Passwords hashed with `werkzeug.security.generate_password_hash` (PBKDF2 + SHA-256, 600k iterations by default)
- Session cookies: `HttpOnly`, `SameSite=Lax`, `Secure` in production
- Rate limit login attempts: max 5 failed attempts per email per 15 minutes (use in-memory counter or DB-backed)
- CSRF protection on all state-changing endpoints (Flask-WTF or manual token, since existing app uses `fetch()` with JSON bodies, a custom header check like `X-Requested-With` is sufficient)

### Authorization

- All ownership checks done server-side in service layer
- Users can only modify/delete their own files/tasks
- `is_public = FALSE` items are invisible to other users (filtered in SQL queries, not just hidden in UI)
- Admin endpoints restricted to `tier = 'admin'`

### Data Validation

- All user input validated and sanitized at the service layer
- SQL injection prevented via SQLAlchemy ORM (parameterized queries)
- XSS prevented via Jinja2 auto-escaping (already in place) and `escapeHtml()` in JS (already exists)
- File uploads: existing 16MB limit and extension validation remain

### Environment

- `.env` file must never be committed (add to `.gitignore`)
- `SECRET_KEY` must be a strong random value in production (warn on startup if default)
- Database password in `DATABASE_URL` — connection string in env var, never in code

---

## 18. Implementation Order — Step by Step

Each step is independently deployable and backward-compatible with the previous state.

### Step 1: Database Foundation
1. Add `SQLAlchemy`, `psycopg2-binary`, `python-dotenv`, `Flask-Login` to `requirements.txt`
2. Create `.env` file (merge `.env.example` + relevant `.ai.env` values)
3. Update `backend/config.py` — load dotenv, export `DATABASE_URL`, `SECRET_KEY`, `TIER_LIMITS`
4. Create `backend/db.py` — engine, scoped session, `init_db(app)`, `get_db()`
5. Create `backend/models/base.py` — declarative base, `TimestampMixin`
6. Create `backend/migrations/` and migration runner
7. Update `app.py` — load dotenv, call `init_db(app)`, keep existing routes working
8. **Test**: app starts, connects to DB, migration table created

### Step 2: User Model & Auth
1. Create `backend/models/user.py` — `User` model
2. Create migration `001_initial_schema.sql`
3. Run migration
4. Create `backend/services/auth_service.py` — register, authenticate, change_password
5. Create `backend/utils/auth_decorators.py` — `@login_required`, `@premium_required`
6. Create `backend/routes/auth.py` — auth blueprint with all endpoints
7. Register auth blueprint in `app.py`
8. Set up Flask-Login (user loader, login manager)
9. **Test**: register user via API, login, `/auth/me` returns user

### Step 3: Frontend Auth UI
1. Create `static/js/auth.js` — `AuthManager` class
2. Add auth dialogs to `templates/index.html` (login, register)
3. Add auth header controls (login button / user badge)
4. Wire up in `app.js` — initialize `AuthManager`, check session on load
5. Implement anonymous→authenticated session migration prompt
6. **Test**: register in browser, login, see user badge, logout

### Step 4: Waypoint File Storage
1. Create `backend/models/waypoint_file.py` — `WaypointFile`, `WaypointEntry`
2. Create migration `002_waypoint_files.sql`
3. Run migration
4. Create `backend/services/waypoint_service.py` — CRUD with tier limit checks
5. Create `backend/routes/waypoints.py` — waypoints blueprint
6. Move existing waypoint routes from `app.py` to new blueprint
7. Add save/load file endpoints
8. Add "Save" / "My Files" buttons to `index.html` (Map View + List View toolbars)
9. Wire button handlers in `app.js`
10. **Test**: save session waypoints to DB, load them back, verify tier limits

### Step 5: Task Storage
1. Create `backend/models/task.py` — `SavedTask`
2. Create migration `003_saved_tasks.sql`
3. Run migration
4. Create `backend/services/task_service.py` — CRUD with tier limit checks
5. Create `backend/routes/tasks.py` — tasks blueprint
6. Move existing task export routes from `app.py` to new blueprint
7. Add save/load task endpoints
8. Add "Save Task" / "My Tasks" buttons to Task Planner sidebar in `index.html`
9. Wire button handlers in `task-planner.js`
10. **Test**: save task to DB, load it back, export still works

### Step 6: Browse Dialogs
1. Create `backend/services/browse_service.py` — search with pagination, visibility filtering
2. Create `backend/routes/browse.py` — browse blueprint
3. Create `static/js/browse-dialog.js` — `BrowseDialog` class
4. Add browse dialogs to `index.html` (waypoints + tasks)
5. Add "Browse" buttons to Map View toolbar and Task Planner sidebar
6. Wire in `app.js` and `task-planner.js`
7. **Test**: browse public files/tasks, search, paginate, load into session

### Step 7: Visibility Controls
1. Add public/private toggle to save dialogs (disabled for free tier)
2. Add visibility PATCH endpoints to waypoints and tasks blueprints
3. Enforce `is_public = TRUE` for free tier in service layer
4. Filter private items from browse results (only visible to owner)
5. Add visibility badge (`<sl-badge>`) to "My Files" / "My Tasks" lists
6. **Test**: premium user sets file to private, verify it's invisible to others, free user cannot set private

### Step 8: AI Planner Tab Placeholder
1. Add 4th tab "AI Planner" to `templates/index.html`
2. Add placeholder content with feature description
3. Add tier gate — overlay for non-premium users, placeholder for premium
4. Add `@premium_required` to stub `/api/ai-planner/status` endpoint
5. **Test**: free user sees upgrade CTA, premium user sees placeholder

### Step 9: Cleanup & Hardening
1. Refactor remaining inline routes from `app.py` into blueprints
2. Add login rate limiting
3. Add request validation (email format, password strength)
4. Update `docker-compose.yaml` with `env_file: .env`
5. Update `.env.example` with all new variables
6. Update deployment docs
7. **Test**: full end-to-end flow — register, login, upload CUP, save to DB, browse, export, share

---

> **After all steps above are complete**, DO NOT proceed to implement the AI Task Planner per [`AI_TASK_PLANNER.md`](AI_TASK_PLANNER.md). Wait for user instruction