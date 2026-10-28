"""Cross-cutting behaviour: same-origin check, security headers and JSON error responses."""

import sqlite3
import traceback
from urllib.parse import urlsplit

from flask import current_app, request
from werkzeug.exceptions import HTTPException

from .errors import Error, require
from .guards import SAFE_METHODS

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; "
    "style-src 'self' 'unsafe-inline'; script-src 'self'; frame-src 'self' blob:; "
    "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
    "frame-ancestors 'self'"
)


def register_hooks(app):
    @app.before_request
    def check_origin():
        """Mutations must come from this site (or ``FEFFEL_PUBLIC_URL`` when set)."""
        if request.method in SAFE_METHODS:
            return
        origin = request.headers.get('Origin')
        if not origin:
            return
        public_url = current_app.config['PUBLIC_URL']
        if public_url:
            allowed = origin.rstrip('/') == public_url
        else:
            # Compare the host only: behind an HTTPS proxy the app sees "http" while the browser
            # sends an "https" origin, and the scheme adds nothing to the same-site check.
            allowed = urlsplit(origin).netloc == request.host
        require(allowed, 'Cross-origin request denied')

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = CONTENT_SECURITY_POLICY
        return response

    @app.errorhandler(Error)
    def handle_error(error):
        return {'error': error.message}, error.status

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        return {'error': error.description or error.name}, error.code

    @app.errorhandler(ValueError)  # includes json.JSONDecodeError and UnicodeDecodeError
    @app.errorhandler(KeyError)
    @app.errorhandler(TypeError)
    @app.errorhandler(OverflowError)  # an integer too large for SQLite
    @app.errorhandler(sqlite3.InterfaceError)  # a list or object where a value was expected
    @app.errorhandler(sqlite3.ProgrammingError)
    def handle_bad_input(_error):
        return {'error': 'Invalid request'}, 400

    @app.errorhandler(Exception)
    def handle_unexpected(error):
        current_app.logger.error('Unhandled error\n%s', ''.join(traceback.format_exception(error)))
        return {'error': 'Server error. Check server logs.'}, 500
