"""i18n service — loads languages and translations from the database.

Translations are cached in-process after the first DB fetch per language.
Use bust_cache() after admin edits to force a reload.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.i18n import Language, Translation, TranslationKey

logger = logging.getLogger(__name__)

_FALLBACK_LANG = 'en'

# In-process cache: { lang_code: { key: value } }
_cache: dict[str, dict[str, str]] = {}
_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_active_languages(db: Session) -> list[dict]:
    """Return list of active languages ordered by sort_order."""
    rows = (
        db.query(Language)
        .filter(Language.is_active.is_(True))
        .order_by(Language.sort_order)
        .all()
    )
    return [lang.to_dict() for lang in rows]


def get_translations(db: Session, lang_code: str) -> dict[str, str]:
    """Return a flat key→value dict for *lang_code*.

    Falls back to the key's ``default_value`` (English) for any key that has
    no translation record for the requested language.  Results are cached
    in-process.
    """
    with _cache_lock:
        if lang_code in _cache:
            return _cache[lang_code]

    result = _build_translations(db, lang_code)

    with _cache_lock:
        _cache[lang_code] = result

    return result


def bust_cache(lang_code: Optional[str] = None) -> None:
    """Invalidate the in-process translation cache.

    If *lang_code* is given, only that language is evicted; otherwise the
    entire cache is cleared.
    """
    with _cache_lock:
        if lang_code:
            _cache.pop(lang_code, None)
        else:
            _cache.clear()
    logger.info('Translation cache busted: %s', lang_code or 'all')


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_translations(db: Session, lang_code: str) -> dict[str, str]:
    """Query DB and assemble key→value dict, falling back to default_value."""
    # Load all keys with their English defaults
    keys: dict[int, tuple[str, str]] = {}  # id → (key, default_value)
    for tk in db.query(TranslationKey).all():
        keys[tk.id] = (tk.key, tk.default_value)

    # Load translations for the requested language
    overrides: dict[int, str] = {}
    if lang_code != _FALLBACK_LANG:
        rows = (
            db.query(Translation)
            .filter(Translation.language_code == lang_code)
            .all()
        )
        for t in rows:
            overrides[t.key_id] = t.value

    result: dict[str, str] = {}
    for key_id, (key_str, default) in keys.items():
        result[key_str] = overrides.get(key_id, default)

    logger.debug('Built %d translations for lang=%s', len(result), lang_code)
    return result
