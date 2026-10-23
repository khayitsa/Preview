"""Accounts and sessions: sign-in, registration, invitation acceptance, ``/api/me``, sign-out."""

import re
import time

from flask import Blueprint, g, request

from .. import constants
from ..db import get_db
from ..errors import require, textval
from ..guards import json_body, signed_in
from ..notifications import audit
from ..security import password_hash, password_ok
from ..sessions import load_session, start_session
from ..util import dumps, now, sha256, uid
from ..workflow import default_workflow

bp = Blueprint('auth', __name__)

EMAIL = re.compile(r'[^\s@]+@[^\s@]+\.[^\s@]+')
THROTTLE_WINDOW = 600  # seconds
THROTTLE_LIMIT = 40  # attempts per window and client address


def throttle(db):
    """Allow at most ``THROTTLE_LIMIT`` account attempts per client address per ten minutes."""
    key = request.environ.get('REMOTE_ADDR', 'local')
    t = time.time()
    db.execute('BEGIN IMMEDIATE')
    row = db.execute('SELECT * FROM rate_limits WHERE key=?', (key,)).fetchone()
    if row and t - row['window'] < THROTTLE_WINDOW:
        db.execute('UPDATE rate_limits SET count=count+1 WHERE key=?', (key,))
        db.commit()
        require(row['count'] < THROTTLE_LIMIT, 'Too many attempts. Try again in ten minutes.', 429)
    else:
        db.execute('INSERT OR REPLACE INTO rate_limits VALUES(?,?,1)', (key, t))
        db.execute('DELETE FROM rate_limits WHERE window<?', (t - 3600,))
        db.commit()


# --- public endpoints -----------------------------------------------------------------------


def _credentials():
    """Throttle, then read and validate the email and password from the request body."""
    throttle(get_db())
    body = json_body()
    email = textval(body.get('email', ''), 254).lower()
    require(EMAIL.fullmatch(email), 'Enter a valid email', 400)
    password = body.get('password', '')
    require(
        isinstance(password, str) and 12 <= len(password) <= 256,
        'Use a password of 12–256 characters',
        400,
    )
    return body, email, password


@bp.post('/api/login')
def login():
    db = get_db()
    _, email, password = _credentials()
    user = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    # Derive a hash even for unknown addresses so response time does not reveal who has an account.
    valid = password_ok(password, user['password'] if user else password_hash('dummy-password-123'))
    require(user and valid, 'Email or password is incorrect', 401)
    return start_session(db, user['id'])


@bp.post('/api/register')
def register():
    """Create an account and a new organisation with default roles and a first company."""
    db = get_db()
    body, email, password = _credentials()
    db.execute('BEGIN IMMEDIATE')
    existing = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    require(not existing, 'An account already exists. Sign in instead.', 409)
    user, org = uid(), uid()
    name = textval(body.get('name', ''), 100)
    org_name = textval(body.get('organisation', ''), 150)
    require(name and org_name, 'Your name and organisation are required', 400)
    db.execute('INSERT INTO users VALUES(?,?,?,?,?)', (user, email, name, password_hash(password), now()))
    db.execute('INSERT INTO orgs VALUES(?,?,?)', (org, org_name, now()))
    roles = {}
    for title, perms in constants.DEFAULT_ROLES:
        role_id = uid()
        roles[title] = role_id
        db.execute('INSERT INTO roles VALUES(?,?,?,?)', (role_id, org, title, dumps(perms)))
    db.execute(
        'INSERT INTO members(id,org,user,role,companies,platforms,title) VALUES(?,?,?,?,?,?,?)',
        (uid(), org, user, roles[constants.ADMIN_ROLE], '[]', '[]', constants.ADMIN_ROLE),
    )
    handle = re.sub(r'[^a-z0-9_]', '', org_name.lower())[:30] or 'brand'
    db.execute(
        'INSERT INTO companies VALUES(?,?,?,?,?,?,?)',
        (uid(), org, org_name, handle, '#6b5ce7', dumps(default_workflow(roles)), '{}'),
    )
    audit(db, org, user, 'Created organisation')
    db.commit()
    return start_session(db, user)


@bp.post('/api/accept-invite')
def accept_invite():
    """Join an organisation with a single-use invitation token bound to one email address."""
    db = get_db()
    body, email, password = _credentials()
    db.execute('BEGIN IMMEDIATE')
    existing = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    invite = db.execute(
        'SELECT * FROM invites WHERE token_hash=? AND used=0 AND expires>?',
        (sha256(body.get('token', '')), time.time()),
    ).fetchone()
    require(
        invite and invite['email'].lower() == email,
        'Invitation is invalid, expired or for another email',
        400,
    )
    if existing:
        require(password_ok(password, existing['password']), 'Use your existing account password', 401)
        user = existing['id']
    else:
        user = uid()
        db.execute(
            'INSERT INTO users VALUES(?,?,?,?,?)',
            (user, email, textval(body.get('name', ''), 100) or email, password_hash(password), now()),
        )
    require(
        not db.execute('SELECT 1 FROM members WHERE org=? AND user=?', (invite['org'], user)).fetchone(),
        'Already a member',
        409,
    )
    db.execute(
        'INSERT INTO members(id,org,user,role,companies,platforms,title) VALUES(?,?,?,?,?,?,?)',
        (
            uid(),
            invite['org'],
            user,
            invite['role'],
            invite['companies'],
            invite['platforms'],
            invite['title'],
        ),
    )
    db.execute(
        'UPDATE members SET department=?,reports_to=? WHERE org=? AND user=?',
        (invite['department'], invite['reports_to'], invite['org'], user),
    )
    db.execute('UPDATE invites SET used=1 WHERE id=?', (invite['id'],))
    audit(db, invite['org'], user, 'Joined organisation')
    db.commit()
    return start_session(db, user)


# --- signed-in endpoints --------------------------------------------------------------------


@bp.get('/api/me')
def me():
    """Who is signed in, their organisations and the platform catalogue (works signed out)."""
    session = load_session(get_db())
    if not session:
        return {'user': None, 'platforms': constants.PLATFORMS}
    memberships = [
        dict(row)
        for row in get_db().execute(
            'SELECT m.org,o.name FROM members m JOIN orgs o ON o.id=m.org WHERE m.user=?',
            (session['user'],),
        )
    ]
    return {
        'user': {'id': session['user'], 'name': session['name'], 'email': session['email']},
        'csrf': session['csrf'],
        'organisations': memberships,
        'platforms': constants.PLATFORMS,
    }


@bp.post('/api/logout')
@signed_in
def logout():
    get_db().execute('DELETE FROM sessions WHERE token=?', (g.session['token'],))
    clear = f'{constants.SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax'
    return {'ok': True}, 200, [('Set-Cookie', clear)]
