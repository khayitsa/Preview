# Feffel

A desktop-first social content planning and approval workspace. Built for Leah's team, with separate organisations so other businesses can use the same software.

**Start here:** run the application, create an organisation, configure your people and workflow, then add posts. The included `Feffel-preview.html` is an offline, read-only preview with fictional content. It includes a visible static layout for file viewers that disable scripts; interactive controls require a browser. the application itself starts with an empty database and real accounts.

## Run locally

Requires **Python 3.12 or later**. No JavaScript build or database installation is needed. The only
Python dependencies are Flask (and gunicorn for production).

```sh
cd feffel
python3 -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
# then: pip install -r requirements.txt && python app.py   (http://127.0.0.1:8000)
pip install -r requirements.txt
flask --app wsgi run --debug
```

Open **http://127.0.0.1:5000** (Flask's default port; add `--port 8000` to change it). Choose **Create an organisation**. There is no shared default password. Use a password of at least 12 characters.

The SQLite database and uploaded files are created in `data/`. They survive application restarts. They are deliberately excluded from this source package. Never place `data/` in a public web directory.

## First setup

1. Create the organisation (a group of companies, or a single business).
2. Open **Companies & team → Companies**. Add brands and configure each platform's display name, handle and bio.
3. Open **Custom roles**. The supplied job titles can be edited, and new roles created.
4. Open **People & access**. Invite each person by email, select their role and restrict their companies/platforms if needed. Empty scope checklists mean access to all. Add a department and reporting manager independently of review permissions.
5. Copy each invitation link to the intended teammate. It expires in seven days and can only be accepted by the specified email. Existing users enter their existing password when joining another organisation.
6. Open **Approval workflows**. Configure each company's review stages, parallel stages, dependencies, any/all reviewers and self-approval policy.
7. Create a post, choose its platform/format, add media in order and paste the caption. Save the draft. Open it to add creative and marketing tasks.
8. Complete tasks, then submit for review. Reviewers use their queue or the feed; final approvers see stages only when dependencies are complete.
9. Download the publishing pack after approval, then publish separately using the team's normal tools.

## Included behaviour

- **Organisations and companies:** independent customers, several companies per organisation, shared or restricted teams, custom roles, departments and reporting lines.
- **Platforms:** Instagram, Facebook, LinkedIn, X/Twitter, TikTok, YouTube, Pinterest and Threads. Platform-aware feed shells, content formats and media ratios.
- **Formats:** text, photos, image carousels, video, Stories, Reels/Shorts, community posts, image/video pins and LinkedIn PDF documents. Native browser media/PDF playback.
- **Previews:** scrolling feed, grid/profile view, chronological planning calendar, status/company/platform filters, caption search and a review queue across companies. Historical posts are manually entered and displayed alongside planned content.
- **Uploads:** JPG, PNG, GIF, WebP, MP4, MOV, WebM and PDF. Multi-file upload into a post, remove/reorder media, up to 35 files, 100 MB per file by default.
- **Approvals:** company-specific dependency graph, sequential or parallel stages, role-assigned reviewers, any/all requirement, self-approval switch, final override with a reason, stale-edit protection and 30-second undo of the latest approval.
- **Versioning:** caption/media/format changes reset approval, revisions retain their media, decisions reference versions, and resubmission after changes starts a new review round. Updating the internal title or planning date preserves approval.
- **Feedback:** comments/replies/resolution, image drawing, image pins, carousel slide references, video timestamps, PDF page references and selected-caption references. Informal reactions do not count as approval.
- **Collaboration:** parallel creative/marketing/legal tasks with assignees, notes and due dates; tasks must be complete before review. In-app notifications and optional SMTP outbox delivery.
- **Handover:** approved ZIP contains the caption, ordered media and complete review record. It does not schedule or publish.
- **Interface:** light/dark modes, keyboard focus, responsive desktop/mobile layouts and readable captions.

## Technical approach

- Frontend: vanilla JavaScript, HTML and CSS. No CDN, external fonts, tracking or frontend dependencies.
- Backend: Flask (application factory and blueprints) and SQLite. Runtime credentials and data are outside the source tree.
- Media: local private filesystem, with authenticated reads and byte-range video responses.
- Permissions: enforced by the backend on every post operation and media request. A member's organisation, company and platform scope is checked independently of their role.
- Login: scrypt passwords, random server-side sessions, HttpOnly/SameSite cookies, CSRF tokens, origin checks and login throttling. Set secure cookies and the canonical public URL when hosting behind HTTPS.
- SQLite uses WAL mode and explicit write transactions. This is intended for an initial team deployment on one server, with durable storage.

## Hosting handover

See **[docs/KEITH-HANDOVER.md](docs/KEITH-HANDOVER.md)** for Docker, direct Python hosting, environment variables, email delivery and backups. See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the data model and extension points.

## Verification

```sh
python3 -m unittest discover -s tests -v
npm run check        # syntax-check every file in feffel/static/js (needs Node)
```

Optional developer tooling (not needed to run or host the application): `pip install ruff` then
`ruff check . && ruff format .` for Python, and `npm run format` (Prettier) for the interface. See
`docs/ARCHITECTURE.md` for the code layout.

The integration suite uses real SQLite and the Flask application (through its test client) with isolated temporary data. It covers login, invitations, permission scopes, media access, workflows, version resets, feedback, tasks, notifications, concurrent edits and export gates. Browser UI inspection used a separate, read-only fictional fixture; the authenticated backend flow is tested by the integration suite rather than a browser login.

## Practical limits of this first version

- Social previews are approximations of platform layouts, not official social network interfaces. Real platforms may crop, truncate or display content differently. Social publishing limits are not fully enforced; check the final post in its destination application.
- There is one configured account per platform per company. To represent several accounts on the same platform, create separate brands/companies. Roles are assigned per organisation, with company/platform access scopes.
- Review chains are configured per company and captured at submission. A role's eligible reviewers are captured for that review round. If one leaves before an all-reviewer stage is complete, use final override or request changes and resubmit. There are no per-platform/per-post workflow overrides in this version.
- Drawing and pins work on images; videos use timestamp feedback, PDFs use a browser viewer and page references. PDFs are not rasterised into image slides. Caption selections are attached as quoted suggestions, not tracked replacement edits.
- Multiple files can be uploaded into one post. Spreadsheet imports, automatic creation of many posts from folders, bulk approval and automatic imports of published posts are not included.
- @Name can be written in comments; notifications go to other members with access to the post. There is no separate mention autocomplete/mention-only notification engine.
- Updates refresh every 45 seconds when no editor is open. This is not simultaneous document editing or live chat.
- Invitations can be copied immediately. Email notifications require SMTP and the outbox worker. Deadline reminders, password-reset emails and anonymous guest review links are not implemented. Password recovery is available through the local operator command.
- Signup creates separate organisations; subscription billing, organisation deletion, SSO, MFA, storage quotas and horizontally distributed hosting are outside this initial release.
- No automatic transcoding: video playback depends on the browser's codec support. Large uploads/exports are read into memory. For large teams or very large video libraries, extend media storage and pagination before scaling.

These limits are documented so G can assess the delivered implementation and Keith can host it on an appropriate server.


## Android app

`android/` contains a WebView shell that wraps a hosted copy of Feffel as an installable APK. See [docs/ANDROID.md](docs/ANDROID.md).
"# Preview" 
