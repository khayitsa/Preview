"""Uploaded media: storing files and serving them (with byte ranges for video)."""

import json
import re
from pathlib import Path
from urllib.parse import unquote

from flask import Blueprint, current_app, g, request

from ..access import visible
from ..db import get_db
from ..errors import require
from ..guards import org_member, read_body
from ..util import now, uid

bp = Blueprint('files', __name__)

# File types are decided from the first bytes of the upload, never from its name.
UPLOAD_TYPES_MESSAGE = 'Supported uploads: JPG, PNG, GIF, WebP, MP4, MOV, WebM and PDF'
RANGE = re.compile(r'bytes=(\d*)-(\d*)')


def sniff_mime(data):
    """The MIME type for supported file signatures, or ``None``."""
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    if data.startswith(b'%PDF-'):
        return 'application/pdf'
    if len(data) > 12 and data[4:8] == b'ftyp':
        return 'video/quicktime' if b'qt  ' in data[8:32] else 'video/mp4'
    if data.startswith(b'\x1aE\xdf\xa3'):
        return 'video/webm'
    return None


@bp.post('/api/upload')
@org_member
def upload():
    """``POST /api/upload``: one raw file in the body, original name in ``X-File-Name``."""
    require('create' in g.perms or 'edit_all' in g.perms)
    data = read_body(current_app.config['MAX_UPLOAD_BYTES'])
    require(data, 'Empty upload', 400)
    name = unquote(Path(request.environ.get('HTTP_X_FILE_NAME', 'file')).name[:200])
    mime = sniff_mime(data)
    require(mime, UPLOAD_TYPES_MESSAGE, 400)
    asset_id = uid()
    (current_app.config['UPLOAD_DIR'] / asset_id).write_bytes(data)
    get_db().execute(
        'INSERT INTO assets VALUES(?,?,?,?,?,?,?)',
        (asset_id, g.org, g.user, name, mime, len(data), now()),
    )
    return {'id': asset_id, 'name': name, 'mime': mime, 'size': len(data)}, 201, []


def _asset_in_org(asset_id):
    asset = get_db().execute('SELECT * FROM assets WHERE id=? AND org=?', (asset_id, g.org)).fetchone()
    require(asset, 'File not found', 404)
    return asset


@bp.get('/media/<asset_id>')
@org_member
def media_by_header(asset_id):
    """``GET /media/<asset>``: organisation comes from the ``X-Org-ID`` header."""
    return serve(_asset_in_org(asset_id))


@bp.get('/file/<org_id>/<asset_id>')
@org_member
def media_by_url(org_id, asset_id):
    """``GET /file/<org>/<asset>``: for ``<img>``/``<video>`` tags, which cannot send headers.

    The organisation in the URL is only a selector. Session, membership and scope are still checked
    by ``org_member``.
    """
    return serve(_asset_in_org(asset_id))


def _may_view(db, member, asset):
    if asset['user'] == member['user']:
        return True
    for post in db.execute('SELECT * FROM posts WHERE org=?', (member['org'],)):
        if not visible(member, post):
            continue
        if asset['id'] in json.loads(post['assets']):
            return True
        for revision in db.execute('SELECT data FROM revisions WHERE post=?', (post['id'],)):
            if asset['id'] in json.loads(json.loads(revision['data'])['assets']):
                return True
    return False


def serve(asset):
    """Send a file the member may see, honouring a single ``Range`` header."""
    require(_may_view(get_db(), g.member, asset), 'File not found', 404)
    path = current_app.config['UPLOAD_DIR'] / asset['id']
    require(path.is_file(), 'File not found', 404)
    size = path.stat().st_size
    headers = [('Content-Type', asset['mime']), ('Accept-Ranges', 'bytes'), ('Content-Disposition', 'inline')]
    requested = request.environ.get('HTTP_RANGE', '')
    if not requested:
        return path.read_bytes(), 200, headers
    match = RANGE.fullmatch(requested)
    require(match and (match[1] or match[2]), 'Invalid range', 416)
    start = int(match[1]) if match[1] else max(0, size - int(match[2]))
    end = min(size - 1, int(match[2])) if match[1] and match[2] else size - 1
    require(start <= end and start < size, 'Invalid range', 416)
    with path.open('rb') as f:
        f.seek(start)
        data = f.read(end - start + 1)
    return data, 206, headers + [('Content-Range', f'bytes {start}-{end}/{size}')]
