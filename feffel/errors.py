"""Request errors and input validation helpers."""


class Error(Exception):
    """An error that is safe to show the user: becomes ``{"error": message}`` with this status."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def require(ok, message='Not permitted', status=403):
    """Raise ``Error`` unless ``ok`` is truthy."""
    if not ok:
        raise Error(status, message)


def textval(value, maximum=10000):
    """Validate a string field (type and length) and return it stripped."""
    require(isinstance(value, str) and len(value) <= maximum, 'Invalid text or text too long', 400)
    return value.strip()
