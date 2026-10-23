"""WSGI entry point: ``gunicorn wsgi:application`` or ``flask --app wsgi run``."""

from feffel import create_app

application = create_app()
app = application  # `flask --app wsgi` looks for `app` or `application`
