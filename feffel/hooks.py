"""Cross-cutting behaviour: same-origin check, security headers and JSON error responses."""

import traceback

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
        expected = current_app.config['PUBLIC_URL'] or (
            request.environ.get('wsgi.url_scheme', 'http') + '://' + request.environ.get('HTTP_HOST', '')
        )
        require(not origin or origin.rstrip('/') == expected, 'Cross-origin request denied')

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
    def handle_bad_input(_error):
        return {'error': 'Invalid request'}, 400

    @app.errorhandler(Exception)
    def handle_unexpected(error):
        current_app.logger.error('Unhandled error\n%s', ''.join(traceback.format_exception(error)))
        return {'error': 'Server error. Check server logs.'}, 500
