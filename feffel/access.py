"""Who may see and do what.

A member has one role per organisation (which carries permissions) and optional company and
platform scopes. An empty scope list means "everything". Scope and permission are checked
independently on every operation.
"""

import json

from .errors import require


def permissions(db, member):
    """The permission names granted by the member's role."""
    row = db.execute(
        'SELECT permissions FROM roles WHERE id=? AND org=?', (member['role'], member['org'])
    ).fetchone()
    return json.loads(row[0])


def can_company(member, company):
    scope = json.loads(member['companies'])
    return not scope or company in scope


def can_platform(member, platform):
    scope = json.loads(member['platforms'])
    return not scope or platform in scope


def visible(member, post):
    """True when the post falls inside the member's company and platform scope."""
    return can_company(member, post['company']) and can_platform(member, post['platform'])


def can_edit(perms, member, post):
    """Editors may change any post; creators may change their own."""
    return 'edit_all' in perms or ('create' in perms and post['creator'] == member['user'])


def is_org_wide(member):
    """True when the member has no company or platform restriction."""
    return not json.loads(member['companies']) and not json.loads(member['platforms'])


def require_org_wide(member, message):
    require(is_org_wide(member), message)


def other_org_admins(db, org, *, exclude_member=None, exclude_role=None):
    """Members who could still administer the organisation if one member or role changed.

    An administrator is organisation-wide and holds both ``manage`` and ``override``.
    """
    query, args = 'SELECT * FROM members WHERE org=?', [org]
    if exclude_role:
        query, args = query + ' AND role!=?', args + [exclude_role]
    if exclude_member:
        query, args = query + ' AND id!=?', args + [exclude_member]
    return [
        m
        for m in db.execute(query, args)
        if is_org_wide(m) and {'manage', 'override'} <= set(permissions(db, m))
    ]


LAST_ADMIN_MESSAGE = 'Keep at least one organisation-wide administrator with final override'
