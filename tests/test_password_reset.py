"""Password reset: emailed links, administrator-issued links and the rules around both."""

import os
import time
import unittest

from test_app import Client, app

from feffel.db import get_db
from feffel.util import uid

PASSWORD = 'a-long-safe-password'
NEW_PASSWORD = 'a-brand-new-password'


class ResetBase(unittest.TestCase):
    def setUp(self):
        self.owner = Client().register('reset-' + uid())
        self.roles = {r['name']: r['id'] for r in self.owner.state['roles']}
        self.member = Client().invite(self.owner, self.roles['Viewer'])
        self.email = self.member.call('/api/me')[1]['user']['email']
        self.member_id = next(m['id'] for m in self.owner.call('/api/state')[1]['members'] if m['email'] == self.email)

    def reset_link(self, client=None):
        return (client or self.owner).call('/api/admin/reset-link', {'id': self.member_id})

    def use(self, token, email=None, password=NEW_PASSWORD):
        return Client().call(
            '/api/reset-password', {'token': token, 'email': email or self.email, 'password': password}
        )

    def can_sign_in(self, password):
        return Client().call('/api/login', {'email': self.email, 'password': password})[0] == 200


class AdministratorResetTests(ResetBase):
    def test_reset_link_changes_the_password_and_signs_out_everywhere(self):
        status, result, _ = self.reset_link()
        self.assertEqual(status, 201)
        self.assertEqual(self.member.call('/api/state')[0], 200)
        self.assertEqual(self.use(result['token'])[0], 200)
        self.assertTrue(self.can_sign_in(NEW_PASSWORD))
        self.assertFalse(self.can_sign_in(PASSWORD))
        self.assertEqual(self.member.call('/api/state')[0], 401)  # the old session is gone

    def test_a_link_works_once_and_only_for_its_own_email(self):
        token = self.reset_link()[1]['token']
        self.assertEqual(self.use(token, email=self.owner.call('/api/me')[1]['user']['email'])[0], 400)
        self.assertEqual(self.use(token)[0], 200)
        self.assertEqual(self.use(token, password='yet-another-long-password')[0], 400)
        self.assertEqual(self.use('not-a-token')[0], 400)
        self.assertEqual(Client().call('/api/reset-password', {'token': [], 'email': self.email,
                                                              'password': NEW_PASSWORD})[0], 400)

    def test_a_new_link_replaces_the_previous_one(self):
        first = self.reset_link()[1]['token']
        second = self.reset_link()[1]['token']
        self.assertEqual(self.use(first)[0], 400)
        self.assertEqual(self.use(second)[0], 200)

    def test_expired_links_are_refused(self):
        token = self.reset_link()[1]['token']
        with app.app_context():
            db = get_db()
            db.execute('UPDATE password_resets SET expires=?', (time.time() - 1,))
        self.assertEqual(self.use(token)[0], 400)

    def test_short_passwords_are_refused_and_keep_the_link_usable(self):
        token = self.reset_link()[1]['token']
        self.assertEqual(self.use(token, password='short')[0], 400)
        self.assertEqual(self.use(token)[0], 200)

    def test_only_organisation_wide_managers_can_issue_links(self):
        self.assertEqual(self.reset_link(self.member)[0], 403)
        scoped = Client().invite(self.owner, self.roles['Head of Brand & Client Experience'],
                                 company_ids=[self.owner.state['companies'][0]['id']])
        self.assertEqual(self.reset_link(scoped)[0], 403)

    def test_cannot_reset_someone_who_belongs_to_another_organisation(self):
        other = Client().register('elsewhere-' + uid())
        email = other.call('/api/me')[1]['user']['email']
        status, invite, _ = self.owner.call(
            '/api/admin/invite', {'email': email, 'role': self.roles['Viewer']}
        )
        self.assertEqual(status, 201)
        Client().call('/api/accept-invite', {'email': email, 'password': PASSWORD, 'name': 'x',
                                             'token': invite['token']})
        member_id = next(m['id'] for m in self.owner.call('/api/state')[1]['members'] if m['email'] == email)
        self.assertEqual(self.owner.call('/api/admin/reset-link', {'id': member_id})[0], 409)

    def test_unknown_member_is_not_found(self):
        self.assertEqual(self.owner.call('/api/admin/reset-link', {'id': 'nope'})[0], 404)


class ForgotPasswordTests(ResetBase):
    def tearDown(self):
        os.environ.pop('FEFFEL_SMTP_HOST', None)
        app.config['PUBLIC_URL'] = ''

    def mail_count(self):
        with app.app_context():
            return get_db().execute(
                "SELECT count(*) FROM mail_outbox WHERE recipient=? AND subject LIKE 'Reset%'", (self.email,)
            ).fetchone()[0]

    def test_without_email_set_up_nothing_is_sent_and_the_answer_says_so(self):
        status, result, _ = Client().call('/api/forgot-password', {'email': self.email})
        self.assertEqual((status, result['email_available']), (200, False))
        self.assertEqual(self.mail_count(), 0)

    def test_with_email_set_up_a_link_is_queued_and_works(self):
        os.environ['FEFFEL_SMTP_HOST'] = 'smtp.example.test'
        app.config['PUBLIC_URL'] = 'https://feffel.example'
        anon = Client()
        self.assertTrue(anon.call('/api/me')[1]['email_available'])
        status, result, _ = anon.call('/api/forgot-password', {'email': self.email})
        self.assertEqual((status, result['email_available']), (200, True))
        with app.app_context():
            body = get_db().execute(
                "SELECT body FROM mail_outbox WHERE recipient=? AND subject LIKE 'Reset%'", (self.email,)
            ).fetchone()[0]
        self.assertIn('https://feffel.example/?reset=', body)
        token = body.split('?reset=')[1].strip()
        self.assertEqual(self.use(token)[0], 200)

    def test_unknown_addresses_get_the_same_answer_and_no_email(self):
        os.environ['FEFFEL_SMTP_HOST'] = 'smtp.example.test'
        app.config['PUBLIC_URL'] = 'https://feffel.example'
        known = Client().call('/api/forgot-password', {'email': self.email})[1]
        unknown = Client().call('/api/forgot-password', {'email': 'nobody-' + uid() + '@example.test'})[1]
        self.assertEqual(known, unknown)
        self.assertEqual(self.mail_count(), 1)

    def test_invalid_email_is_a_bad_request(self):
        self.assertEqual(Client().call('/api/forgot-password', {'email': 'nope'})[0], 400)


if __name__ == '__main__':
    unittest.main(verbosity=2)
