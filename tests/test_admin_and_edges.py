"""Characterisation tests for admin settings, media delivery and error handling.

These pin down behaviour that the first test module does not exercise, so the
backend can be reorganised without changing what it does.
"""

import io
import json
import unittest
import zipfile

from test_app import PNG, Client

from feffel.util import uid


class Base(unittest.TestCase):
    def setUp(self):
        self.owner = Client().register('edge-' + uid())
        self.state = self.owner.state
        self.company = self.state['companies'][0]['id']
        self.roles = {r['name']: r['id'] for r in self.state['roles']}

    def upload(self, client=None):
        status, result, _ = (client or self.owner).call(
            '/api/upload', raw=PNG, extra={'HTTP_X_FILE_NAME': 'pic.png'}
        )
        self.assertEqual(status, 201, result)
        return result['id']

    def post(self, client=None, **kw):
        body = {
            'company': self.company,
            'platform': 'instagram',
            'format': 'Photo',
            'caption': 'Caption',
            'title': 'Title',
            'assets': [],
            **kw,
        }
        status, result, _ = (client or self.owner).call('/api/posts', body)
        self.assertEqual(status, 201, result)
        return result

    def act(self, p, route, client=None, **kw):
        return (client or self.owner).call(f'/api/posts/{p["id"]}/{route}', {'lock': p['lock'], **kw})

    def single_stage_workflow(self):
        stage = {
            'id': 'final',
            'name': 'Final',
            'depends': [],
            'mode': 'any',
            'allow_self': True,
            'role': self.roles['Head of Brand & Client Experience'],
        }
        status, result, _ = self.owner.call(
            '/api/admin/workflow', {'company': self.company, 'stages': [stage]}
        )
        self.assertEqual(status, 200, result)


class SessionAndRequestTests(Base):
    def test_logout_ends_the_session(self):
        self.assertEqual(self.owner.call('/api/logout', {})[0], 200)
        self.assertEqual(self.owner.call('/api/state')[0], 401)
        self.assertIsNone(self.owner.call('/api/me')[1]['user'])

    def test_health_endpoint_is_public(self):
        status, result, _ = Client().call('/health')
        self.assertEqual((status, result['status']), (200, 'ok'))

    def test_cross_origin_mutation_is_refused(self):
        status, _, _ = self.owner.call(
            '/api/posts', {}, extra={'HTTP_ORIGIN': 'https://evil.example', 'HTTP_HOST': 'feffel.test'}
        )
        self.assertEqual(status, 403)

    def test_malformed_json_and_unknown_routes(self):
        self.assertEqual(self.owner.call('/api/posts', raw=b'{not json')[0], 400)
        self.assertEqual(self.owner.call('/api/posts', raw=b'[1,2]')[0], 400)
        self.assertEqual(self.owner.call('/api/nothing-here')[0], 404)
        self.assertEqual(self.owner.call('/api/admin/nothing-here', {})[0], 404)

    def test_organisation_header_must_match_membership(self):
        self.owner.org = 'not-an-org'
        self.assertEqual(self.owner.call('/api/state')[0], 403)

    def test_login_throttle_returns_429(self):
        anon = Client()
        env = {'REMOTE_ADDR': '203.0.113.' + str(len(uid()))}
        credentials = {'email': 'nobody@example.test', 'password': 'wrong-but-long-password'}
        statuses = [anon.call('/api/login', credentials, extra=env)[0] for _ in range(42)]
        self.assertEqual(statuses[0], 401)
        self.assertEqual(statuses[-1], 429)

    def test_security_headers_are_set(self):
        _, _, headers = self.owner.call('/api/state')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn("default-src 'self'", headers['Content-Security-Policy'])
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_static_index_served_and_methods_restricted(self):
        status, body, _ = Client().call('/')
        self.assertEqual(status, 200)
        self.assertIn(b'<div id="app">', body)
        self.assertEqual(Client().call('/', {})[0], 405)

    def test_static_nested_assets_are_served(self):
        status, body, headers = Client().call('/static/js/core.js')
        self.assertEqual(status, 200)
        self.assertIn('javascript', headers['Content-Type'])
        self.assertEqual(Client().call('/static/js/../../__init__.py')[0], 404)


class NotificationTests(Base):
    def test_notifications_are_created_for_others_and_can_be_marked_read(self):
        member = Client().invite(self.owner, self.roles['Head of Creative'])
        p = self.post(assets=[self.upload()])
        self.act(p, 'comment', body='Looks good')
        unread = member.call('/api/state')[1]['notifications']
        self.assertTrue(unread and not any(n['seen'] for n in unread))
        self.assertEqual(member.call('/api/notifications/read', {})[0], 200)
        self.assertTrue(all(n['seen'] for n in member.call('/api/state')[1]['notifications']))
        # The actor is never notified about their own action.
        self.assertFalse(self.owner.call('/api/state')[1]['notifications'])


class MediaTests(Base):
    def test_range_requests(self):
        asset = self.upload()
        url = f'/file/{self.owner.org}/{asset}'
        status, body, headers = self.owner.call(url, extra={'HTTP_RANGE': 'bytes=0-9'})
        self.assertEqual((status, len(body)), (206, 10))
        self.assertEqual(headers['Content-Range'], f'bytes 0-9/{len(PNG)}')
        status, body, _ = self.owner.call(url, extra={'HTTP_RANGE': 'bytes=-4'})
        self.assertEqual((status, body), (206, PNG[-4:]))
        self.assertEqual(self.owner.call(url, extra={'HTTP_RANGE': 'bytes=9999-'})[0], 416)
        self.assertEqual(self.owner.call(url, extra={'HTTP_RANGE': 'nonsense'})[0], 416)

    def test_header_based_media_route(self):
        asset = self.upload()
        status, body, headers = self.owner.call(f'/media/{asset}')
        self.assertEqual((status, body), (200, PNG))
        self.assertEqual(headers['Content-Type'], 'image/png')
        self.assertEqual(self.owner.call('/media/does-not-exist')[0], 404)

    def test_file_route_requires_matching_org_in_url(self):
        asset = self.upload()
        self.assertEqual(self.owner.call(f'/file/wrong-org/{asset}')[0], 403)
        self.assertEqual(self.owner.call(f'/file/{self.owner.org}/missing')[0], 404)

    def test_asset_stays_visible_through_older_revisions(self):
        asset = self.upload()
        p = self.post(assets=[asset])
        p = self.act(
            p, 'edit', platform='instagram', format='Photo', caption='New', title='Title', assets=[]
        )[1]
        viewer = Client().invite(self.owner, self.roles['Viewer'])
        self.assertEqual(viewer.call(f'/file/{self.owner.org}/{asset}')[0], 200)

    def test_empty_upload_and_upload_permission(self):
        self.assertEqual(self.owner.call('/api/upload', raw=b'')[0] in (400, 413), True)
        viewer = Client().invite(self.owner, self.roles['Viewer'])
        self.assertEqual(viewer.call('/api/upload', raw=PNG)[0], 403)

    def test_upload_detects_formats_from_content(self):
        samples = {
            b'\xff\xd8\xff\xe0' + b'0' * 20: 'image/jpeg',
            b'GIF89a' + b'0' * 20: 'image/gif',
            b'RIFF\x00\x00\x00\x00WEBPVP8 ': 'image/webp',
            b'%PDF-1.7 test': 'application/pdf',
            b'\x00\x00\x00\x18ftypmp42' + b'0' * 20: 'video/mp4',
            b'\x00\x00\x00\x14ftypqt  ' + b'0' * 20: 'video/quicktime',
            b'\x1aE\xdf\xa3' + b'0' * 20: 'video/webm',
        }
        for data, mime in samples.items():
            status, result, _ = self.owner.call('/api/upload', raw=data)
            self.assertEqual((status, result.get('mime')), (201, mime))
        self.assertEqual(self.owner.call('/api/upload', raw=b'plain text, not media')[0], 400)


class PostLifecycleTests(Base):
    def test_title_only_edit_keeps_approval(self):
        self.single_stage_workflow()
        asset = self.upload()
        p = self.post(assets=[asset])
        p = self.act(p, 'submit')[1]
        p = self.act(p, 'decision', stage='final', action='approve')[1]
        self.assertEqual(p['status'], 'approved')
        edited = self.act(
            p,
            'edit',
            platform=p['platform'],
            format=p['format'],
            caption=p['caption'],
            title='Renamed',
            assets=[asset],
        )[1]
        self.assertEqual(edited['status'], 'approved')
        self.assertEqual(edited['version'], p['version'] + 1)
        self.assertTrue(all(s['done'] for s in edited['stages']))

    def test_archive_and_restore(self):
        p = self.post()
        p = self.act(p, 'archive')[1]
        self.assertEqual(p['status'], 'archived')
        self.assertEqual(
            self.act(p, 'edit', platform='instagram', format='Photo', caption='x', title='', assets=[])[0],
            409,
        )
        restored = self.act(p, 'archive')[1]
        self.assertEqual(restored['status'], 'draft')
        self.assertGreater(restored['version'], p['version'])

    def test_undo_latest_approval(self):
        self.single_stage_workflow()
        p = self.post(assets=[self.upload()])
        p = self.act(p, 'submit')[1]
        p = self.act(p, 'decision', stage='final', action='approve')[1]
        p = self.act(p, 'undo')[1]
        self.assertEqual(p['status'], 'review')
        self.assertFalse(any(s['done'] for s in p['stages']))
        self.assertEqual(self.act(p, 'undo')[0], 409)

    def test_reopening_a_task_after_approval_starts_a_new_version(self):
        p = self.post(assets=[self.upload()])
        p = self.act(p, 'task', title='Design', kind='Creative')[1]
        p = self.act(p, 'task-update', id=p['tasks'][0]['id'], status='done')[1]
        p = self.act(p, 'submit')[1]
        self.assertEqual(p['status'], 'review')
        reopened = self.act(p, 'task-update', id=p['tasks'][0]['id'], status='doing')[1]
        self.assertEqual(reopened['status'], 'changes')
        self.assertEqual(reopened['version'], p['version'] + 1)

    def test_override_requires_a_reason_and_published_posts_cannot_be_overridden(self):
        p = self.post(assets=[self.upload()])
        self.assertEqual(self.act(p, 'override', note='')[0], 400)
        historical = self.post(historical=True)
        self.assertEqual(historical['status'], 'published')
        self.assertEqual(self.act(historical, 'override', note='nope')[0], 409)

    def test_export_zip_contains_caption_record_and_ordered_media(self):
        asset = self.upload()
        p = self.post(assets=[asset], caption='Export me')
        p = self.act(p, 'override', note='Authority reviewed this directly')[1]
        status, data, headers = self.owner.call(f'/api/posts/{p["id"]}/export')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'application/zip')
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            self.assertEqual(z.read('caption.txt'), b'Export me')
            self.assertIn('media/01-pic.png', names)
            record = json.loads(z.read('review-record.json'))
            self.assertEqual(record['id'], p['id'])

    def test_invalid_decisions_and_reactions_are_rejected(self):
        self.single_stage_workflow()
        p = self.post(assets=[self.upload()])
        p = self.act(p, 'submit')[1]
        self.assertEqual(self.act(p, 'decision', stage='final', action='explode')[0], 400)
        self.assertEqual(self.act(p, 'decision', stage='final', action='changes', note='')[0], 400)
        self.assertEqual(self.act(p, 'reaction', emoji='💩')[0], 400)
        self.assertEqual(self.act(p, 'unknown-action')[0], 404)

    def test_submit_requires_media_for_media_formats(self):
        p = self.post(caption='Words only')
        status, result, _ = self.act(p, 'submit')
        self.assertEqual(status, 400)

    def test_pdf_format_requires_pdf_files(self):
        asset = self.upload()
        status, _, _ = self.owner.call(
            '/api/posts',
            {
                'company': self.company,
                'platform': 'linkedin',
                'format': 'PDF document',
                'caption': '',
                'title': '',
                'assets': [asset],
            },
        )
        self.assertEqual(status, 400)


class AdminTests(Base):
    def admin(self, action, body):
        return self.owner.call('/api/admin/' + action, body)

    def test_company_create_update_and_account_profile(self):
        self.assertEqual(self.admin('company', {'name': 'Second brand', 'color': '#abcdef'})[0], 200)
        companies = self.owner.call('/api/state')[1]['companies']
        second = [c for c in companies if c['name'] == 'Second brand'][0]
        self.assertEqual(
            self.admin('company', {'id': second['id'], 'name': 'Renamed', 'color': '#123456'})[0], 200
        )
        self.assertEqual(self.admin('company', {'name': 'Bad colour', 'color': 'red'})[0], 400)
        profile = {
            'company': second['id'],
            'platform': 'x',
            'name': 'Renamed X',
            'handle': '@renamed',
            'bio': 'Hello',
        }
        self.assertEqual(self.admin('account', profile)[0], 200)
        self.assertEqual(self.admin('account', {**profile, 'platform': 'myspace'})[0], 400)
        updated = [c for c in self.owner.call('/api/state')[1]['companies'] if c['id'] == second['id']][0]
        self.assertEqual(updated['name'], 'Renamed')
        self.assertEqual(updated['accounts']['x']['handle'], '@renamed')

    def test_new_companies_inherit_the_first_workflow(self):
        self.admin('company', {'name': 'Another'})
        companies = self.owner.call('/api/state')[1]['companies']
        first, other = companies[0], companies[-1]
        self.assertEqual([s['id'] for s in other['workflow']], [s['id'] for s in first['workflow']])

    def test_roles_can_be_created_edited_and_protected(self):
        status, _, _ = self.admin('role', {'name': 'Intern', 'permissions': ['create']})
        self.assertEqual(status, 200)
        roles = self.owner.call('/api/state')[1]['roles']
        intern = [r for r in roles if r['name'] == 'Intern'][0]
        self.assertEqual(
            self.admin('role', {'id': intern['id'], 'name': 'Junior', 'permissions': ['create', 'export']})[
                0
            ],
            200,
        )
        self.assertEqual(self.admin('role', {'name': 'Bad', 'permissions': ['fly']})[0], 400)
        admin_role = self.roles['Head of Brand & Client Experience']
        self.assertEqual(
            self.admin('role', {'id': admin_role, 'name': 'Demoted', 'permissions': ['create']})[0], 409
        )

    def test_members_can_be_updated_and_removed(self):
        member = Client().invite(self.owner, self.roles['Viewer'])
        listed = [
            m
            for m in self.owner.call('/api/state')[1]['members']
            if m['user'] != self.state['member']['user']
        ][0]
        update = {
            'id': listed['id'],
            'role': self.roles['Head of Creative'],
            'companies': [],
            'platforms': ['instagram'],
            'title': 'Lead',
            'department': 'Studio',
            'reports_to': self.state['member']['user'],
        }
        self.assertEqual(self.admin('member', update)[0], 200)
        refreshed = [m for m in self.owner.call('/api/state')[1]['members'] if m['id'] == listed['id']][0]
        self.assertEqual((refreshed['department'], refreshed['platforms']), ('Studio', ['instagram']))
        self.assertEqual(self.admin('remove-member', {'id': listed['id']})[0], 200)
        self.assertEqual(member.call('/api/state')[0], 403)
        self.assertEqual(self.admin('remove-member', {'id': self.state['member']['id']})[0], 409)

    def test_reporting_lines_cannot_form_a_cycle(self):
        Client().invite(self.owner, self.roles['Viewer'])
        Client().invite(self.owner, self.roles['Viewer'])
        members = [
            m
            for m in self.owner.call('/api/state')[1]['members']
            if m['user'] != self.state['member']['user']
        ]
        first, second = members[0], members[1]
        base = {'role': self.roles['Viewer'], 'companies': [], 'platforms': []}
        self.assertEqual(
            self.admin('member', {**base, 'id': first['id'], 'reports_to': second['user']})[0], 200
        )
        self.assertEqual(
            self.admin('member', {**base, 'id': second['id'], 'reports_to': first['user']})[0], 400
        )
        self.assertEqual(self.admin('member', {**base, 'id': second['id'], 'reports_to': 'ghost'})[0], 400)

    def test_admin_actions_need_manage_permission(self):
        creator = Client().invite(self.owner, self.roles['Creative Lead'])
        self.assertEqual(creator.call('/api/admin/company', {'name': 'Sneaky'})[0], 403)

    def test_restricted_admin_cannot_manage_roles_or_members(self):
        # A manager limited to one company is not an organisation-wide administrator.
        scoped_role = self.owner.call(
            '/api/admin/role', {'name': 'Scoped admin', 'permissions': ['manage', 'create']}
        )
        self.assertEqual(scoped_role[0], 200)
        roles = {r['name']: r['id'] for r in self.owner.call('/api/state')[1]['roles']}
        scoped = Client().invite(self.owner, roles['Scoped admin'], [self.company])
        self.assertEqual(scoped.call('/api/admin/role', {'name': 'X', 'permissions': []})[0], 403)
        self.assertEqual(
            scoped.call('/api/admin/invite', {'email': 'a@b.test', 'role': roles['Viewer']})[0], 403
        )

    def test_invitation_validation(self):
        self.assertEqual(
            self.admin('invite', {'email': 'not-an-email', 'role': self.roles['Viewer']})[0], 400
        )
        self.assertEqual(self.admin('invite', {'email': 'a@example.test', 'role': 'missing'})[0], 400)
        self.assertEqual(
            self.admin(
                'invite', {'email': 'a@example.test', 'role': self.roles['Viewer'], 'platforms': ['myspace']}
            )[0],
            400,
        )
        self.assertEqual(
            self.admin(
                'invite', {'email': 'a@example.test', 'role': self.roles['Viewer'], 'companies': ['nope']}
            )[0],
            400,
        )

    def test_invite_email_requires_configuration(self):
        body = {'email': 'mail@example.test', 'role': self.roles['Viewer'], 'send_email': True}
        self.assertEqual(self.admin('invite', body)[0], 409)

    def test_invite_link_is_single_use_and_existing_users_keep_their_password(self):
        other = Client().register('existing-' + uid())
        email = other.call('/api/me')[1]['user']['email']
        status, invite, _ = self.admin('invite', {'email': email, 'role': self.roles['Viewer']})
        self.assertEqual(status, 201)
        joiner = Client()
        wrong = {'email': email, 'password': 'another-long-password', 'name': 'x', 'token': invite['token']}
        self.assertEqual(joiner.call('/api/accept-invite', wrong)[0], 401)
        right = {**wrong, 'password': 'a-long-safe-password'}
        self.assertEqual(joiner.call('/api/accept-invite', right)[0], 200)
        self.assertEqual(Client().call('/api/accept-invite', right)[0], 400)
        organisations = joiner.call('/api/me')[1]['organisations']
        self.assertEqual(len(organisations), 2)

    def test_registration_rules(self):
        email = 'dupe-' + uid() + '@example.test'
        good = {'email': email, 'password': 'a-long-safe-password', 'name': 'Dupe', 'organisation': 'Dupes'}
        self.assertEqual(Client().call('/api/register', good)[0], 200)
        self.assertEqual(Client().call('/api/register', good)[0], 409)
        self.assertEqual(
            Client().call('/api/register', {**good, 'email': 'x' + email, 'password': 'short'})[0], 400
        )
        self.assertEqual(
            Client().call('/api/register', {**good, 'email': 'y' + email, 'organisation': ''})[0], 400
        )
        self.assertEqual(Client().call('/api/register', {**good, 'email': 'nope'})[0], 400)

    def test_workflow_validation(self):
        role = self.roles['Head of Creative']
        base = {'company': self.company}
        self.assertEqual(self.admin('workflow', {**base, 'stages': []})[0], 400)
        self.assertEqual(
            self.admin(
                'workflow', {**base, 'stages': [{'id': 'a', 'name': 'A', 'role': 'missing', 'depends': []}]}
            )[0],
            400,
        )
        no_review = self.roles['Viewer']
        self.assertEqual(
            self.admin(
                'workflow', {**base, 'stages': [{'id': 'a', 'name': 'A', 'role': no_review, 'depends': []}]}
            )[0],
            400,
        )
        dup = [{'id': 'a', 'name': 'A', 'role': role, 'depends': []}] * 2
        self.assertEqual(self.admin('workflow', {**base, 'stages': dup})[0], 400)
        bad_mode = [{'id': 'a', 'name': 'A', 'role': role, 'depends': [], 'mode': 'most'}]
        self.assertEqual(self.admin('workflow', {**base, 'stages': bad_mode})[0], 400)
        bad_dep = [{'id': 'a', 'name': 'A', 'role': role, 'depends': ['ghost']}]
        self.assertEqual(self.admin('workflow', {**base, 'stages': bad_dep})[0], 400)


if __name__ == '__main__':
    unittest.main()
