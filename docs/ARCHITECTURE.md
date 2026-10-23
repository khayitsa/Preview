# Feffel — implementation map

## Layout

```
wsgi.py              WSGI entry (`wsgi:application`, also read by `flask --app wsgi`)
feffel/              The Flask application package
  __init__.py        create_app(): config, database, hooks, blueprints, CLI
  config.py          Deployment settings from FEFFEL_* environment variables
  constants.py       Platforms, permissions, default roles and other fixed vocabulary
  db.py, schema.py   get_db() (one connection per request), table definitions, migrations
  guards.py          @signed_in, @org_member, json_body(), require_permission()
  sessions.py        Server-side sessions (cookie holds a random token, DB holds its hash)
  hooks.py           Same-origin check, security headers, JSON error handlers
  access.py          Permissions, company/platform scope, "last administrator" rules
  workflow.py        Workflow validation and stage_state() (the review engine)
  posts.py           Post serialisation, revisions, media/format validation
  notifications.py   Audit trail, in-app notifications, email outbox
  security.py, util.py, errors.py   Password hashing, small helpers, Error/require()
  cli.py             `flask backup`, `flask reset-password`, `flask send-mail`
  api/               One blueprint per area: site, auth, workspace, files, posts, admin
  templates/         index.html (the single-page shell; lists scripts and styles in load order)
  static/            Interface: js/ and css/ (no build step, no dependencies)
tests/
  test_app.py              Integration tests (real SQLite, Flask test client)
  test_admin_and_edges.py  Admin settings, media ranges, exports, error handling
  browser-fixture/         Fictional data used to build Feffel-preview.html
tools/build-preview.mjs    Builds the offline preview from the files listed in the template
docs/                Hosting and architecture notes
```

### Request flow

1. `before_request` (`hooks.py`): same-origin check for anything that changes data.
2. Flask routes the request to a view in one of the blueprints in `feffel/api/`.
3. Views that need a user are wrapped in `@signed_in` (session cookie + CSRF token for mutations)
   or `@org_member` (also resolves `X-Org-ID`, or the `<org_id>` in `/file/<org_id>/<asset_id>`,
   to a membership and loads `g.org`, `g.member`, `g.perms`, `g.user`).
4. Views read `request`, use `get_db()` and return a dict (JSON), or `(body, status, headers)`.
   Raise `Error(status, message)` for anything the user should see.
5. `after_request` adds the security headers. `teardown_appcontext` rolls back and closes the
   database connection.

Sign-in uses Feffel's own server-side sessions rather than Flask's signed-cookie `session`, so a
session can be revoked from the database.

### Frontend

The interface is plain scripts sharing one global scope, loaded in the order given in
`feffel/templates/index.html` (state and helpers in `core.js`, then one file per area, `main.js` last).
There is deliberately no bundler. Run `npm run format` after editing, `npm run check` for syntax
and `npm run preview` to rebuild `Feffel-preview.html`.

HTML is written with the `html` tagged template (defined in `core.js`). It behaves exactly like an
ordinary template literal but lets editors and Prettier format the markup. Always wrap untrusted
values in `esc(...)`.

## Organisation model

Users have global email identities and can belong to multiple independent organisations. Each organisation owns roles, memberships, companies, assets and posts. A member has one organisation-level role, optional company/platform restrictions, a department and a reporting manager. Empty restriction lists mean all companies/platforms. Reporting lines do not grant permissions.

The frontend sends the selected organisation ID as `X-Org-ID`; the server verifies membership. Media elements cannot attach custom headers, so `/file/<organisation>/<asset>` uses the URL only as an organisation selector and performs the same session/membership/scope checks. An asset ID alone never grants access.

## Review model

Company workflows are arrays of stages:

```json
[
  {"id":"creative","name":"Creative review","role":"ROLE_ID","depends":[],"mode":"any","allow_self":true},
  {"id":"marketing","name":"Marketing review","role":"ROLE_ID","depends":[],"mode":"any","allow_self":true},
  {"id":"brand","name":"Final brand approval","role":"ROLE_ID","depends":["creative","marketing"],"mode":"any","allow_self":true}
]
```

Stages without dependencies can proceed in parallel. Dependencies must refer to valid stages and cannot contain a cycle. The role must have review permission. On submission, the workflow and its eligible reviewer IDs are captured on the post. Eligibility considers membership, role, company scope, platform scope and self-approval policy. This preserves past decisions if a person's role later changes. A removed member cannot access the post or make new decisions.

All tasks must be complete before submission. Normal stage approval is allowed only for eligible reviewers when dependencies are satisfied. Every stage must complete for `approved`. A final override can approve a current version directly and requires a reason; it remains separate in the audit trail.

States: `draft → review → approved`; a reviewer can return `changes` or `rejected`. Resubmitting either starts a new version/review round. Historical posts use `published` and bypass review because they represent already-public content. `archived` is recoverable; restoration creates a fresh draft version.

Caption, format, platform or media edits create a revision and reset approvals on reviewed content. Title/date-only edits copy decisions to the new revision. Every edit has an optimistic `lock` counter to reject concurrent stale changes. Comments are independent of that lock and stay attached to a specific content version.

## Feedback model

Comments contain a body, optional parent and a JSON context object. Supported context fields are `asset_index`, `strokes`, `pin`, `selected_text`, `time` and `pdf_page`. Drawing strokes use normalised coordinates and colour; resizing preserves positioning on the media viewport. The saved viewport includes letterboxing, so the drawing aligns with the same displayed image. Image editing/replacement creates a new version; annotations remain on the original.

Resolved comments remain in the record. Reactions are stored separately from decisions and never grant approval. In-app notifications are created for other members who can access the post; SMTP copies are queued only when configured.

## API conventions

- JSON API, same origin, cookie session.
- `GET /api/me` returns user identity and CSRF token, or a signed-out result.
- Authenticated mutations require `X-CSRF-Token` and `X-Org-ID`.
- `POST /api/register`, `/api/login`, `/api/accept-invite` handle account flows.
- `GET /api/state` returns scoped companies/posts and organisation directory metadata.
- `POST /api/upload` accepts one raw binary file plus encoded `X-File-Name`.
- `POST /api/posts` creates a draft or historical post.
- `GET /api/posts/<id>` includes full revisions, comments, tasks and decisions.
- `POST /api/posts/<id>/{edit,submit,decision,undo,override,archive}` updates versioned state and requires `lock`.
- `POST /api/posts/<id>/{comment,resolve,reaction,task,task-update}` handles collaboration.
- `GET /api/posts/<id>/export` requires export permission and approved/published status.
- `POST /api/admin/{company,account,role,member,invite,workflow,remove-member}` handles organisation settings.
- `GET /file/<org>/<asset>` authorises media and supports byte ranges.

Responses use JSON errors with HTTP status codes. Version conflicts return 409. Authenticated and media responses are not cached by shared proxies.

## Extension points

- Add platforms/formats to `PLATFORMS` in `feffel/config.py`, then add the corresponding labels/shell rendering in `feffel/static/js/core.js` and `feffel/static/js/workspace.js`.
- Add per-account or per-post workflow overrides through an explicit schema/API extension; current submission selects the company default.
- Add platform publishing adapters only after approved-content export; do not let a publishing integration bypass the version-specific review state.
- Replace local media with authenticated object storage and replace full-file memory reads with streaming for larger libraries.
- Replace state-wide loading with pagination and event updates for large organisations.
- Migrate SQLite to PostgreSQL before distributed/multi-region hosting. User and organisation IDs are opaque random strings and can be preserved.
- Add dedicated notification preferences, mention targets, deadline scheduling and self-service password recovery as later features.

No analytics, scheduling/publishing integration, third-party account credentials or payment processing is included.
