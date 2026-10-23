"""Deployment settings, read from ``FEFFEL_*`` environment variables.

``create_app()`` loads these into ``app.config``; tests and other callers can override any key
by passing a mapping to ``create_app``.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def settings_from_env():
    data_dir = Path(os.environ.get('FEFFEL_DATA_DIR', str(PROJECT_ROOT / 'data'))).resolve()
    return {
        # Private, writable directory for the SQLite database and uploaded media.
        'DATA_DIR': data_dir,
        # Canonical public origin, e.g. https://feffel.example.com (needed behind HTTPS).
        'PUBLIC_URL': os.environ.get('FEFFEL_PUBLIC_URL', '').rstrip('/'),
        # Send the session cookie only over HTTPS.
        'SECURE_COOKIES': os.environ.get('FEFFEL_SECURE_COOKIES', '0') == '1',
        'MAX_UPLOAD_BYTES': int(os.environ.get('FEFFEL_MAX_UPLOAD_MB', '100')) * 1024 * 1024,
    }


def smtp_configured():
    """Read on every call: operators may set the variable after the process starts."""
    return bool(os.environ.get('FEFFEL_SMTP_HOST'))
