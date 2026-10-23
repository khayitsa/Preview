"""The ``flask`` operator commands: backup, reset-password and send-mail."""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_app import PNG, Client, app

from feffel.db import get_db
from feffel.util import uid


class CliTests(unittest.TestCase):
    def setUp(self):
        self.runner = app.test_cli_runner()
        self.owner = Client().register('cli-' + uid())

    def test_backup_copies_database_and_uploads(self):
        self.owner.call('/api/upload', raw=PNG, extra={'HTTP_X_FILE_NAME': 'a.png'})
        with tempfile.TemporaryDirectory() as parent:
            target = Path(parent) / 'backup'
            result = self.runner.invoke(args=['backup', str(target)])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn('Backup created', result.output)
            self.assertTrue(list((target / 'uploads').iterdir()))
            with sqlite3.connect(target / 'feffel.sqlite3') as copy:
                self.assertGreater(copy.execute('SELECT count(*) FROM users').fetchone()[0], 0)
            # A destination that already exists is refused.
            self.assertNotEqual(self.runner.invoke(args=['backup', str(target)]).exit_code, 0)

    def test_backup_refuses_destination_inside_data_directory(self):
        inside = Path(app.config['DATA_DIR']) / 'nested-backup'
        result = self.runner.invoke(args=['backup', str(inside)])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('outside the live data directory', result.output)
        self.assertFalse(inside.exists())

    def test_reset_password_replaces_password_and_revokes_sessions(self):
        email = self.owner.call('/api/me')[1]['user']['email']
        new = 'a-brand-new-password'
        result = self.runner.invoke(args=['reset-password', email], input=f'{new}\n{new}\n')
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.owner.call('/api/state')[0], 401)
        self.assertEqual(Client().call('/api/login', {'email': email, 'password': new})[0], 200)
        old = {'email': email, 'password': 'a-long-safe-password'}
        self.assertEqual(Client().call('/api/login', old)[0], 401)

    def test_reset_password_rejects_short_passwords_and_unknown_accounts(self):
        email = self.owner.call('/api/me')[1]['user']['email']
        short = self.runner.invoke(args=['reset-password', email], input='short\nshort\n')
        self.assertNotEqual(short.exit_code, 0)
        unknown = self.runner.invoke(
            args=['reset-password', 'nobody@example.test'],
            input='a-long-safe-password\na-long-safe-password\n',
        )
        self.assertIn('Account not found', unknown.output)

    def test_send_mail_needs_configuration(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('FEFFEL_SMTP_HOST', None)
            result = self.runner.invoke(args=['send-mail'])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('FEFFEL_SMTP_HOST', result.output)

    def test_send_mail_delivers_queued_messages(self):
        environment = {
            'FEFFEL_SMTP_HOST': 'smtp.example.test',
            'FEFFEL_SMTP_FROM': 'Feffel <notify@example.test>',
            'FEFFEL_SMTP_PORT': '587',
        }
        with app.app_context():
            db = get_db()
            db.execute('DELETE FROM mail_outbox')
            db.execute(
                'INSERT INTO mail_outbox(id,recipient,subject,body,created) VALUES(?,?,?,?,?)',
                (uid(), 'to@example.test', 'Hello', 'Body text', '2026-01-01T00:00:00+00:00'),
            )
        with mock.patch.dict(os.environ, environment), mock.patch('smtplib.SMTP') as smtp:
            result = self.runner.invoke(args=['send-mail'])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn('Delivered 1 messages', result.output)
        server = smtp.return_value
        server.starttls.assert_called_once()
        self.assertEqual(server.send_message.call_args[0][0]['To'], 'to@example.test')
        with app.app_context():
            sent = get_db().execute('SELECT sent FROM mail_outbox').fetchone()[0]
        self.assertTrue(sent)
        # Nothing left to deliver on the next run.
        with mock.patch.dict(os.environ, environment), mock.patch('smtplib.SMTP'):
            self.assertIn('No queued messages', self.runner.invoke(args=['send-mail']).output)


if __name__ == '__main__':
    unittest.main()
