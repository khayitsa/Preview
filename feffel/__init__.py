"""Feffel: a portable, multi-organisation social content review application (Flask)."""

from pathlib import Path

from flask import Flask

from . import cli, config
from .db import close_db, init_db
from .hooks import register_hooks


def create_app(overrides=None):
    """Application factory.

    ``overrides`` is an optional mapping applied on top of the environment settings
    (see ``feffel/config.py``), mainly for tests.
    """
    app = Flask(__name__)
    app.config.from_mapping(config.settings_from_env())
    app.config.update(overrides or {})

    data_dir = Path(app.config['DATA_DIR'])
    app.config['UPLOAD_DIR'] = data_dir / 'uploads'
    app.config['DATABASE'] = data_dir / 'feffel.sqlite3'
    app.config['UPLOAD_DIR'].mkdir(parents=True, exist_ok=True)
    app.json.ensure_ascii = False  # keep UTF-8 readable in API responses
    app.json.sort_keys = False

    init_db(app.config['DATABASE'])
    app.teardown_appcontext(close_db)
    register_hooks(app)

    from .api import admin, auth, files, posts, site, workspace

    for module in (site, auth, workspace, files, posts, admin):
        app.register_blueprint(module.bp)

    cli.register(app)
    return app
