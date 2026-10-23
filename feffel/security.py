"""Password hashing."""

import hashlib
import hmac
import secrets


def password_hash(password, salt=None):
    """Return ``salt:scrypt`` for a password. Pass an existing salt to re-derive for comparison."""
    salt = salt or secrets.token_hex(16)
    hashed = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ':' + hashed


def password_ok(password, stored):
    """Constant-time check of a password against a stored ``salt:scrypt`` value."""
    return hmac.compare_digest(password_hash(password, stored.split(':')[0]), stored)
