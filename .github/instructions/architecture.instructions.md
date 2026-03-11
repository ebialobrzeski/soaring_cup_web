---
description: "Use when implementing any new feature, endpoint, module, or data layer in soaring_cup_web. Enforces modular architecture, separation of concerns, and Python/Flask best practices. Apply when writing backend routes, services, models, utilities, or AI integration code."
applyTo: "**/*.py"
---

# Architecture & Best Practices

## Core Principle: No Monoliths

Every implementation must follow single-responsibility. If a function or module does more than one logical thing, split it.

- **Routes** only handle HTTP concerns: parse input, call a service, return a response
- **Services** contain business logic and orchestration — never import Flask directly
- **Models** define data structures and DB schema only — no business logic
- **Utilities** are pure functions with no side effects and no external dependencies

## Module Layout

Follow the existing `backend/` conventions and expand them:

```
backend/
  config.py          # env vars, constants, DB connection strings
  models.py          # SQLAlchemy models or dataclasses
  file_io.py         # file read/write helpers
  routes/            # one file per feature area (e.g. forecast.py, polars.py)
  services/          # one file per domain (e.g. weather_service.py, ai_service.py)
  utils/             # stateless helpers (unit-testable)
```

Never put business logic directly in `app.py`. Route handlers in `app.py` must stay thin — register blueprints, not inline logic.

## Python Best Practices

- Use **type hints** on all function signatures
- Use **dataclasses or Pydantic models** for structured data passed between layers
- Use **environment variables** via `backend/config.py` — never hardcode credentials or URLs
- **When adding a new environment variable**, always do all three:
  1. Add it to `backend/config.py` with `os.environ.get(...)`
  2. Add it (with a placeholder value) to `.env.example`
  3. Add it to the `glideplan` service `environment:` block in `docker-compose.yaml` using `${VAR_NAME:-default}` syntax — otherwise it will be silently missing in production
- Prefer **explicit imports** over wildcard (`from module import *`)
- Keep functions short: if a function exceeds ~30 lines, it likely has more than one responsibility

## AI / External API Integration

- Wrap each AI provider (Gemini, Groq, DeepSeek) in its own service class or module
- All external HTTP calls go through a dedicated service — routes never call `requests` or `httpx` directly
- Handle API errors at the service layer; routes receive clean results or typed exceptions

## Database

- DB access lives in service files or a dedicated `db/` layer — never in routes
- Use parameterized queries or ORM methods — never string-interpolated SQL
- When adding and/or removing functionallity always remember to update application translation keys and translations in `backend/models/i18n.py` and `backend/translations/` respectively

## Internationalisation (i18n)

**Every new UI element must have a translation.** This is non-negotiable — never add visible text to HTML or JS without covering all four languages (en, pl, de, cs).

Checklist whenever a new label, button, checkbox, tooltip, or status message is added:

1. Add a `data-i18n="category.key"` attribute to the HTML element (or use `window.i18n.t('category.key', 'Fallback')` in JS).
2. Create a new SQL migration (`backend/migrations/NNN_<feature>_i18n.sql`) that:
   - Inserts the key into `translation_keys` with `default_value` = English text.
   - Inserts rows into `translations` for `pl`, `de`, and `cs` using the `key_id` + `language_code` JOIN pattern (see existing migrations for the exact syntax).
3. Follow the naming convention `category.key` — use an existing category (`wpgen`, `btn`, `confirm`, `task`, `map`, …) or introduce a new one consistently.

## Flask Blueprints

- Every feature area must be a **Blueprint** registered in `app.py`
- Blueprint files live in `backend/routes/`

## What NOT to Do

- Do not add all new logic to `app.py`
- Do not mix DB queries, AI calls, and HTTP response building in the same function
- Do not duplicate config values across files — add them to `backend/config.py` once
