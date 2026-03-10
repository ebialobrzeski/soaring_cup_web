"""i18n routes — publicly accessible language and translation endpoints.

All routes are intentionally unauthenticated: any visitor needs translations
to render the UI before they ever log in.
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from backend.db import get_db
from backend.services import i18n_service

logger = logging.getLogger(__name__)

i18n_bp = Blueprint('i18n', __name__, url_prefix='/api/i18n')

_SUPPORTED_LANG_CODES: set[str] = {'en', 'pl', 'de', 'cs'}


@i18n_bp.route('/languages', methods=['GET'])
def list_languages():
    """Return all active languages.  No authentication required."""
    db = get_db()
    if db is None:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 503
    languages = i18n_service.get_active_languages(db)
    return jsonify({'success': True, 'languages': languages})


@i18n_bp.route('/<string:lang_code>', methods=['GET'])
def get_translations(lang_code: str):
    """Return flat key→value translation dict for *lang_code*.

    Falls back to English default for any missing key.
    No authentication required — the frontend needs this before login.
    """
    # Validate lang code to prevent abuse / unexpected DB queries
    if lang_code not in _SUPPORTED_LANG_CODES:
        return jsonify({'success': False, 'error': f'Unsupported language: {lang_code}'}), 400

    db = get_db()
    if db is None:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 503

    translations = i18n_service.get_translations(db, lang_code)
    return jsonify({'success': True, 'lang': lang_code, 'translations': translations})
