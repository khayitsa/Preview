# Feffel — handover for G and Keith

This package is a working first version with actual user accounts, database persistence, uploaded media, scoped access, reviews and feedback. G should review the source and run the included tests; Keith can choose his normal hosting arrangement. No ChatGPT service is required to run it.

## Fastest local review

From the extracted `feffel/` directory create a virtual environment, run `pip install -r requirements.txt`, then `flask --app wsgi run`, and open `http://127.0.0.1:5000`. Python 3.12+ is required. The browser interface needs a current desktop browser. Node is only needed for the optional JavaScript syntax check.

The offline `Feffel-preview.html` shows fictional content without signup. It is deliberately read-only and does not contain the application database or a working team login.

## Option A: existing Linux server

```sh
cd /opt/feffel
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Create a private, writable data directory owned by the service user, for example `/srv/feffel-data`. Load these environment variables using the existing process manager:

```text
FEFFEL_DATA_DIR=/srv/feffel-data
FEFFEL_PUBLIC_URL=https://YOUR-ACTUAL-HOSTNAME
FEFFEL_SECURE_COOKIES=1
FEFFEL_MAX_UPLOAD_MB=100
```

Then serve the WSGI application:

```sh
.venv/bin/gunicorn --bind 127.0.0.1:8000 --workers 2 --threads 4 --timeout 180 wsgi:application
```

Put the existing HTTPS reverse proxy in front of port 8000. The `nginx.conf.example` and `feffel.service.example` files are adaptable examples. Keep the application at the origin root; hosting beneath a URL subdirectory is not supported without adapting the frontend URLs.

The application must have persistent local disk. It is not a static website, and cannot be hosted by uploading `feffel/static/` alone. It is not configured for serverless functions, a read-only filesystem or multiple machines sharing independent SQLite copies.

For local HTTP review, leave `FEFFEL_SECURE_COOKIES=0` (the default) and omit the public URL or set it to the local origin. HTTPS hosting needs the secure-cookie setting and the exact public origin. All web workers must use the same data directory.

## Option B: Docker

Copy `.env.example` to `.env` and replace the public URL with the actual hostname.

```sh
docker compose up --build -d
```

The container runs as a non-root user. Port 8000 is bound only to host loopback; use Keith's HTTPS reverse proxy. The named `feffel-data` volume holds the database and uploads. Preserve it across deployments. For an existing bind mount, give UID 10001 read/write access.

The package contains production server configuration, but the Docker image was not built in this environment. Review and build it on the target host. There is no dependency lockfile; resolve and pin the chosen Gunicorn version in the deployment process if needed.

## Email delivery (optional)

Without SMTP, in-app notifications and manually copied invitation links work immediately. To enable email, configure:

```text
FEFFEL_PUBLIC_URL=https://YOUR-ACTUAL-HOSTNAME
FEFFEL_SMTP_HOST=YOUR-SMTP-HOST
FEFFEL_SMTP_PORT=587
FEFFEL_SMTP_FROM=Feffel <notifications@YOUR-DOMAIN>
FEFFEL_SMTP_USER=YOUR-SMTP-USERNAME
FEFFEL_SMTP_PASSWORD=YOUR-SMTP-PASSWORD
```

Restart the web service after changing its environment. Run this command every minute with the same environment/data directory, under a scheduler with only one outbox worker:

```sh
/opt/feffel/.venv/bin/flask --app /opt/feffel/wsgi.py send-mail
```

Port 587 uses STARTTLS; port 465 uses implicit TLS. Messages stay in the outbox until successful delivery. Delivery can be retried and may duplicate after an interruption between sending and saving its result. No SMTP delivery was attempted during development.

## Option C: PythonAnywhere (or another WSGI host)

Feffel is a standard Flask application. Hosts that ask for a WSGI file only need the factory:

```python
# /var/www/YOUR_USERNAME_pythonanywhere_com_wsgi.py
import os, sys

sys.path.insert(0, '/home/YOUR_USERNAME/feffel')
os.environ['FEFFEL_DATA_DIR'] = '/home/YOUR_USERNAME/feffel-data'  # outside the web-served folders
os.environ['FEFFEL_PUBLIC_URL'] = 'https://YOUR_USERNAME.pythonanywhere.com'
os.environ['FEFFEL_SECURE_COOKIES'] = '1'

from feffel import create_app

application = create_app()
```

Install `requirements.txt` into the web app's virtualenv. Keep the data directory outside any static
mapping. This route has not been exercised on PythonAnywhere itself, so check uploads and the
SQLite database (which uses WAL mode) on that host's file system before real use.

## Backups and recovery

Keep database and media together. Take a backup during a brief maintenance pause so no upload or write occurs while files are copied:

```sh
flask --app wsgi backup /backups/feffel-2026-10-21
```

The destination must be a new directory. The tool uses SQLite's backup API and copies media. Choose a destination **outside** the live data directory. Back up the environment configuration separately using Keith's normal secrets handling.

Restore by stopping the web process, copying the backup's `feffel.sqlite3` and `uploads/` to the configured data directory, restoring filesystem ownership, and restarting. Do not mix database and media from different backups.

If a user needs password recovery, run locally with the same data-directory setting:

```sh
flask --app wsgi reset-password person@example.com
```

It prompts privately for the new password and revokes that account's existing sessions. There is no web password-reset flow yet.

## Data and operational details

- `/health` returns a basic application health response. It is not a full database/storage probe.
- The first launch creates the schema; small additive migrations for reporting fields are idempotent. Future schema changes need versioned migrations.
- The reverse proxy must accept the configured upload size plus overhead and allow 180-second responses.
- Login throttling is per remote address: 40 attempts per ten minutes. Behind a proxy, addresses may be shared, so adapt this to the deployment if needed. The app deliberately does not trust arbitrary forwarding headers.
- Production server logs may contain request paths. Invitation tokens are in the browser URL and should be redacted from proxy access logs; API audit entries never store the invitation token.
- Membership removal revokes organisation access immediately on the next request. Historical decisions remain intact. At least one unrestricted administrator with final override must remain.
- Use a dedicated host/origin. Media is served only after login and scope checks; no public upload-directory route exists.
- Modern browsers provide the PDF viewer. Browser PDF/mobile behaviour and video codecs need a quick check on the team's actual devices.

## Review focus for G

Run the included integration suite, create a temporary organisation, invite a creator and reviewers, and walk one real carousel through tasks, changes, resubmission, final approval and export. Check the intended company/platform scopes. The developer notes document first-version constraints explicitly; no public launch, data migration or third-party publishing has been performed.
