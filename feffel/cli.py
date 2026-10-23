"""Operator commands, run with the same ``FEFFEL_DATA_DIR`` as the web service:

flask --app wsgi backup /srv/backups/2026-10-22
flask --app wsgi reset-password person@example.com
flask --app wsgi send-mail
"""

import os
import shutil
import smtplib
import sqlite3
import ssl
from email.message import EmailMessage
from pathlib import Path

import click
from flask import current_app
from flask.cli import with_appcontext

from .db import connect
from .security import password_hash
from .util import now


def register(app):
    app.cli.add_command(backup)
    app.cli.add_command(reset_password)
    app.cli.add_command(send_mail)


@click.command('backup')
@click.argument('destination')
@with_appcontext
def backup(destination):
    """Copy the database and uploads into a new directory outside the data directory."""
    data_dir = Path(current_app.config['DATA_DIR'])
    target = Path(destination).resolve()
    if target.is_relative_to(data_dir):
        raise click.ClickException('Backup destination must be outside the live data directory.')
    target.mkdir(parents=True, exist_ok=False)
    source = connect(current_app.config['DATABASE'])
    dest = sqlite3.connect(target / 'feffel.sqlite3')
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()
    shutil.copytree(current_app.config['UPLOAD_DIR'], target / 'uploads')
    click.echo(f'Backup created: {target}')


@click.command('reset-password')
@click.argument('email')
@with_appcontext
def reset_password(email):
    """Set a new password for an account and sign it out everywhere."""
    password = click.prompt('New password (12+ characters)', hide_input=True, confirmation_prompt=True)
    if not 12 <= len(password) <= 256:
        raise click.ClickException('Use 12–256 characters.')
    db = connect(current_app.config['DATABASE'])
    try:
        user = db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
        if not user:
            raise click.ClickException('Account not found.')
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE users SET password=? WHERE id=?', (password_hash(password), user['id']))
        db.execute('DELETE FROM sessions WHERE user=?', (user['id'],))
        db.commit()
    finally:
        db.close()
    click.echo('Password updated; previous sessions revoked.')


@click.command('send-mail')
@with_appcontext
def send_mail():
    """Deliver queued notification emails over SMTP (run from one scheduler only)."""
    host = os.environ.get('FEFFEL_SMTP_HOST')
    sender = os.environ.get('FEFFEL_SMTP_FROM')
    if not host or not sender:
        raise click.ClickException('Set FEFFEL_SMTP_HOST and FEFFEL_SMTP_FROM first.')
    port = int(os.environ.get('FEFFEL_SMTP_PORT', '587'))
    db = connect(current_app.config['DATABASE'])
    try:
        # Failed deliveries remain queued; no secrets are logged.
        pending = db.execute(
            'SELECT * FROM mail_outbox WHERE sent IS NULL ORDER BY created LIMIT 100'
        ).fetchall()
        if not pending:
            click.echo('No queued messages.')
            return
        context = ssl.create_default_context()
        if port == 465:
            smtp = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
        else:
            smtp = smtplib.SMTP(host, port, timeout=30)
        try:
            if port != 465:
                smtp.starttls(context=context)
            if os.environ.get('FEFFEL_SMTP_USER'):
                smtp.login(os.environ['FEFFEL_SMTP_USER'], os.environ.get('FEFFEL_SMTP_PASSWORD', ''))
            delivered = 0
            for item in pending:
                message = EmailMessage()
                message['From'] = sender
                message['To'] = item['recipient']
                message['Subject'] = item['subject']
                message['Message-ID'] = '<' + item['id'] + '@feffel.local>'
                message.set_content(item['body'])
                try:
                    smtp.send_message(message)
                    db.execute('UPDATE mail_outbox SET sent=?,error=? WHERE id=?', (now(), '', item['id']))
                    delivered += 1
                except smtplib.SMTPException:
                    db.execute(
                        'UPDATE mail_outbox SET error=? WHERE id=?',
                        ('Delivery failed; check SMTP service.', item['id']),
                    )
            click.echo(f'Delivered {delivered} messages.')
        finally:
            smtp.quit()
    finally:
        db.close()
