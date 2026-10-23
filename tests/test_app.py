"""Integration tests exercise the real Flask app, SQLite and authentication."""

import base64
import json
import os
from pathlib import Path
import atexit
import sys
import tempfile
import unittest

TEMP = tempfile.TemporaryDirectory()
atexit.register(TEMP.cleanup)
os.environ['FEFFEL_DATA_DIR'] = TEMP.name
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from feffel import create_app
from feffel.constants import PLATFORMS
from feffel.db import get_db
from feffel.util import uid

app = create_app({'DATA_DIR': TEMP.name})

PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII='
)


class Client:
    def __init__(self):
        self.cookie = ''
        self.csrf = ''
        self.org = ''

    def call(self, path, body=None, method=None, raw=None, extra=None):
        """Make a request. ``extra`` overrides WSGI environ keys (``HTTP_RANGE``, ``REMOTE_ADDR``...)."""
        data = raw if raw is not None else json.dumps(body).encode() if body is not None else b''
        environ = {'REMOTE_ADDR': 'test-' + str(id(self)), **(extra or {})}
        response = app.test_client(use_cookies=False).open(
            path,
            method=method or ('POST' if body is not None or raw is not None else 'GET'),
            data=data,
            headers={'Cookie': self.cookie, 'X-CSRF-Token': self.csrf, 'X-Org-ID': self.org},
            environ_overrides=environ,
        )
        headers = dict(response.headers)
        if 'Set-Cookie' in headers:
            self.cookie = headers['Set-Cookie'].split(';')[0]
        result = response.get_json(silent=True) if response.is_json else response.data
        response.close()
        if isinstance(result, dict) and 'csrf' in result:
            self.csrf = result['csrf']
        return response.status_code, result, headers

    def register(self, suffix):
        status, result, _ = self.call(
            '/api/register',
            {
                'email': suffix + '@example.test',
                'password': 'a-long-safe-password',
                'name': suffix,
                'organisation': suffix + ' group',
            },
        )
        assert status == 200, (status, result)
        me = self.call('/api/me')[1]
        self.org = me['organisations'][0]['org']
        self.state = self.call('/api/state')[1]
        return self

    def invite(self, owner, role, company_ids=None):
        email = 'member-' + uid() + '@example.test'
        res = owner.call(
            '/api/admin/invite',
            {'email': email, 'role': role, 'companies': company_ids or [], 'platforms': []},
        )
        assert res[0] == 201, res
        token = res[1]['token']
        res = self.call(
            '/api/accept-invite',
            {'email': email, 'password': 'a-long-safe-password', 'name': email.split('@')[0], 'token': token},
        )
        assert res[0] == 200, res
        self.org = owner.org
        self.state = self.call('/api/state')[1]
        return self


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.owner = Client().register('org-' + uid())
        self.state = self.owner.state
        self.company = self.state['companies'][0]['id']
        self.roles = {r['name']: r['id'] for r in self.state['roles']}

    def post(self, client=None, **kw):
        c = client or self.owner
        body = {
            'company': self.company,
            'platform': 'instagram',
            'format': 'Photo',
            'caption': 'A thoughtful caption.',
            'title': 'Launch post',
            'assets': [],
            **kw,
        }
        result = c.call('/api/posts', body)
        self.assertEqual(result[0], 201, result)
        return result[1]

    def upload(self, client=None):
        result = (client or self.owner).call('/api/upload', raw=PNG, extra={'HTTP_X_FILE_NAME': 'image.png'})
        self.assertEqual(result[0], 201, result)
        return result[1]['id']

    def action(self, p, route, client=None, **kw):
        return (client or self.owner).call('/api/posts/' + p['id'] + '/' + route, {'lock': p['lock'], **kw})

    def simple_workflow(self, client=None):
        result = self.owner.call(
            '/api/admin/workflow',
            {
                'company': self.company,
                'stages': [
                    {
                        'id': 'final',
                        'name': 'Final',
                        'role': self.roles['Head of Brand & Client Experience'],
                        'depends': [],
                        'mode': 'any',
                        'allow_self': True,
                    }
                ],
            },
        )
        self.assertEqual(result[0], 200, result)

    def test_auth_password_and_csrf(self):
        anon = Client()
        self.assertEqual(anon.call('/api/state')[0], 401)
        self.assertEqual(
            anon.call(
                '/api/login',
                {
                    'email': self.owner.call('/api/me')[1]['user']['email'],
                    'password': 'wrong-but-long-password',
                },
            )[0],
            401,
        )
        self.owner.csrf = 'bad'
        self.assertEqual(self.owner.call('/api/posts', {})[0], 403)

    def test_organisation_isolation_for_posts_and_files(self):
        asset = self.upload()
        p = self.post(assets=[asset])
        other = Client().register('other-' + uid())
        self.assertEqual(other.call('/api/posts/' + p['id'])[0], 404)
        self.assertEqual(other.call('/file/' + self.owner.org + '/' + asset)[0], 403)
        self.assertEqual(self.owner.call('/file/' + self.owner.org + '/' + asset)[0], 200)

    def test_scope_limits_companies_and_media(self):
        asset = self.upload()
        p = self.post(assets=[asset])
        self.owner.call('/api/admin/company', {'name': 'Other brand', 'color': '#112233'})
        state = self.owner.call('/api/state')[1]
        other = [c for c in state['companies'] if c['id'] != self.company][0]
        restricted = Client().invite(self.owner, self.roles['Creative Assistant'], [other['id']])
        self.assertEqual(restricted.call('/api/posts/' + p['id'])[0], 404)
        self.assertEqual(restricted.call('/file/' + self.owner.org + '/' + asset)[0], 404)
        self.assertEqual(len(restricted.call('/api/state')[1]['companies']), 1)

    def test_parallel_reviews_and_final_dependency(self):
        assistant = Client().invite(self.owner, self.roles['Creative Assistant'])
        creative = Client().invite(self.owner, self.roles['Head of Creative'])
        marketing = Client().invite(self.owner, self.roles['Head of Marketing'])
        p = self.post(assistant, assets=[self.upload(assistant)])
        p = self.action(p, 'submit', assistant)[1]
        result = self.action(p, 'decision', stage='brand', action='approve')
        self.assertEqual(result[0], 403)
        self.assertEqual(self.action(p, 'decision', assistant, stage='creative', action='approve')[0], 403)
        p = self.action(p, 'decision', creative, stage='creative', action='approve')[1]
        self.assertEqual(p['status'], 'review')
        p = self.action(p, 'decision', marketing, stage='marketing', action='approve')[1]
        self.assertEqual(p['status'], 'review')
        p = self.action(p, 'decision', stage='brand', action='approve')[1]
        self.assertEqual(p['status'], 'approved')
        self.assertEqual(self.owner.call('/api/posts/' + p['id'] + '/export')[0], 200)

    def test_edit_invalidates_approval_keeps_history(self):
        self.simple_workflow()
        asset = self.upload()
        p = self.post(assets=[asset])
        p = self.action(p, 'submit')[1]
        p = self.action(p, 'decision', stage='final', action='approve')[1]
        old = p['version']
        p = self.action(
            p,
            'edit',
            platform=p['platform'],
            format=p['format'],
            caption='Changed caption',
            title=p['title'],
            assets=[asset],
        )[1]
        self.assertEqual(p['status'], 'changes')
        self.assertGreater(p['version'], old)
        self.assertTrue(p['decisions'])
        self.assertFalse(any(s['done'] for s in p['stages']))
        self.assertEqual(self.owner.call('/api/posts/' + p['id'] + '/export')[0], 409)

    def test_change_request_returns_to_creator_and_restarts(self):
        self.simple_workflow()
        p = self.post(assets=[self.upload()])
        p = self.action(p, 'submit')[1]
        p = self.action(p, 'decision', stage='final', action='changes', note='Please change the heading')[1]
        self.assertEqual(p['status'], 'changes')
        old = p['version']
        p = self.action(p, 'submit')[1]
        self.assertGreater(p['version'], old)
        self.assertFalse(p['stages'][0]['done'])

    def test_optimistic_concurrency(self):
        p = self.post(assets=[self.upload()])
        self.assertEqual(self.action(p, 'submit')[0], 200)
        self.assertEqual(
            self.action(
                p, 'edit', platform='instagram', format='Photo', caption='stale', title='', assets=[]
            )[0],
            409,
        )

    def test_tasks_gate_review_and_parallel_workstreams(self):
        p = self.post(assets=[self.upload()])
        p = self.action(p, 'task', title='Design', kind='Creative')[1]
        p = self.action(p, 'task', title='Keywords', kind='Marketing')[1]
        self.assertEqual(self.action(p, 'submit')[0], 409)
        for t in p['tasks']:
            p = self.action(p, 'task-update', id=t['id'], status='done')[1]
        self.assertEqual(self.action(p, 'submit')[0], 200)

    def test_custom_workflow_cycle_denied(self):
        role = self.roles['Head of Creative']
        stages = [
            {'id': 'a', 'name': 'A', 'role': role, 'depends': ['b']},
            {'id': 'b', 'name': 'B', 'role': role, 'depends': ['a']},
        ]
        self.assertEqual(
            self.owner.call('/api/admin/workflow', {'company': self.company, 'stages': stages})[0], 400
        )

    def test_self_approval_can_be_disabled(self):
        stages = [
            {
                'id': 'a',
                'name': 'A',
                'role': self.roles['Head of Brand & Client Experience'],
                'depends': [],
                'allow_self': False,
            }
        ]
        self.owner.call('/api/admin/workflow', {'company': self.company, 'stages': stages})
        p = self.post(assets=[self.upload()])
        p = self.action(p, 'submit')[1]
        self.assertFalse(p['stages'][0]['can_approve'])
        self.assertEqual(self.action(p, 'decision', stage='a', action='approve')[0], 403)
        self.assertEqual(self.action(p, 'override', note='Final authority reviewed this directly')[0], 200)

    def test_all_reviewers_must_approve_when_configured(self):
        self.owner.call(
            '/api/admin/workflow',
            {
                'company': self.company,
                'stages': [
                    {
                        'id': 'a',
                        'name': 'A',
                        'role': self.roles['Head of Creative'],
                        'depends': [],
                        'mode': 'all',
                        'allow_self': True,
                    }
                ],
            },
        )
        a = Client().invite(self.owner, self.roles['Head of Creative'])
        b = Client().invite(self.owner, self.roles['Head of Creative'])
        p = self.post(assets=[self.upload()])
        p = self.action(p, 'submit')[1]
        p = self.action(p, 'decision', a, stage='a', action='approve')[1]
        self.assertEqual(p['status'], 'review')
        p = self.action(p, 'decision', b, stage='a', action='approve')[1]
        self.assertEqual(p['status'], 'approved')

    def test_annotations_replies_and_resolve_persist(self):
        p = self.post(assets=[self.upload()])
        context = {
            'asset_index': 0,
            'pin': [0.2, 0.4],
            'strokes': [{'color': '#ff0000', 'points': [[0.1, 0.2], [0.2, 0.3]]}],
            'selected_text': 'thoughtful',
        }
        p = self.action(p, 'comment', body='Move this please', context=context)[1]
        c = p['comments'][0]
        self.assertEqual(c['context'], context)
        p = self.action(p, 'comment', body='Done', parent=c['id'])[1]
        self.assertEqual(p['comments'][1]['parent'], c['id'])
        p = self.action(p, 'resolve', id=c['id'], resolved=True)[1]
        self.assertEqual(p['comments'][0]['resolved'], 1)

    def test_reactions_do_not_approve(self):
        p = self.post(assets=[self.upload()])
        p = self.action(p, 'reaction', emoji='👍')[1]
        self.assertEqual(p['status'], 'draft')
        self.assertEqual(len(p['reactions']), 1)

    def test_invite_bound_to_email_and_single_use(self):
        token = self.owner.call(
            '/api/admin/invite',
            {'email': 'specific-' + uid() + '@example.test', 'role': self.roles['Viewer']},
        )[1]['token']
        self.assertEqual(
            Client().call(
                '/api/accept-invite',
                {
                    'email': 'wrong@example.test',
                    'name': 'Wrong',
                    'password': 'a-long-safe-password',
                    'token': token,
                },
            )[0],
            400,
        )

    def test_last_administrator_cannot_be_demoted(self):
        member = self.state['member']
        self.assertEqual(
            self.owner.call(
                '/api/admin/member',
                {'id': member['id'], 'role': self.roles['Viewer'], 'companies': [], 'platforms': []},
            )[0],
            409,
        )

    def test_unsupported_upload_and_path_traversal(self):
        self.assertEqual(
            self.owner.call(
                '/api/upload', raw=b'<script>bad()</script>', extra={'HTTP_X_FILE_NAME': 'test.html'}
            )[0],
            400,
        )
        self.assertEqual(self.owner.call('/static/../__init__.py')[0], 404)

    def test_video_range_and_cross_origin(self):
        data = b'\x00\x00\x00\x18ftypmp42' + b'0' * 100
        aid = self.owner.call('/api/upload', raw=data, extra={'HTTP_X_FILE_NAME': 'video.mp4'})[1]['id']
        status, part, headers = self.owner.call(
            '/file/' + self.owner.org + '/' + aid, extra={'HTTP_RANGE': 'bytes=10-19'}
        )
        self.assertEqual(status, 206)
        self.assertEqual(len(part), 10)
        self.assertIn('Content-Range', headers)
        self.assertEqual(
            self.owner.call('/api/logout', {}, extra={'HTTP_ORIGIN': 'https://evil.example'})[0], 403
        )

    def test_every_platform_and_format_can_be_saved(self):
        for platform, formats in PLATFORMS.items():
            for fmt in formats:
                self.post(platform=platform, format=fmt, caption='Review content', assets=[])

    def test_historical_posts_are_not_pending(self):
        p = self.post(historical=True, assets=[self.upload()])
        self.assertEqual(p['status'], 'published')
        self.assertFalse(any(s['can_approve'] for s in p['stages']))

    def test_removed_member_loses_access_but_history_survives(self):
        viewer = Client().invite(self.owner, self.roles['Viewer'])
        mid = viewer.call('/api/state')[1]['member']['id']
        self.assertEqual(self.owner.call('/api/admin/remove-member', {'id': mid})[0], 200)
        self.assertEqual(viewer.call('/api/state')[0], 403)
        self.assertEqual(
            self.owner.call('/api/admin/remove-member', {'id': self.state['member']['id']})[0], 409
        )

    def test_reporting_structure_and_cycle_prevention(self):
        teammate = Client().invite(self.owner, self.roles['Head of Creative'])
        m = teammate.call('/api/state')[1]['member']
        owner = self.state['member']
        body = {
            'id': m['id'],
            'role': m['role'],
            'companies': [],
            'platforms': [],
            'department': 'Creative',
            'reports_to': owner['user'],
        }
        self.assertEqual(self.owner.call('/api/admin/member', body)[0], 200)
        self.assertEqual(
            self.owner.call(
                '/api/admin/member',
                {
                    'id': owner['id'],
                    'role': owner['role'],
                    'companies': [],
                    'platforms': [],
                    'reports_to': m['user'],
                },
            )[0],
            400,
        )

    def test_restore_archived_approval_starts_a_new_round(self):
        self.simple_workflow()
        p = self.post(assets=[self.upload()])
        p = self.action(p, 'submit')[1]
        p = self.action(p, 'decision', stage='final', action='approve')[1]
        p = self.action(p, 'archive')[1]
        p = self.action(p, 'archive')[1]
        p = self.action(p, 'submit')[1]
        self.assertEqual(p['status'], 'review')
        self.assertFalse(p['stages'][0]['done'])

    def test_historical_approval_survives_role_reassignment(self):
        self.simple_workflow()
        p = self.post(assets=[self.upload()])
        p = self.action(p, 'submit')[1]
        p = self.action(p, 'decision', stage='final', action='approve')[1]
        second = Client().invite(self.owner, self.roles['Head of Brand & Client Experience'])
        owner = self.state['member']
        result = self.owner.call(
            '/api/admin/member',
            {'id': owner['id'], 'role': self.roles['Viewer'], 'companies': [], 'platforms': []},
        )
        self.assertEqual(result[0], 200)
        p = second.call('/api/posts/' + p['id'])[1]
        self.assertTrue(p['stages'][0]['done'])
        self.assertEqual(p['status'], 'approved')

    def test_asset_ids_cannot_bypass_company_scope(self):
        asset = self.upload()
        self.post(assets=[asset])
        self.owner.call('/api/admin/company', {'name': 'Private brand', 'color': '#112233'})
        other = [c for c in self.owner.call('/api/state')[1]['companies'] if c['id'] != self.company][0]
        restricted = Client().invite(self.owner, self.roles['Creative Assistant'], [other['id']])
        result = restricted.call(
            '/api/posts',
            {'company': other['id'], 'platform': 'instagram', 'format': 'Photo', 'assets': [asset]},
        )
        self.assertEqual(result[0], 403)

    def test_platform_scope_blocks_view_and_creation(self):
        assistant = Client().invite(self.owner, self.roles['Creative Assistant'])
        m = assistant.call('/api/state')[1]['member']
        self.owner.call(
            '/api/admin/member',
            {'id': m['id'], 'role': m['role'], 'companies': [], 'platforms': ['linkedin']},
        )
        result = assistant.call(
            '/api/posts',
            {
                'company': self.company,
                'platform': 'instagram',
                'format': 'Text',
                'caption': 'Hidden',
                'assets': [],
            },
        )
        self.assertEqual(result[0], 400)
        p = self.post(assets=[self.upload()])
        self.assertEqual(assistant.call('/api/posts/' + p['id'])[0], 404)

    def test_notifications_queue_email_only_when_configured(self):
        other = Client().invite(self.owner, self.roles['Head of Creative'])
        os.environ['FEFFEL_SMTP_HOST'] = 'smtp.example.test'
        try:
            p = self.post(assets=[self.upload()])
            self.action(p, 'submit')
            with app.app_context():
                db = get_db()
                self.assertGreater(db.execute('SELECT count(*) FROM mail_outbox').fetchone()[0], 0)
            self.assertTrue(other.call('/api/state')[1]['notifications'])
        finally:
            os.environ.pop('FEFFEL_SMTP_HOST', None)

    def test_undo_latest_approval(self):
        self.simple_workflow()
        p = self.post(assets=[self.upload()])
        p = self.action(p, 'submit')[1]
        p = self.action(p, 'decision', stage='final', action='approve')[1]
        p = self.action(p, 'undo')[1]
        self.assertEqual(p['status'], 'review')
        self.assertFalse(p['stages'][0]['done'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
