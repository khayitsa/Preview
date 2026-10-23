"""Request helpers and the decorators that protect views.

* ``@signed_in``  : needs a valid session; mutations also need the CSRF token.
* ``@org_member`` : ``@signed_in`` plus an organisation the user belongs to. Sets
  ``g.org``, ``g.member``, ``g.perms`` and ``g.user``.
"""

import hmac
import json
from functools import wraps

from flask import g, request

from . import constants
from .access import permissions
from .db import get_db
from .errors import require
from .sessions import load_session

SAFE_METHODS = ('GET', 'HEAD')


def read_body(max_bytes=constants.MAX_JSON_BYTES):
    length = int(request.content_length or 0)
    require(0 <= length <= max_bytes, 'Request too large', 413)
    return request.get_data()


def json_body():
    """The request body as a JSON object (an empty body is ``{}``)."""
    value = json.loads(read_body() or b'{}')
    require(isinstance(value, dict), 'Expected an object', 400)
    return value


def require_permission(name, message='Not permitted'):
    require(name in g.perms, message)


def _check_csrf():
    if request.method not in SAFE_METHODS:
        supplied = request.headers.get('X-CSRF-Token', '')
        require(
            hmac.compare_digest(supplied, g.session['csrf']),
            'Session expired. Refresh and try again.',
            403,
        )


def _require_session():
    g.session = load_session(get_db())
    require(g.session, 'Sign in to continue', 401)
    _check_csrf()


def signed_in(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        _require_session()
        return view(*args, **kwargs)

    return wrapper


def org_member(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        _require_session()
        # <img>/<video> cannot send headers, so /file/<org_id>/... carries the organisation in the URL.
        g.org = request.view_args.get('org_id') or request.headers.get('X-Org-ID', '')
        g.member = (
            get_db()
            .execute('SELECT * FROM members WHERE org=? AND user=?', (g.org, g.session['user']))
            .fetchone()
        )
        require(g.member, 'Select an organisation you belong to', 403)
        g.perms = permissions(get_db(), g.member)
        g.user = g.session['user']
        return view(*args, **kwargs)

    return wrapper
