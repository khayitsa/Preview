"""The single-page interface (``/``) and the health check."""

from flask import Blueprint, Response, render_template, url_for

from .. import constants
from ..util import dumps

bp = Blueprint('site', __name__)


@bp.get('/')
def index():
    return render_template('index.html')


@bp.get('/health')
def health():
    return {'status': 'ok', 'application': 'Feffel', 'version': constants.VERSION}


@bp.get('/manifest.webmanifest')
def manifest():
    """Lets phones and desktops install Feffel as an app ("Add to Home screen" / "Install")."""
    icon = lambda name, purpose: {  # noqa: E731
        'src': url_for('static', filename='icons/' + name),
        'sizes': name.split('-')[-1].split('.')[0] + 'x' + name.split('-')[-1].split('.')[0],
        'type': 'image/png',
        'purpose': purpose,
    }
    body = {
        'name': 'Feffel',
        'short_name': 'Feffel',
        'description': 'Review social posts the way they will appear on each platform.',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'background_color': '#f6f5fa',
        'theme_color': '#f6f5fa',
        'icons': [icon('icon-192.png', 'any'), icon('icon-512.png', 'any'), icon('maskable-512.png', 'maskable')],
    }
    return Response(dumps(body), mimetype='application/manifest+json')


SERVICE_WORKER = """\
// Feffel always needs the network (private, always-fresh data), so nothing is cached here.
// This worker exists so browsers treat the site as an installable app.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
"""


@bp.get('/sw.js')
def service_worker():
    return Response(SERVICE_WORKER, mimetype='text/javascript')
