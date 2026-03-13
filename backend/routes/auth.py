"""Authentication blueprint — /auth/*"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_user, logout_user

from backend.db import get_db
from backend.models.user import User
from backend.services import auth_service, user_service
from backend.services.auth_service import AuthError, EmailNotVerifiedError
from backend.services.email_service import send_verification_code
from backend.utils.auth_decorators import admin_required, login_required

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '')
    display_name = data.get('display_name', '')
    password = data.get('password', '')

    if not email or not display_name or not password:
        return jsonify({'error': 'email, display_name, and password are required.'}), 400

    db = get_db()
    try:
        user = auth_service.register_user(db, email, display_name, password)
        code = auth_service.generate_verification_code(db, user)
        db.commit()
        send_verification_code(user.email, code, user.display_name)
        return jsonify({'requires_verification': True, 'email': user.email}), 201
    except AuthError as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 409
    except Exception:
        db.rollback()
        logger.exception('Unexpected error during registration')
        return jsonify({'error': 'Registration failed.'}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '')
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'email and password are required.'}), 400

    db = get_db()
    try:
        user = auth_service.authenticate(db, email, password)
        if user is None:
            return jsonify({'error': 'Invalid email or password.'}), 401
        db.commit()
        login_user(user, remember=True)
        limits = user_service.get_tier_limits(user.tier)
        return jsonify({'user': user.to_dict(), 'limits': limits})
    except EmailNotVerifiedError as exc:
        # Correct credentials but unverified — send a fresh code and prompt
        unverified = db.query(User).filter(User.email == exc.email).first()
        if unverified:
            code = auth_service.generate_verification_code(db, unverified)
            db.commit()
            send_verification_code(exc.email, code, unverified.display_name)
        return jsonify({'requires_verification': True, 'email': exc.email})
    except Exception:
        db.rollback()
        logger.exception('Unexpected error during login')
        return jsonify({'error': 'Login failed.'}), 500


@auth_bp.route('/verify-email', methods=['POST'])
def verify_email():
    """Verify a user's email with the OTP code. Logs the user in on success."""
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()
    code = data.get('code', '').strip()

    if not email or not code:
        return jsonify({'error': 'email and code are required.'}), 400

    db = get_db()
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active:
        return jsonify({'error': 'code_invalid'}), 400

    try:
        auth_service.verify_email_code(db, user, code)
        db.commit()
        login_user(user, remember=True)
        limits = user_service.get_tier_limits(user.tier)
        return jsonify({'user': user.to_dict(), 'limits': limits})
    except AuthError as exc:
        db.commit()  # persist attempt count increment
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.rollback()
        logger.exception('Unexpected error during email verification')
        return jsonify({'error': 'Verification failed.'}), 500


@auth_bp.route('/resend-code', methods=['POST'])
def resend_code():
    """Resend a verification code. Always returns 200 to avoid leaking account existence."""
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()

    if email:
        db = get_db()
        user = db.query(User).filter(User.email == email).first()
        if user and user.is_active and not user.email_verified:
            code = auth_service.generate_verification_code(db, user)
            db.commit()
            send_verification_code(user.email, code, user.display_name)

    return jsonify({}), 200


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return '', 204


@auth_bp.route('/me', methods=['GET'])
@login_required
def me():
    limits = user_service.get_tier_limits(current_user.tier)
    return jsonify({'user': current_user.to_dict(), 'limits': limits})


@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json(silent=True) or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not old_password or not new_password:
        return jsonify({'error': 'old_password and new_password are required.'}), 400

    db = get_db()
    try:
        auth_service.change_password(db, current_user, old_password, new_password)
        db.commit()
        return '', 204
    except AuthError as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.rollback()
        logger.exception('Unexpected error during password change')
        return jsonify({'error': 'Password change failed.'}), 500


@auth_bp.route('/me/language', methods=['PATCH'])
@login_required
def update_language():
    """Update (or clear) the authenticated user's preferred UI language."""
    data = request.get_json(silent=True) or {}
    lang_code = (data.get('lang_code') or '').strip()

    if lang_code:
        db = get_db()
        from backend.services.i18n_service import get_active_languages
        valid_codes = {l['code'] for l in get_active_languages(db)}
        if lang_code not in valid_codes:
            return jsonify({'error': 'Unsupported language code.'}), 400
    else:
        lang_code = None  # empty string → clear the preference
        db = get_db()

    try:
        user_service.update_preferred_language(db, current_user, lang_code)
        db.commit()
        return jsonify({'preferred_language': lang_code})
    except Exception:
        db.rollback()
        logger.exception('Unexpected error updating language preference')
        return jsonify({'error': 'Update failed.'}), 500


# ── API key management (BYOK) ────────────────────────────────────────────────

import re as _re

_OPENROUTER_KEY_RE = _re.compile(r'^sk-or-v1-[a-f0-9]{64}$')


@auth_bp.route('/me/api-key', methods=['GET'])
@login_required
def get_api_key():
    """Return masked status of the user's OpenRouter API key."""
    has_key = bool(current_user.openrouter_key_enc)
    last4 = ''
    if has_key:
        try:
            from backend.utils.crypto import decrypt_value
            plain = decrypt_value(current_user.openrouter_key_enc)
            last4 = plain[-4:]
        except Exception:
            pass
    return jsonify({'has_key': has_key, 'last4': last4})


@auth_bp.route('/me/api-key', methods=['PUT'])
@login_required
def set_api_key():
    """Store the user's OpenRouter API key (encrypted at rest)."""
    data = request.get_json(silent=True) or {}
    key = (data.get('api_key') or '').strip()

    if not key:
        return jsonify({'error': 'api_key is required.'}), 400
    if not _OPENROUTER_KEY_RE.match(key):
        return jsonify({'error': 'Invalid OpenRouter API key format. It should start with sk-or-v1- followed by 64 hex characters.'}), 400

    from backend.utils.crypto import encrypt_value
    db = get_db()
    try:
        current_user.openrouter_key_enc = encrypt_value(key)
        db.flush()
        db.commit()
        return jsonify({'success': True, 'has_key': True, 'last4': key[-4:]})
    except Exception:
        db.rollback()
        logger.exception('Failed to save API key')
        return jsonify({'error': 'Failed to save API key.'}), 500


@auth_bp.route('/me/api-key', methods=['DELETE'])
@login_required
def delete_api_key():
    """Remove the user's stored OpenRouter API key."""
    db = get_db()
    try:
        current_user.openrouter_key_enc = None
        db.flush()
        db.commit()
        return jsonify({'success': True, 'has_key': False})
    except Exception:
        db.rollback()
        logger.exception('Failed to remove API key')
        return jsonify({'error': 'Failed to remove API key.'}), 500


@auth_bp.route('/admin/set-tier', methods=['POST'])
@admin_required
def set_tier():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '')
    tier = data.get('tier', '')

    if not email or not tier:
        return jsonify({'error': 'email and tier are required.'}), 400

    db = get_db()
    try:
        user = user_service.set_user_tier(db, email, tier)
        if user is None:
            return jsonify({'error': 'User not found.'}), 404
        db.commit()
        return jsonify({'user': user.to_dict()})
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.rollback()
        logger.exception('Unexpected error during set-tier')
        return jsonify({'error': 'Operation failed.'}), 500
