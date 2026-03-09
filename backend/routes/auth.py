"""Authentication blueprint — /auth/*"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_user, logout_user

from backend.db import get_db
from backend.services import auth_service, user_service
from backend.services.auth_service import AuthError
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
        db.commit()
        login_user(user, remember=True)
        limits = user_service.get_tier_limits(user.tier)
        return jsonify({'user': user.to_dict(), 'limits': limits}), 201
    except AuthError as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 409
    except Exception as exc:
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
    except Exception as exc:
        db.rollback()
        logger.exception('Unexpected error during login')
        return jsonify({'error': 'Login failed.'}), 500


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
