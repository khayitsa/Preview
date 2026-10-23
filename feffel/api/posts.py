"""Posts: create, read, export, and every state change (``POST /api/posts/<id>/<action>``).

State changes share one pattern, implemented in ``post_action``: parse the body, open a write
transaction, reject the request if the caller's ``lock`` is stale, run the action function, then
commit and return the refreshed post. Action functions receive ``(post, body)``.
"""

import io
import json
import re
import time
import zipfile
from datetime import datetime

from flask import Blueprint, current_app, g

from .. import constants
from ..access import can_company, can_edit, can_platform, permissions, visible
from ..db import get_db
from ..errors import Error, require, textval
from ..guards import json_body, org_member, require_permission
from ..notifications import audit, notify
from ..posts import get_post, post_data, snapshot, validate_post_body
from ..util import dumps, now, uid
from ..workflow import stage_state

EDITABLE_STATES = ['draft', 'changes', 'rejected']
UNDO_WINDOW_SECONDS = 30

bp = Blueprint('posts', __name__)


# --- create / read / export ------------------------------------------------------------------


@bp.post('/api/posts')
@org_member
def create():
    """``POST /api/posts``: a new draft, or a historical (already published) post."""
    db, org, user, member = get_db(), g.org, g.user, g.member
    require_permission('create')
    body = json_body()
    company_id = body.get('company')
    company = db.execute('SELECT * FROM companies WHERE id=? AND org=?', (company_id, org)).fetchone()
    require(company and can_company(member, company_id), 'Company not available')
    values = validate_post_body(db, org, body, member)
    require(can_platform(member, values['platform']))
    historical = bool(body.get('historical'))
    post_id, stamp = uid(), now()
    db.execute('BEGIN IMMEDIATE')
    db.execute(
        'INSERT INTO posts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (
            post_id,
            org,
            company_id,
            user,
            values['platform'],
            values['format'],
            values['title'],
            values['caption'],
            values['assets'],
            values['scheduled'],
            int(historical),
            'published' if historical else 'draft',
            1,
            1,
            company['workflow'],
            stamp,
            stamp,
        ),
    )
    post = get_post(db, post_id)
    snapshot(db, post, user)
    audit(db, org, user, 'Added historical post' if historical else 'Created draft', post_id)
    db.commit()
    return post_data(db, post, user, True), 201, []


def _visible_post(post_id):
    """The post if it exists in this organisation and the member's scope allows it."""
    post = get_db().execute('SELECT * FROM posts WHERE id=? AND org=?', (post_id, g.org)).fetchone()
    require(post and visible(g.member, post), 'Post not found', 404)
    return post


@bp.get('/api/posts/<post_id>')
@org_member
def show(post_id):
    return post_data(get_db(), _visible_post(post_id), g.user, True), 200, []


@bp.get('/api/posts/<post_id>/export')
@org_member
def export_pack(post_id):
    """Caption, ordered media and the full review record as a ZIP."""
    post, db = _visible_post(post_id), get_db()
    require_permission('export')
    require(
        post['status'] in ['approved', 'published'], 'Only approved or historical posts can be exported', 409
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('caption.txt', post['caption'])
        archive.writestr('review-record.json', json.dumps(post_data(db, post, g.user, True), indent=2))
        for index, asset_id in enumerate(json.loads(post['assets'])):
            asset = db.execute('SELECT * FROM assets WHERE id=?', (asset_id,)).fetchone()
            filename = re.sub(r'[^a-zA-Z0-9._-]', '_', asset['name'])
            archive.write(current_app.config['UPLOAD_DIR'] / asset_id, f'media/{index + 1:02}-{filename}')
    download = f'feffel-{post["id"][:8]}-v{post["version"]}.zip'
    return (
        buffer.getvalue(),
        200,
        [
            ('Content-Type', 'application/zip'),
            ('Content-Disposition', f'attachment; filename="{download}"'),
        ],
    )


@bp.post('/api/posts/<post_id>/<action>')
@org_member
def post_action(post_id, action):
    _visible_post(post_id)
    db = get_db()
    body = json_body()
    db.execute('BEGIN IMMEDIATE')
    post = db.execute('SELECT * FROM posts WHERE id=? AND org=?', (post_id, g.org)).fetchone()
    # Comments, replies, reactions and tasks never conflict with edits, so they skip the lock.
    if action not in COLLABORATION_ACTIONS:
        require(
            body.get('lock') == post['lock'],
            'This post changed while you were reviewing. Refresh and try again.',
            409,
        )
    handler = ACTIONS.get(action)
    if handler is None:
        raise Error(404, 'Unknown action')
    handler(post, body)
    db.commit()
    return post_data(db, get_post(db, post_id), g.user, True), 200, []


# --- editing and submitting -------------------------------------------------------------------


def edit(post, body):
    db = get_db()
    require(can_edit(g.perms, g.member, post))
    require(post['status'] != 'archived', 'Restore this post before editing', 409)
    values = validate_post_body(db, g.org, body, g.member)
    require(can_platform(g.member, values['platform']))
    changed = any(values[k] != post[k] for k in ['platform', 'format', 'caption', 'assets'])
    status = post['status']
    if changed and status not in ['draft', 'published']:
        status = 'changes'
    version = post['version'] + 1
    db.execute(
        'UPDATE posts SET platform=?,format=?,title=?,caption=?,assets=?,scheduled=?,status=?,'
        'version=?,lock=lock+1,updated=? WHERE id=?',
        (
            values['platform'],
            values['format'],
            values['title'],
            values['caption'],
            values['assets'],
            values['scheduled'],
            status,
            version,
            now(),
            post['id'],
        ),
    )
    # Cosmetic edits preserve the approval trail on the new version; content changes never do.
    if not changed:
        for d in db.execute(
            'SELECT * FROM decisions WHERE post=? AND version=?', (post['id'], post['version'])
        ).fetchall():
            db.execute(
                'INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?)',
                (uid(), post['id'], version, d['stage'], d['user'], d['action'], d['note'], now()),
            )
    snapshot(db, get_post(db, post['id']), g.user)
    audit(db, g.org, g.user, 'Edited post', post['id'], f'Version {version}; content changed: {changed}')
    notify(db, post, g.user, f'{g.session["name"]} updated {post["title"] or "a post"} to version {version}')


def submit(post, body):
    db = get_db()
    require(can_edit(g.perms, g.member, post))
    require(post['status'] in EDITABLE_STATES, 'Post cannot be submitted in its current state', 409)
    assets = json.loads(post['assets'])
    require(post['caption'] or assets, 'Add content before submitting', 400)
    require(post['format'] in ['Text', 'Community post'] or assets, 'This format needs media', 400)
    require(
        not db.execute("SELECT 1 FROM tasks WHERE post=? AND status!='done'", (post['id'],)).fetchone(),
        'Complete the creative and marketing tasks before submitting',
        409,
    )
    company = db.execute('SELECT workflow FROM companies WHERE id=?', (post['company'],)).fetchone()
    stages = json.loads(company['workflow'])
    members = db.execute('SELECT * FROM members WHERE org=?', (g.org,)).fetchall()
    for stage in stages:
        # Capture who may review now, so later role changes cannot rewrite this review round.
        stage['reviewers'] = [
            m['user']
            for m in members
            if m['role'] == stage['role']
            and visible(m, post)
            and 'review' in permissions(db, m)
            and (stage['allow_self'] or m['user'] != post['creator'])
        ]
    # Resubmission after requested changes always starts a fresh review round.
    version = post['version'] + 1 if post['status'] in ['changes', 'rejected'] else post['version']
    db.execute(
        "UPDATE posts SET status='review',workflow=?,version=?,lock=lock+1,updated=? WHERE id=?",
        (dumps(stages), version, now(), post['id']),
    )
    if version != post['version']:
        snapshot(db, get_post(db, post['id']), g.user)
    audit(db, g.org, g.user, 'Submitted for review', post['id'])
    notify(db, post, g.user, f'{post["title"] or "A post"} is ready for review')


# --- review decisions -------------------------------------------------------------------------

DECISION_LABELS = {'approve': 'Approved stage', 'changes': 'Requested changes', 'reject': 'Rejected post'}


def decision(post, body):
    db = get_db()
    require_permission('review')
    require(post['status'] == 'review', 'This post is not awaiting review', 409)
    stage = next((s for s in stage_state(db, post, g.user) if s['id'] == body.get('stage')), None)
    require(stage and stage['can_approve'], 'This stage is not assigned to you or is not ready', 403)
    verdict = body.get('action')
    require(verdict in DECISION_LABELS, 'Invalid decision', 400)
    note = textval(body.get('note', ''), 5000)
    require(verdict == 'approve' or note, 'Explain the changes or rejection', 400)
    db.execute(
        'INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?)',
        (uid(), post['id'], post['version'], stage['id'], g.user, verdict, note, now()),
    )
    status = {'changes': 'changes', 'reject': 'rejected'}.get(verdict, 'review')
    if verdict == 'approve' and all(s['done'] for s in stage_state(db, post, g.user)):
        status = 'approved'
    db.execute('UPDATE posts SET status=?,lock=lock+1,updated=? WHERE id=?', (status, now(), post['id']))
    audit(
        db,
        g.org,
        g.user,
        DECISION_LABELS[verdict],
        post['id'],
        stage['name'] + (': ' + note if note else ''),
    )
    notify(db, post, g.user, f'{g.session["name"]}: {stage["name"]} — {verdict}')


def undo(post, body):
    db = get_db()
    last = db.execute(
        'SELECT * FROM decisions WHERE post=? AND version=? ORDER BY rowid DESC LIMIT 1',
        (post['id'], post['version']),
    ).fetchone()
    require(
        last
        and last['user'] == g.user
        and last['action'] == 'approve'
        and time.time() - datetime.fromisoformat(last['created']).timestamp() < UNDO_WINDOW_SECONDS,
        'Undo is only available for your latest approval for 30 seconds',
        409,
    )
    db.execute(
        'INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?)',
        (uid(), post['id'], post['version'], last['stage'], g.user, 'undo', '', now()),
    )
    db.execute("UPDATE posts SET status='review',lock=lock+1,updated=? WHERE id=?", (now(), post['id']))
    audit(db, g.org, g.user, 'Undid approval', post['id'])


def override(post, body):
    db = get_db()
    require_permission('override')
    require(post['status'] not in ['archived', 'published'], 'Cannot override this post', 409)
    note = textval(body.get('note', ''), 5000)
    require(note, 'Give a reason for overriding', 400)
    db.execute("UPDATE posts SET status='approved',lock=lock+1,updated=? WHERE id=?", (now(), post['id']))
    db.execute(
        'INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?)',
        (uid(), post['id'], post['version'], 'override', g.user, 'approve', note, now()),
    )
    audit(db, g.org, g.user, 'Final approval override', post['id'], note)
    notify(db, post, g.user, f'{g.session["name"]} used final approval override')


def archive(post, body):
    db = get_db()
    require_permission('archive')
    require(post['status'] != 'published', 'Historical posts stay in the feed', 409)
    restoring = post['status'] == 'archived'
    db.execute(
        'UPDATE posts SET status=?,version=version+?,lock=lock+1,updated=? WHERE id=?',
        ('draft' if restoring else 'archived', int(restoring), now(), post['id']),
    )
    if restoring:
        snapshot(db, get_post(db, post['id']), g.user)
    audit(db, g.org, g.user, 'Restored post' if restoring else 'Archived post', post['id'])


# --- collaboration: comments, reactions, tasks (no lock required) ------------------------------


def comment(post, body):
    db = get_db()
    text = textval(body.get('body', ''), 10000)
    context = body.get('context', {})
    require(isinstance(context, dict) and len(dumps(context)) < 200000, 'Annotation too large', 400)
    require(text or context.get('strokes'), 'Write feedback or draw an annotation', 400)
    version = body.get('version', post['version'])
    require(
        db.execute('SELECT 1 FROM revisions WHERE post=? AND version=?', (post['id'], version)).fetchone(),
        'Version not found',
        400,
    )
    parent = body.get('parent')
    require(
        not parent
        or db.execute('SELECT 1 FROM comments WHERE id=? AND post=?', (parent, post['id'])).fetchone(),
        'Invalid reply',
        400,
    )
    db.execute(
        'INSERT INTO comments VALUES(?,?,?,?,?,?,?,?,?)',
        (uid(), post['id'], version, g.user, text, dumps(context), 0, parent, now()),
    )
    audit(db, g.org, g.user, 'Added feedback', post['id'], f'Version {version}')
    notify(db, post, g.user, f'{g.session["name"]} left feedback on {post["title"] or "a post"}')


def resolve(post, body):
    db = get_db()
    found = db.execute(
        'SELECT * FROM comments WHERE id=? AND post=?', (body.get('id'), post['id'])
    ).fetchone()
    require(found, 'Comment not found', 404)
    require(found['user'] == g.user or 'review' in g.perms or 'edit_all' in g.perms)
    db.execute('UPDATE comments SET resolved=? WHERE id=?', (int(bool(body.get('resolved'))), found['id']))
    audit(
        db,
        g.org,
        g.user,
        'Resolved feedback' if body.get('resolved') else 'Reopened feedback',
        post['id'],
        found['id'],
    )


def reaction(post, body):
    db = get_db()
    emoji = body.get('emoji')
    require(emoji in constants.REACTIONS, 'Unknown reaction', 400)
    db.execute('DELETE FROM reactions WHERE post=? AND user=?', (post['id'], g.user))
    if emoji:
        db.execute('INSERT INTO reactions VALUES(?,?,?)', (post['id'], g.user, emoji))


def add_task(post, body):
    db = get_db()
    require(can_edit(g.perms, g.member, post))
    require(post['status'] in EDITABLE_STATES, 'Add tasks before submitting for review', 409)
    title = textval(body.get('title', ''), 300)
    require(title, 'Task title required', 400)
    assignee = body.get('assignee') or None
    assigned = (
        db.execute('SELECT * FROM members WHERE org=? AND user=?', (g.org, assignee)).fetchone()
        if assignee
        else None
    )
    require(
        not assignee or assigned and visible(assigned, post), 'Assignee must have access to this post', 400
    )
    kind = body.get('kind', 'Creative')
    require(kind in constants.TASK_KINDS, 'Unknown task type', 400)
    db.execute(
        'INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
        (uid(), post['id'], kind, title, assignee, 'todo', '', textval(body.get('due', ''), 64), now()),
    )
    audit(db, g.org, g.user, 'Added task', post['id'], title)


def update_task(post, body):
    db = get_db()
    task = db.execute('SELECT * FROM tasks WHERE id=? AND post=?', (body.get('id'), post['id'])).fetchone()
    require(task, 'Task not found', 404)
    require(task['assignee'] == g.user or 'edit_all' in g.perms or post['creator'] == g.user)
    status = body.get('status')
    require(status in constants.TASK_STATUSES, 'Unknown task status', 400)
    if status != 'done' and post['status'] in ['review', 'approved']:
        require(
            'edit_all' in g.perms or post['creator'] == g.user,
            'Reopening a reviewed task requires an editor',
        )
        db.execute(
            "UPDATE posts SET status='changes',version=version+1,lock=lock+1,updated=? WHERE id=?",
            (now(), post['id']),
        )
        snapshot(db, get_post(db, post['id']), g.user)
    db.execute(
        'UPDATE tasks SET status=?,notes=? WHERE id=?',
        (status, textval(body.get('notes', task['notes']), 10000), task['id']),
    )
    audit(db, g.org, g.user, 'Updated task', post['id'], task['title'] + ' → ' + status)
    notify(db, post, g.user, f'{g.session["name"]} updated a {task["kind"].lower()} task')


ACTIONS = {
    'edit': edit,
    'submit': submit,
    'decision': decision,
    'undo': undo,
    'override': override,
    'archive': archive,
    'comment': comment,
    'resolve': resolve,
    'reaction': reaction,
    'task': add_task,
    'task-update': update_task,
}
COLLABORATION_ACTIONS = ('comment', 'reaction', 'resolve', 'task', 'task-update')
