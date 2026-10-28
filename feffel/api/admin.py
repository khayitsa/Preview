"""Administration (``POST /api/admin/<action>``): companies, accounts, workflows, roles, people.

Requires the ``manage`` permission. Actions that affect roles and members additionally need an
organisation-wide administrator, and never remove the last one.
"""

import json
import re
import secrets
import time

from flask import Blueprint, current_app, g

from .. import config, constants
from ..access import LAST_ADMIN_MESSAGE, can_company, other_org_admins, require_org_wide
from ..db import get_db
from ..errors import Error, require, textval
from ..guards import json_body, org_member, require_permission
from ..notifications import audit, queue_mail
from .auth import new_reset_token
from ..util import dumps, sha256, uid
from ..workflow import validate_workflow

bp = Blueprint('admin', __name__)

EMAIL = re.compile(r'[^\s@]+@[^\s@]+\.[^\s@]+')
COLOUR = re.compile(r'#[0-9a-fA-F]{6}')


@bp.post('/api/admin/<action>')
@org_member
def admin_route(action):
    require_permission('manage')
    body = json_body()
    get_db().execute('BEGIN IMMEDIATE')
    handler = ACTIONS.get(action)
    if handler is None:
        raise Error(404, 'Unknown settings action')
    result = handler(body)
    get_db().commit()
    return result or {'ok': True}


def _company_row(company_id):
    return get_db().execute('SELECT * FROM companies WHERE id=? AND org=?', (company_id, g.org)).fetchone()


def _role_exists(role_id):
    return get_db().execute('SELECT 1 FROM roles WHERE id=? AND org=?', (role_id, g.org)).fetchone()


# --- companies ---------------------------------------------------------------------------------


def company(body):
    db, org = get_db(), g.org
    name = textval(body.get('name', ''), 150)
    require(name, 'Company name required', 400)
    company_id = body.get('id')
    handle = textval(body.get('handle', ''), 100) or re.sub(r'[^a-z0-9_]', '', name.lower())
    colour = body.get('color', '#6b5ce7')
    require(COLOUR.fullmatch(colour), 'Invalid colour', 400)
    if company_id:
        require(can_company(g.member, company_id))
        require(_company_row(company_id), 'Company not found', 404)
        db.execute(
            'UPDATE companies SET name=?,handle=?,color=? WHERE id=?', (name, handle, colour, company_id)
        )
    else:
        require(
            not json.loads(g.member['companies']), 'Only organisation-wide administrators can add companies'
        )
        # A new company starts with the first company's workflow.
        inherited = json.loads(
            db.execute('SELECT workflow FROM companies WHERE org=? LIMIT 1', (org,)).fetchone()[0]
        )
        db.execute(
            'INSERT INTO companies VALUES(?,?,?,?,?,?,?)',
            (uid(), org, name, handle, colour, dumps(inherited), '{}'),
        )
    audit(db, org, g.user, 'Updated company settings', detail=name)


def account(body):
    """Display name, handle and bio of a company's profile on one platform."""
    db = get_db()
    company_id = body.get('company')
    require(can_company(g.member, company_id))
    row = _company_row(company_id)
    require(row, 'Company not found', 404)
    platform = body.get('platform')
    require(platform in constants.PLATFORMS, 'Unknown platform', 400)
    accounts = json.loads(row['accounts'])
    accounts[platform] = {
        'name': textval(body.get('name', ''), 150),
        'handle': textval(body.get('handle', ''), 100),
        'bio': textval(body.get('bio', ''), 1000),
    }
    db.execute('UPDATE companies SET accounts=? WHERE id=?', (dumps(accounts), company_id))
    audit(db, g.org, g.user, 'Updated account profile', detail=platform)


def workflow(body):
    db = get_db()
    company_id = body.get('company')
    require(can_company(g.member, company_id))
    require(_company_row(company_id), 'Company not found', 404)
    stages = validate_workflow(db, g.org, body.get('stages'))
    db.execute('UPDATE companies SET workflow=? WHERE id=?', (dumps(stages), company_id))
    audit(db, g.org, g.user, 'Updated approval workflow', detail=company_id)


# --- roles -------------------------------------------------------------------------------------


def role(body):
    db, org = get_db(), g.org
    require_org_wide(g.member, 'Only organisation-wide administrators can manage roles')
    name = textval(body.get('name', ''), 100)
    require(name, 'Role name required', 400)
    granted = body.get('permissions', [])
    require(
        isinstance(granted, list) and all(v in constants.PERMISSIONS for v in granted),
        'Unknown permission',
        400,
    )
    role_id = body.get('id')
    if role_id:
        require(_role_exists(role_id), 'Role not found', 404)
        # Every organisation keeps an unrestricted manager with override authority.
        if 'manage' not in granted or 'override' not in granted:
            require(other_org_admins(db, org, exclude_role=role_id), LAST_ADMIN_MESSAGE, 409)
        db.execute('UPDATE roles SET name=?,permissions=? WHERE id=?', (name, dumps(granted), role_id))
    else:
        db.execute('INSERT INTO roles VALUES(?,?,?,?)', (uid(), org, name, dumps(granted)))
    audit(db, org, g.user, 'Updated role', detail=name)


# --- people ------------------------------------------------------------------------------------


def remove_member(body):
    db, org = get_db(), g.org
    require_org_wide(g.member, 'Only organisation-wide administrators can remove members')
    member_id = body.get('id')
    old = db.execute('SELECT * FROM members WHERE id=? AND org=?', (member_id, org)).fetchone()
    require(old, 'Member not found', 404)
    require(other_org_admins(db, org, exclude_member=member_id), LAST_ADMIN_MESSAGE, 409)
    db.execute('DELETE FROM members WHERE id=?', (member_id,))
    audit(db, org, g.user, 'Removed member access', detail=old['user'])


def _access_fields(body):
    """Validate the role, scopes and reporting line shared by invitations and member updates."""
    db, org = get_db(), g.org
    require_org_wide(g.member, 'Only organisation-wide administrators can manage members')
    role_id = body.get('role')
    require(_role_exists(role_id), 'Role not found', 400)
    companies, platforms = body.get('companies', []), body.get('platforms', [])
    require(isinstance(companies, list) and isinstance(platforms, list), 'Invalid access scope', 400)
    for company_id in companies:
        require(_company_row(company_id), 'Unknown company', 400)
    require(all(p in constants.PLATFORMS for p in platforms), 'Unknown platform', 400)
    reports_to = body.get('reports_to') or ''
    require(isinstance(reports_to, str), 'Unknown reporting manager', 400)
    fields = {
        'role': role_id,
        'companies': companies,
        'platforms': platforms,
        'title': textval(body.get('title', ''), 150),
        'department': textval(body.get('department', ''), 100),
        'reports_to': reports_to,
    }
    require(
        not reports_to
        or db.execute('SELECT 1 FROM members WHERE org=? AND user=?', (org, reports_to)).fetchone(),
        'Unknown reporting manager',
        400,
    )
    return fields


def _reject_reporting_cycle(db, org, member_user, manager):
    seen = {member_user}
    while manager:
        require(manager not in seen, 'Reporting lines cannot contain a cycle', 400)
        seen.add(manager)
        row = db.execute('SELECT reports_to FROM members WHERE org=? AND user=?', (org, manager)).fetchone()
        manager = row['reports_to'] if row else ''


def member(body):
    """Change a member's role, scope, title, department or manager."""
    db, org = get_db(), g.org
    fields = _access_fields(body)
    member_id = body.get('id')
    old = db.execute('SELECT * FROM members WHERE id=? AND org=?', (member_id, org)).fetchone()
    require(old, 'Member not found', 404)
    new_permissions = json.loads(
        db.execute('SELECT permissions FROM roles WHERE id=?', (fields['role'],)).fetchone()[0]
    )
    stays_admin = (
        not fields['companies'] and not fields['platforms'] and {'manage', 'override'} <= set(new_permissions)
    )
    if not stays_admin:
        require(other_org_admins(db, org, exclude_member=member_id), LAST_ADMIN_MESSAGE, 409)
    _reject_reporting_cycle(db, org, old['user'], fields['reports_to'])
    db.execute(
        'UPDATE members SET role=?,companies=?,platforms=?,title=?,department=?,reports_to=? WHERE id=?',
        (
            fields['role'],
            dumps(fields['companies']),
            dumps(fields['platforms']),
            fields['title'],
            fields['department'],
            fields['reports_to'],
            member_id,
        ),
    )
    audit(db, org, g.user, 'Updated member access', detail=old['user'])


def invite(body):
    """Create a single-use, seven-day invitation bound to one email address."""
    db, org = get_db(), g.org
    fields = _access_fields(body)
    email = textval(body.get('email', ''), 254).lower()
    require(EMAIL.fullmatch(email), 'Invalid email', 400)
    token = secrets.token_urlsafe(32)
    token_hash = sha256(token)
    db.execute(
        'INSERT INTO invites(id,org,email,role,companies,platforms,title,token_hash,expires,used) '
        'VALUES(?,?,?,?,?,?,?,?,?,?)',
        (
            uid(),
            org,
            email,
            fields['role'],
            dumps(fields['companies']),
            dumps(fields['platforms']),
            fields['title'],
            token_hash,
            time.time() + constants.INVITE_SECONDS,
            0,
        ),
    )
    db.execute(
        'UPDATE invites SET department=?,reports_to=? WHERE token_hash=?',
        (fields['department'], fields['reports_to'], token_hash),
    )
    link = (current_app.config['PUBLIC_URL'] or '') + '/?invite=' + token
    if body.get('send_email'):
        require(
            current_app.config['PUBLIC_URL'] and config.smtp_configured(),
            'Email delivery has not been configured',
            409,
        )
        queue_mail(
            db,
            email,
            'You are invited to Feffel',
            'Join your team using this link (valid for seven days):\n'
            + current_app.config['PUBLIC_URL']
            + '/?invite='
            + token,
        )
    audit(db, org, g.user, 'Created invitation', detail=email)
    return {'token': token, 'email': email, 'expires_days': 7, 'link': link}, 201, []


def reset_link(body):
    """Create a one-day password reset link for a member, to hand over in person."""
    db, org = get_db(), g.org
    require_org_wide(g.member, 'Only organisation-wide administrators can reset passwords')
    member = db.execute(
        'SELECT m.user,u.email FROM members m JOIN users u ON u.id=m.user WHERE m.id=? AND m.org=?',
        (body.get('id'), org),
    ).fetchone()
    require(member, 'Member not found', 404)
    # An account that also belongs to another organisation is not this organisation's to take over.
    elsewhere = db.execute(
        'SELECT 1 FROM members WHERE user=? AND org!=?', (member['user'], org)
    ).fetchone()
    require(
        not elsewhere,
        'This person belongs to another organisation too. They can use "Forgot password" instead.',
        409,
    )
    token = new_reset_token(db, member['user'], constants.RESET_ADMIN_SECONDS)
    audit(db, org, g.user, 'Created password reset link', detail=member['email'])
    return {'token': token, 'email': member['email'], 'expires_hours': 24}, 201, []


def revoke_invite(body):
    """Withdraw an unused invitation so its link stops working."""
    db, org = get_db(), g.org
    require_org_wide(g.member, 'Only organisation-wide administrators can manage members')
    invite_id = body.get('id')
    row = db.execute('SELECT email FROM invites WHERE id=? AND org=? AND used=0', (invite_id, org)).fetchone()
    require(row, 'Invitation not found', 404)
    db.execute('DELETE FROM invites WHERE id=?', (invite_id,))
    audit(db, org, g.user, 'Revoked invitation', detail=row['email'])


ACTIONS = {
    'company': company,
    'account': account,
    'workflow': workflow,
    'role': role,
    'remove-member': remove_member,
    'member': member,
    'invite': invite,
    'revoke-invite': revoke_invite,
    'reset-link': reset_link,
}
