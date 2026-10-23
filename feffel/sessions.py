"""Server-side sessions. The cookie holds a random token; only its hash is stored."""

import secrets
import time

from flask import current_app, request

from . import constants
from .util import sha256


def load_session(db):
    """The session row (with the user's name and email) for the request cookie, or ``None``."""
    token = request.cookies.get(constants.SESSION_COOKIE)
    if not token:
        return None
    return db.execute(
        'SELECT s.*,u.name,u.email FROM sessions s JOIN users u ON u.id=s.user WHERE token=? AND expires>?',
        (sha256(token), time.time()),
    ).fetchone()


def start_session(db, user_id):
    """Create a session for ``user_id`` and return the response that sets its cookie."""
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
    db.execute(
        'INSERT INTO sessions VALUES(?,?,?,?)',
        (sha256(token), user_id, csrf, time.time() + constants.SESSION_SECONDS),
    )
    cookie = (
        f'{constants.SESSION_COOKIE}={token}; HttpOnly; SameSite=Lax; Path=/; '
        f'Max-Age={constants.SESSION_SECONDS}'
    ) + ('; Secure' if current_app.config['SECURE_COOKIES'] else '')
    return {'ok': True, 'csrf': csrf}, 200, [('Set-Cookie', cookie)]
