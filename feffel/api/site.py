"""The single-page interface (``/``) and the health check."""

from flask import Blueprint, render_template

from .. import constants

bp = Blueprint('site', __name__)


@bp.get('/')
def index():
    return render_template('index.html')


@bp.get('/health')
def health():
    return {'status': 'ok', 'application': 'Feffel', 'version': constants.VERSION}
