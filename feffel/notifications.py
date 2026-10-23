"""Audit trail, in-app notifications and the optional email outbox."""

from flask import current_app

from . import config
from .access import visible
from .util import now, uid


def audit(db, org, user, event, post=None, detail=''):
    db.execute('INSERT INTO audit VALUES(?,?,?,?,?,?,?)', (uid(), org, post, user, event, detail, now()))


def queue_mail(db, email, subject, body):
    """Queue an email for ``manage.py send-mail``. Does nothing unless SMTP is configured."""
    if config.smtp_configured():
        db.execute(
            'INSERT INTO mail_outbox(id,recipient,subject,body,created) VALUES(?,?,?,?,?)',
            (uid(), email, subject, body, now()),
        )


def notify(db, post, actor, message):
    """Tell every other member who can see the post."""
    for member in db.execute('SELECT * FROM members WHERE org=?', (post['org'],)).fetchall():
        if member['user'] == actor or not visible(member, post):
            continue
        db.execute(
            'INSERT INTO notifications VALUES(?,?,?,?,?,?,?)',
            (uid(), post['org'], member['user'], post['id'], message, 0, now()),
        )
        email = db.execute('SELECT email FROM users WHERE id=?', (member['user'],)).fetchone()[0]
        queue_mail(
            db,
            email,
            'Feffel · ' + message[:120],
            message + '\n\nOpen your workspace: ' + current_app.config['PUBLIC_URL'],
        )
