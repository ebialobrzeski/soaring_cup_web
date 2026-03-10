"""
Email delivery via Resend (https://resend.com).

All transactional emails go through this module.  Routes and services
should call the public helpers below — never import `resend` directly.
"""
from __future__ import annotations

import logging
from typing import Optional

import resend

from backend.config import RESEND_API_KEY, RESEND_FROM_ADDRESS

logger = logging.getLogger(__name__)

resend.api_key = RESEND_API_KEY


def _send(*, to: str, subject: str, html: str) -> Optional[str]:
    """
    Send a single transactional email.

    Returns the Resend email id on success, or None if sending failed
    (e.g. missing API key in dev/test environments).
    """
    if not RESEND_API_KEY:
        logger.warning('RESEND_API_KEY is not set — email to %s was not sent.', to)
        return None

    try:
        params: resend.Emails.SendParams = {
            'from': RESEND_FROM_ADDRESS,
            'to': [to],
            'subject': subject,
            'html': html,
        }
        response = resend.Emails.send(params)
        logger.info('Email sent to %s (id=%s)', to, response.get('id'))
        return response.get('id')
    except Exception:
        logger.exception('Failed to send email to %s', to)
        return None


def send_verification_code(to: str, code: str, display_name: str = '') -> Optional[str]:
    """Send a 6-digit email verification code."""
    greeting = f'Hi {display_name},' if display_name else 'Hi,'
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;">
      <h2 style="color:#1a73e8;">Verify your GlidePlan account</h2>
      <p>{greeting}</p>
      <p>Use the code below to verify your email address.
         It expires in <strong>10 minutes</strong>.</p>
      <div style="font-size:2.5rem;font-weight:bold;letter-spacing:.3rem;
                  text-align:center;padding:24px;background:#f1f3f4;
                  border-radius:8px;margin:24px 0;">
        {code}
      </div>
      <p style="color:#666;font-size:.875rem;">
        If you did not create a GlidePlan account, you can safely ignore this email.
      </p>
    </div>
    """
    return _send(to=to, subject='Your GlidePlan verification code', html=html)


def send_welcome(to: str, display_name: str = '') -> Optional[str]:
    """Send a welcome email after successful verification."""
    greeting = f'Hi {display_name},' if display_name else 'Hi,'
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;">
      <h2 style="color:#1a73e8;">Welcome to GlidePlan!</h2>
      <p>{greeting}</p>
      <p>Your account is now verified. Happy soaring!</p>
    </div>
    """
    return _send(to=to, subject='Welcome to GlidePlan', html=html)
