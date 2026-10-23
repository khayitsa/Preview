'use strict';
// Administration: companies, team, roles, workflows and their dialogs.
function settingsPage() {
  return html`<h1 class="page-title">Make Feffel yours.</h1>
    <p class="intro">Your companies, your people, your way of working.</p>
    <div class="settings-tabs">
      ${[
        ['companies', 'Companies'],
        ['team', 'People & access'],
        ['roles', 'Custom roles'],
        ['workflow', 'Approval workflows'],
      ]
        .map(
          ([t, n]) =>
            html`<button
              data-action="settings-tab"
              data-tab="${t}"
              class="${S.settingsTab === t ? 'primary' : ''}"
            >
              ${n}
            </button>`,
        )
        .join('')}
    </div>
    ${S.settingsTab === 'companies'
      ? companySettings()
      : S.settingsTab === 'team'
        ? teamSettings()
        : S.settingsTab === 'roles'
          ? roleSettings()
          : workflowSettings()}`;
}
function companySettings() {
  return html`<div class="settings-grid">
    ${S.data.companies
      .map(
        c =>
          html`<div class="settings-card">
            <div class="row">
              <span class="avatar brand" style="background:${esc(c.color)}"
                >${esc(initials(c.name))}</span
              >
              <div class="grow">
                <h3>${esc(c.name)}</h3>
                <span class="tiny muted">@${esc(c.handle)}</span>
              </div>
              <button class="small" data-action="company-edit" data-id="${c.id}">Edit</button>
            </div>
            <p>Social account profiles are used in your private previews.</p>
            <div class="row wrap">
              ${Object.entries(names)
                .map(
                  ([p, n]) =>
                    html`<button
                      class="small"
                      data-action="account-edit"
                      data-company="${c.id}"
                      data-platform="${p}"
                      title="Edit ${n} profile"
                    >
                      ${icons[p]} ${n}
                    </button>`,
                )
                .join('')}
            </div>
          </div>`,
      )
      .join('')}
    <div class="settings-card" style="display:grid;place-items:center;min-height:180px">
      <button data-action="company-edit">＋ Add company / brand</button>
    </div>
  </div>`;
}
function scopeText(m) {
  return (
    (m.companies.length
      ? m.companies.map(id => company(id)?.name || 'Restricted company').join(', ')
      : 'All companies') +
    (m.platforms.length ? ' · ' + m.platforms.map(p => names[p]).join(', ') : '')
  );
}
function pendingInvites() {
  const invites = S.data.invites || [];
  if (!invites.length) return '';
  return html`<div class="settings-card">
    <h3>Pending invitations</h3>
    <p>
      Links can't be shown again once the dialog is closed. Revoke an invitation and send a new one
      if a link is lost.
    </p>
    <div style="overflow:auto">
      <table class="table">
        <thead>
          <tr>
            <th>Email</th>
            <th>Role</th>
            <th>Expires</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${invites
            .map(
              i =>
                html`<tr>
                  <td>${esc(i.email)}</td>
                  <td>${esc(role(i.role)?.name)}</td>
                  <td class="smalltext muted">${esc(dateLabel(i.expires * 1000))}</td>
                  <td>
                    <button class="small danger" data-action="invite-revoke" data-id="${i.id}">
                      Revoke
                    </button>
                  </td>
                </tr>`,
            )
            .join('')}
        </tbody>
      </table>
    </div>
  </div>`;
}
function teamSettings() {
  return html`<div class="settings-card">
      <div class="row spread">
        <div>
          <h3>One team. Many great ideas.</h3>
          <p>Job titles and access can be customised for each person.</p>
        </div>
        <button class="primary" data-action="invite">＋ Invite member</button>
      </div>
      <div style="overflow:auto">
        <table class="table">
          <thead>
            <tr>
              <th>Person</th>
              <th>Role</th>
              <th>Access</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${S.data.members
              .map(
                m =>
                  html`<tr>
                    <td>
                      <div class="row">
                        <span class="avatar">${esc(initials(m.name))}</span>
                        <div>
                          <strong>${esc(m.name)}</strong>
                          <div class="tiny muted" style="margin-top:4px">${esc(m.email)}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      ${esc(role(m.role)?.name)}${m.title
                        ? html`<div class="tiny muted">${esc(m.title)}</div>`
                        : ''}${m.department
                        ? html`<div class="tiny muted">
                            ${esc(m.department)}${m.reports_to
                              ? ' · Reports to ' + esc(memberName(m.reports_to))
                              : ''}
                          </div>`
                        : ''}
                    </td>
                    <td class="smalltext muted">${esc(scopeText(m))}</td>
                    <td>
                      <button class="small" data-action="member-edit" data-id="${m.id}">
                        Edit
                      </button>
                    </td>
                  </tr>`,
              )
              .join('')}
          </tbody>
        </table>
      </div>
    </div>
    ${pendingInvites()}
    <div class="notice">
      Invitation links are valid for seven days and are bound to the invited email. Copy and share
      each link with that person.
      ${S.data.email_available
        ? 'Email delivery is configured. You can also email invitations.'
        : 'Updates appear in-app. Ask your administrator to enable optional email delivery with SMTP settings.'}
    </div>`;
}
const permNames = {
  create: 'Create posts & edit own',
  edit_all: 'Edit all company posts',
  review: 'Review & approve assigned stages',
  manage: 'Manage companies, people & workflows',
  override: 'Final approval override',
  export: 'Download publishing packs',
  archive: 'Archive / restore posts',
};
function roleSettings() {
  return html`<div class="settings-card">
    <div class="row spread">
      <div>
        <h3>Roles that match real people.</h3>
        <p>Use your own job titles. Permissions determine what each role can do.</p>
      </div>
      <button class="primary" data-action="role-edit">＋ Create role</button>
    </div>
    <div style="overflow:auto">
      <table class="table">
        <thead>
          <tr>
            <th>Role</th>
            <th>Permissions</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${S.data.roles
            .map(
              r =>
                html`<tr>
                  <td><strong>${esc(r.name)}</strong></td>
                  <td>
                    <div class="row wrap">
                      ${r.permissions
                        .map(p => html`<span class="pill">${esc(p.replace('_', ' '))}</span>`)
                        .join('') || '<span class="muted">View and comment only</span>'}
                    </div>
                  </td>
                  <td>
                    <button class="small" data-action="role-edit" data-id="${r.id}">Edit</button>
                  </td>
                </tr>`,
            )
            .join('')}
        </tbody>
      </table>
    </div>
  </div>`;
}
function workflowSettings() {
  const c = company(S.workflowCompany) || S.data.companies[0];
  if (!c) return '';
  S.workflowCompany = c.id;
  S.workflowDraft = structuredClone(c.workflow);
  return html`<div class="settings-card">
    <h3>Good work takes its own route.</h3>
    <p>
      Stages without dependencies run in parallel. Add dependencies to require earlier approvals.
      Saved changes apply on the next submission; work already in review keeps its existing chain.
    </p>
    <label>Company</label
    ><select id="workflow-company" style="max-width:350px">
      ${S.data.companies
        .map(
          x =>
            html`<option value="${x.id}" ${x.id === c.id ? 'selected' : ''}>
              ${esc(x.name)}
            </option>`,
        )
        .join('')}
    </select>
    <div id="stages-editor">${stagesEditor()}</div>
    <div class="row">
      <button data-action="stage-add">＋ Add review stage</button><span class="grow"></span
      ><button class="primary" data-action="workflow-save">Save approval workflow</button>
    </div>
  </div>`;
}
function stagesEditor() {
  return S.workflowDraft
    .map(
      (s, i) =>
        html`<div class="stage-editor" data-stage-index="${i}">
          <div>
            <label>Stage name</label
            ><input class="stage-name" value="${esc(s.name)}" maxlength="100" />
          </div>
          <div>
            <label>Reviewer role</label
            ><select class="stage-role">
              ${S.data.roles
                .filter(r => r.permissions.includes('review'))
                .map(
                  r =>
                    html`<option value="${r.id}" ${s.role === r.id ? 'selected' : ''}>
                      ${esc(r.name)}
                    </option>`,
                )
                .join('')}
            </select>
          </div>
          <div>
            <label>Approval requirement</label
            ><select class="stage-mode">
              <option value="any" ${s.mode === 'any' ? 'selected' : ''}>
                Any eligible reviewer
              </option>
              <option value="all" ${s.mode === 'all' ? 'selected' : ''}>
                Every eligible reviewer
              </option>
            </select>
          </div>
          <div>
            <label>Self-approval</label
            ><select class="stage-self">
              <option value="yes" ${s.allow_self ? 'selected' : ''}>
                Allowed if they created the post
              </option>
              <option value="no" ${!s.allow_self ? 'selected' : ''}>
                A different person must review
              </option>
            </select>
          </div>
          <div class="full">
            <label>Must wait for</label>
            <div class="checklist">
              ${S.workflowDraft
                .filter(x => x.id !== s.id)
                .map(
                  d =>
                    html`<label
                      ><input
                        type="checkbox"
                        class="stage-dep"
                        value="${d.id}"
                        ${s.depends.includes(d.id) ? 'checked' : ''}
                      />
                      ${esc(d.name)}</label
                    >`,
                )
                .join('') || '<span class="tiny muted">No other stages yet.</span>'}
            </div>
          </div>
          <div class="full row spread">
            <span class="tiny muted"
              >${s.depends.length
                ? 'After its dependencies'
                : 'Runs in parallel with other independent stages'}</span
            ><button class="small danger" data-action="stage-remove" data-index="${i}">
              Remove stage
            </button>
          </div>
        </div>`,
    )
    .join('');
}
function readStages() {
  return $$('.stage-editor').map(el => {
    const s = S.workflowDraft[Number(el.dataset.stageIndex)];
    return {
      ...s,
      name: $('.stage-name', el).value,
      role: $('.stage-role', el).value,
      mode: $('.stage-mode', el).value,
      allow_self: $('.stage-self', el).value === 'yes',
      depends: $$('.stage-dep:checked', el).map(x => x.value),
    };
  });
}
function bindSettings() {
  if ($('#workflow-company'))
    $('#workflow-company').onchange = e => {
      S.workflowCompany = e.target.value;
      renderPage();
    };
}
function companyDialog(id) {
  const c = company(id);
  modal(
    c ? 'Edit company' : 'Add a company',
    html`<form id="company-form">
      <label>Company / brand name</label
      ><input name="name" required maxlength="150" value="${esc(c?.name || '')}" /><label
        >Default social handle</label
      ><input name="handle" maxlength="100" value="${esc(c?.handle || '')}" /><label
        >Brand colour</label
      ><input name="color" type="color" value="${c?.color || '#6b5ce7'}" />
    </form>`,
    html`<button data-action="close-modal">Cancel</button
      ><button class="primary" form="company-form" type="submit">Save company</button>`,
  );
  $('#company-form').onsubmit = async e => {
    e.preventDefault();
    await saveSettings('company', { ...Object.fromEntries(new FormData(e.target)), id });
  };
}
function accountDialog(cid, platform) {
  const c = company(cid),
    a = account(c, platform);
  modal(
    names[platform] + ' profile',
    html`<form id="account-form">
      <p class="intro">
        These details appear in your private preview. They do not change the real social account.
      </p>
      <label>Display name</label><input name="name" maxlength="150" value="${esc(a.name)}" /><label
        >Handle</label
      ><input name="handle" maxlength="100" value="${esc(a.handle)}" /><label
        >Bio / profile description</label
      ><textarea name="bio" maxlength="1000">${esc(a.bio)}</textarea>
    </form>`,
    html`<button data-action="close-modal">Cancel</button
      ><button class="primary" form="account-form" type="submit">Save profile</button>`,
  );
  $('#account-form').onsubmit = async e => {
    e.preventDefault();
    await saveSettings('account', {
      ...Object.fromEntries(new FormData(e.target)),
      company: cid,
      platform,
    });
  };
}
function memberDialog(id) {
  const m = S.data.members.find(x => x.id === id);
  modal(
    m ? 'Edit member access' : 'Invite a teammate',
    html`<form id="member-form">
      ${!m
        ? '<label>Work email</label><input name="email" type="email" required>'
        : html`<div class="notice">${esc(m.name)} · ${esc(m.email)}</div>`}<label>Role</label
      ><select name="role">
        ${S.data.roles
          .map(
            r =>
              html`<option value="${r.id}" ${m?.role === r.id ? 'selected' : ''}>
                ${esc(r.name)}
              </option>`,
          )
          .join('')}</select
      ><label>Job title / department (optional)</label
      ><input name="title" maxlength="150" value="${esc(m?.title || '')}" />
      <div class="form-grid">
        <div>
          <label>Department</label
          ><input
            name="department"
            maxlength="100"
            value="${esc(m?.department || '')}"
            placeholder="e.g. Creative"
          />
        </div>
        <div>
          <label>Reports to</label
          ><select name="reports_to">
            <option value="">No reporting manager</option>
            ${S.data.members
              .filter(x => x.user !== m?.user)
              .map(
                x =>
                  html`<option value="${x.user}" ${m?.reports_to === x.user ? 'selected' : ''}>
                    ${esc(x.name)}
                  </option>`,
              )
              .join('')}
          </select>
        </div>
      </div>
      <label>Company access</label>
      <div class="required-note">Leave all unchecked to grant access to every company.</div>
      <div class="checklist">
        ${S.data.companies
          .map(
            c =>
              html`<label
                ><input
                  type="checkbox"
                  name="companies"
                  value="${c.id}"
                  ${m?.companies.includes(c.id) ? 'checked' : ''}
                />
                ${esc(c.name)}</label
              >`,
          )
          .join('')}
      </div>
      <label>Platform access</label>
      <div class="required-note">Leave all unchecked to grant access to every platform.</div>
      <div class="checklist">
        ${Object.entries(names)
          .map(
            ([p, n]) =>
              html`<label
                ><input
                  type="checkbox"
                  name="platforms"
                  value="${p}"
                  ${m?.platforms.includes(p) ? 'checked' : ''}
                />
                ${n}</label
              >`,
          )
          .join('')}
      </div>
      ${!m && S.data.email_available
        ? '<label class="row"><input name="send_email" type="checkbox"> Email this invitation</label>'
        : ''}
    </form>`,
    `${m ? html`<button class="danger" data-action="member-remove" data-id="${m.id}">Remove access</button><span class="grow"></span>` : ''}<button data-action="close-modal">Cancel</button><button class="primary" form="member-form" type="submit">${m ? 'Save access' : 'Create invitation link'}</button>`,
  );
  $('#member-form').onsubmit = async e => {
    e.preventDefault();
    const f = new FormData(e.target);
    const b = {
      ...Object.fromEntries(f),
      companies: f.getAll('companies'),
      platforms: f.getAll('platforms'),
      send_email: !!f.get('send_email'),
      id,
    };
    try {
      const r = await api('/api/admin/' + (m ? 'member' : 'invite'), b);
      await load();
      if (m) {
        closeModal();
        toast('Member access updated.');
      } else {
        const link = new URL(r.link || '/?invite=' + r.token, location.origin).href;
        modal(
          'Your invitation is ready',
          html`<p class="intro">
              Share this link with <strong>${esc(r.email)}</strong>. It expires in seven days.
            </p>
            <label>Invitation link</label
            ><input id="invite-link" readonly value="${esc(link)}" /><button
              style="margin-top:12px"
              data-action="copy-invite"
            >
              Copy invitation link
            </button>
            <p class="smalltext muted">
              Only the invited email address can accept it.
              ${b.send_email
                ? 'An invitation email has been queued for delivery.'
                : 'No email has been sent automatically.'}
            </p>`,
        );
      }
    } catch (err) {
      toast(err.message);
    }
  };
}
function roleDialog(id) {
  const r = role(id);
  modal(
    r ? 'Edit role' : 'Create custom role',
    html`<form id="role-form">
      <label>Role name</label
      ><input name="name" maxlength="100" required value="${esc(r?.name || '')}" /><label
        >Permissions</label
      >
      <div class="checklist" style="display:grid">
        ${Object.entries(permNames)
          .map(
            ([p, n]) =>
              html`<label
                ><input
                  type="checkbox"
                  name="permissions"
                  value="${p}"
                  ${r?.permissions.includes(p) ? 'checked' : ''}
                />
                ${n}</label
              >`,
          )
          .join('')}
      </div>
      <p class="smalltext muted">
        Everyone with access can view, react and comment. Approval additionally requires assignment
        to a workflow stage.
      </p>
    </form>`,
    html`<button data-action="close-modal">Cancel</button
      ><button class="primary" form="role-form" type="submit">Save role</button>`,
  );
  $('#role-form').onsubmit = async e => {
    e.preventDefault();
    const f = new FormData(e.target);
    await saveSettings('role', { id, name: f.get('name'), permissions: f.getAll('permissions') });
  };
}
async function saveSettings(action, b) {
  try {
    await api('/api/admin/' + action, b);
    closeModal();
    await load();
    toast('Settings saved.');
  } catch (e) {
    toast(e.message);
  }
}
