"""Small helpers shared by every module."""

import hashlib
import json
import secrets
from datetime import datetime, timezone


def now():
    """Current UTC time as an ISO-8601 string with second precision."""
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def uid():
    """A new random 128-bit identifier as 32 hex characters."""
    return secrets.token_hex(16)


def dumps(value):
    """Compact JSON (UTF-8 friendly) used for every JSON column and response."""
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def sha256(value):
    """Hex SHA-256, used so session and invitation tokens are never stored in the clear."""
    return hashlib.sha256(value.encode()).hexdigest()
