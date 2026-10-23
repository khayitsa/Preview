"""Posts: loading, serialising for the API, snapshots and input validation."""

import json

from . import constants
from .access import visible
from .errors import require, textval
from .util import dumps, now, uid
from .workflow import stage_state


def get_post(db, post_id):
    return db.execute('SELECT * FROM posts WHERE id=?', (post_id,)).fetchone()


def asset_rows(db, asset_ids_json):
    """Asset metadata for a JSON list of asset ids, in order."""
    return [
        dict(db.execute('SELECT id,name,mime,size FROM assets WHERE id=?', (a,)).fetchone())
        for a in json.loads(asset_ids_json)
    ]


def _rows(db, query, *args):
    return [dict(row) for row in db.execute(query, args)]


def post_data(db, post, user, detailed=False):
    """A post as the API returns it. ``detailed`` adds comments, revisions, history and decisions."""
    p = dict(post)
    p['assets'] = asset_rows(db, p['assets'])
    p['stages'] = stage_state(db, post, user)
    p['creator_name'] = db.execute('SELECT name FROM users WHERE id=?', (p['creator'],)).fetchone()[0]
    p['comments_count'] = db.execute(
        'SELECT COUNT(*) FROM comments WHERE post=? AND resolved=0', (p['id'],)
    ).fetchone()[0]
    p['reactions'] = _rows(
        db, 'SELECT r.*,u.name FROM reactions r JOIN users u ON u.id=r.user WHERE post=?', p['id']
    )
    p['tasks'] = _rows(db, 'SELECT * FROM tasks WHERE post=? ORDER BY created', p['id'])
    p['workflow'] = json.loads(p['workflow'])
    if detailed:
        p['comments'] = _rows(
            db,
            'SELECT c.*,u.name FROM comments c JOIN users u ON u.id=c.user '
            'WHERE post=? ORDER BY c.created,c.rowid',
            p['id'],
        )
        for comment in p['comments']:
            comment['context'] = json.loads(comment['context'])
        p['revisions'] = _rows(
            db,
            'SELECT r.*,u.name FROM revisions r JOIN users u ON u.id=r.user '
            'WHERE post=? ORDER BY version DESC',
            p['id'],
        )
        for revision in p['revisions']:
            revision['data'] = json.loads(revision['data'])
            revision['data']['assets'] = asset_rows(db, revision['data']['assets'])
        p['history'] = _rows(
            db,
            'SELECT a.*,u.name FROM audit a JOIN users u ON u.id=a.user '
            'WHERE post=? ORDER BY a.created DESC,a.rowid DESC',
            p['id'],
        )
        p['decisions'] = _rows(
            db,
            'SELECT d.*,u.name FROM decisions d JOIN users u ON u.id=d.user '
            'WHERE post=? ORDER BY d.created DESC,d.rowid DESC',
            p['id'],
        )
    return p


def snapshot(db, post, user):
    """Store the post's current content as a revision (one per version)."""
    db.execute(
        'INSERT INTO revisions VALUES(?,?,?,?,?,?)',
        (uid(), post['id'], post['version'], dumps(dict(post)), user, now()),
    )


def asset_validation(db, org, assets, member):
    """Media attached to a post must exist in the organisation and be within the member's reach."""
    require(
        isinstance(assets, list)
        and len(assets) <= constants.MAX_ASSETS_PER_POST
        and len(set(assets)) == len(assets),
        f'Maximum {constants.MAX_ASSETS_PER_POST} distinct media files',
        400,
    )
    for asset_id in assets:
        require(
            isinstance(asset_id, str)
            and db.execute('SELECT 1 FROM assets WHERE id=? AND org=?', (asset_id, org)).fetchone(),
            'Invalid media file',
            400,
        )
        owner = db.execute('SELECT user FROM assets WHERE id=?', (asset_id,)).fetchone()['user']
        if owner != member['user']:
            used_in_visible_post = any(
                visible(member, p) and asset_id in json.loads(p['assets'])
                for p in db.execute('SELECT * FROM posts WHERE org=?', (org,))
            )
            require(used_in_visible_post, 'Media is outside your access scope', 403)
    return assets


def validate_post_body(db, org, body, member):
    """Validate the editable fields of a post and return them in database form."""
    platform = body.get('platform')
    require(
        platform in constants.PLATFORMS and body.get('format') in constants.PLATFORMS[platform],
        'Unknown platform or content format',
        400,
    )
    assets = asset_validation(db, org, body.get('assets', []), member)
    if body['format'] == 'PDF document':
        for asset_id in assets:
            mime = db.execute('SELECT mime FROM assets WHERE id=?', (asset_id,)).fetchone()[0]
            require(mime == 'application/pdf', 'A PDF document needs PDF files', 400)
    return {
        'platform': platform,
        'format': body['format'],
        'title': textval(body.get('title', ''), 300),
        'caption': textval(body.get('caption', ''), 50000),
        'assets': dumps(assets),
        'scheduled': textval(body.get('scheduled', ''), 64),
    }
