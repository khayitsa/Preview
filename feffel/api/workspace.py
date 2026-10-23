"""Workspace state for the signed-in member and their notifications."""

import json
import time

from flask import Blueprint, g

from .. import config
from ..access import can_company, visible
from ..db import get_db
from ..guards import org_member
from ..posts import post_data

bp = Blueprint('workspace', __name__)


def _decode(rows, *json_fields):
    items = [dict(row) for row in rows]
    for item in items:
        for field in json_fields:
            item[field] = json.loads(item[field])
    return items


@bp.get('/api/state')
@org_member
def state():
    """``GET /api/state``: everything the interface needs, limited to the member's scope."""
    db, org, user, member = get_db(), g.org, g.user, g.member
    companies = _decode(
        (
            c
            for c in db.execute('SELECT * FROM companies WHERE org=?', (org,))
            if can_company(member, c['id'])
        ),
        'workflow',
        'accounts',
    )
    members = _decode(
        db.execute(
            'SELECT m.*,u.name,u.email FROM members m JOIN users u ON u.id=m.user WHERE m.org=?', (org,)
        ),
        'companies',
        'platforms',
    )
    roles = _decode(db.execute('SELECT * FROM roles WHERE org=?', (org,)), 'permissions')
    # Pending invitations are only shown to people who can manage the team.
    invites = []
    if 'manage' in g.perms:
        invites = [
            dict(row)
            for row in db.execute(
                'SELECT id,email,role,title,expires FROM invites '
                'WHERE org=? AND used=0 AND expires>? ORDER BY expires DESC',
                (org, time.time()),
            )
        ]
    posts = [
        post_data(db, p, user)
        for p in db.execute('SELECT * FROM posts WHERE org=? ORDER BY created DESC,rowid DESC', (org,))
        if visible(member, p)
    ]
    notifications = [
        dict(row)
        for row in db.execute(
            'SELECT * FROM notifications WHERE org=? AND user=? ORDER BY created DESC,rowid DESC LIMIT 100',
            (org, user),
        )
    ]
    return (
        {
            'companies': companies,
            'members': members,
            'roles': roles,
            'invites': invites,
            'posts': posts,
            'notifications': notifications,
            'permissions': g.perms,
            'member': dict(member),
            'email_available': config.smtp_configured(),
        },
        200,
        [],
    )


@bp.post('/api/notifications/read')
@org_member
def mark_notifications_read():
    get_db().execute('UPDATE notifications SET seen=1 WHERE org=? AND user=?', (g.org, g.user))
    return {'ok': True}
