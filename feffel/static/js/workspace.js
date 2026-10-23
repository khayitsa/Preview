'use strict';
// Main workspace: filters, feed, profile grid, calendar and post cards.
function filteredPosts() {
  let posts = S.data.posts.filter(
    p =>
      (S.company === 'all' || p.company === S.company) &&
      (S.status === 'all' ? p.status !== 'archived' : p.status === S.status),
  );
  if (S.nav === 'queue') posts = posts.filter(p => p.stages.some(s => s.can_approve));
  else if (S.nav === 'approved') posts = posts.filter(p => p.status === 'approved');
  else if (S.nav === 'tasks')
    posts = posts.filter(p =>
      p.tasks.some(t => t.status !== 'done' && t.assignee === S.me.user.id),
    );
  if (S.platform !== 'all') posts = posts.filter(p => p.platform === S.platform);
  const search = S.search.toLowerCase();
  if (search)
    posts = posts.filter(p =>
      [p.title, p.caption, company(p.company)?.name, p.creator_name]
        .join(' ')
        .toLowerCase()
        .includes(search),
    );
  return posts.sort((a, b) => (b.scheduled || b.created).localeCompare(a.scheduled || a.created));
}
function render() {
  const d = S.data;
  const orgname = S.me.organisations.find(o => o.org === S.org)?.name || 'Workspace';
  const pending = d.posts.filter(p => p.stages.some(s => s.can_approve)).length;
  const unread = d.notifications.filter(n => !n.seen).length;
  $('#app').innerHTML = html`<div class="app-layout">
    <aside class="sidebar">
      <div class="row">
        <span class="logoicon">f</span><span class="brandword">feffel<i>.</i></span>
      </div>
      <div class="workspace">
        <div class="tiny muted" style="margin-bottom:8px">YOUR ORGANISATION</div>
        <select id="org-select" aria-label="Organisation">
          ${S.me.organisations
            .map(
              o =>
                html`<option value="${o.org}" ${o.org === S.org ? 'selected' : ''}>
                  ${esc(o.name)}
                </option>`,
            )
            .join('')}
        </select>
      </div>
      <div class="nav-label">Workspace</div>
      ${[
        ['workspace', '▦', 'Content studio'],
        ['queue', '✓', 'My review queue'],
        ['tasks', '☷', 'My tasks'],
        ['approved', '↗', 'Ready to publish'],
      ]
        .map(
          ([n, i, t]) =>
            html`<button
              class="nav-button ${S.nav === n ? 'active' : ''}"
              data-action="nav"
              data-nav="${n}"
              title="${t}"
            >
              <span class="nav-icon">${i}</span><span>${t}</span>${n === 'queue' && pending
                ? html`<span class="count">${pending}</span>`
                : ''}
            </button>`,
        )
        .join('')}
      <div style="height:20px"></div>
      <div class="nav-label">Organisation</div>
      ${has('manage')
        ? html`<button
            class="nav-button ${S.nav === 'settings' ? 'active' : ''}"
            data-action="nav"
            data-nav="settings"
            title="Companies and team"
          >
            <span class="nav-icon">⚙</span><span>Companies & team</span>
          </button>`
        : ''}<button class="nav-button" data-action="notifications" title="Notifications">
        <span class="nav-icon">♧</span><span>Notifications</span>${unread
          ? html`<span class="count">${unread}</span>`
          : ''}
      </button>
      <div class="sidebar-bottom">
        <div class="row">
          <span class="avatar">${esc(initials(S.me.user.name))}</span>
          <div class="user-details grow">
            <strong class="smalltext">${esc(S.me.user.name)}</strong>
            <div class="tiny muted" style="margin-top:4px">${esc(role(d.member.role)?.name)}</div>
          </div>
          <button class="ghost small" data-action="logout" title="Sign out">↪</button>
        </div>
      </div>
    </aside>
    <main class="main">
      <header class="topbar">
        <div class="breadcrumb">
          ${esc(orgname)} <span style="margin:0 10px">/</span>
          <strong>${{
            settings: 'Organisation settings',
            queue: 'My review queue',
            tasks: 'My tasks',
            approved: 'Ready to publish',
          }[S.nav] || 'Content workspace'}</strong>
        </div>
        <div class="row">
          <input
            class="search"
            id="search"
            aria-label="Search content"
            placeholder="⌕  Search posts, captions…"
            value="${esc(S.search)}"
          /><button class="ghost" data-action="theme" title="Toggle colour theme">
            ${S.theme === 'dark' ? '☀' : '☾'}</button
          >${has('create')
            ? '<button class="primary" data-action="new-post">＋ Create post</button>'
            : ''}
        </div>
      </header>
      <div class="page" id="page">${S.nav === 'settings' ? settingsPage() : workspacePage()}</div>
    </main>
  </div>`;
  $('#org-select').onchange = async e => {
    S.org = e.target.value;
    S.company = 'all';
    preferences.setItem('feffel-org', S.org);
    closeModal();
    await load();
  };
  $('#search').oninput = e => {
    S.search = e.target.value;
    renderPage();
  };
  bindPage();
}
function workspacePage() {
  const title = {
    workspace: 'A little less back-and-forth.',
    queue: 'Your eye. Your approval.',
    tasks: 'Move good work forward.',
    approved: 'Good to go.',
  }[S.nav];
  const sub = {
    workspace: 'Plan the feed. Fine-tune the details. Make good work happen together.',
    queue: 'Everything waiting for your review, across your companies.',
    tasks: 'Creative and marketing can work together, at their own pace.',
    approved: 'Approved content, ready for your team to publish.',
  }[S.nav];
  const posts = filteredPosts();
  // Counters describe the current view (queue, tasks, ready to publish), not the whole workspace.
  const inView = {
    queue: p => p.stages.some(s => s.can_approve),
    tasks: p => p.tasks.some(t => t.status !== 'done' && t.assignee === S.me.user.id),
    approved: p => p.status === 'approved',
  }[S.nav];
  const all = S.data.posts.filter(
    p => (S.company === 'all' || p.company === S.company) && (!inView || inView(p)),
  );
  return html`<div class="row spread">
      <div>
        <h1 class="page-title">${title}</h1>
        <p class="intro">${sub}</p>
      </div>
      <span class="pill">✦ Content workspace</span>
    </div>
    <div class="metrics">
      ${[
        ['Total posts', all.filter(p => p.status !== 'archived').length, '▦'],
        ['In review', all.filter(p => p.status === 'review').length, '◷'],
        ['Approved', all.filter(p => p.status === 'approved').length, '✓'],
        ['Needs changes', all.filter(p => p.status === 'changes').length, '↺'],
      ]
        .map(
          ([t, n, i]) =>
            html`<div class="metric">
              <div><small>${t}</small><strong>${n.toString().padStart(2, '0')}</strong></div>
              <div class="metric-dot">${i}</div>
            </div>`,
        )
        .join('')}
    </div>
    <div class="controls">
      <select id="company-filter" aria-label="Company">
        <option value="all">All companies</option>
        ${S.data.companies
          .map(
            c =>
              html`<option value="${c.id}" ${S.company === c.id ? 'selected' : ''}>
                ${esc(c.name)}
              </option>`,
          )
          .join('')}</select
      ><select id="status-filter" aria-label="Status">
        <option value="all">All statuses</option>
        ${Object.entries(labels)
          .map(
            ([k, v]) =>
              html`<option value="${k}" ${S.status === k ? 'selected' : ''}>${v}</option>`,
          )
          .join('')}
      </select>
      <div class="view-tabs">
        ${[
          ['feed', '▤ Feed'],
          ['grid', '▦ Grid / profile'],
          ['calendar', '▦ Calendar'],
        ]
          .map(
            ([v, t]) =>
              html`<button
                data-action="view"
                data-view="${v}"
                class="${S.view === v ? 'active' : ''}"
              >
                ${t}
              </button>`,
          )
          .join('')}
      </div>
    </div>
    <div class="platform-tabs">
      ${[['all', 'All platforms'], ...Object.entries(names)]
        .map(
          ([p, n]) =>
            html`<button
              class="platform-tab ${S.platform === p ? 'active' : ''}"
              data-action="platform"
              data-platform="${p}"
              title="${n}"
            >
              <span
                class="platform-symbol"
                style="color:${p === 'instagram'
                  ? '#c65398'
                  : p === 'facebook'
                    ? '#3977dc'
                    : p === 'linkedin'
                      ? '#2874a1'
                      : p === 'youtube'
                        ? '#e85858'
                        : p === 'pinterest'
                          ? '#bd3b4e'
                          : 'inherit'}"
                >${icons[p] || '◉'}</span
              ><span>${n}</span>
            </button>`,
        )
        .join('')}
    </div>
    ${S.view === 'calendar'
      ? calendarView(posts)
      : S.view === 'grid'
        ? gridView(posts)
        : feedView(posts)}`;
}
function renderPage() {
  const page = $('#page');
  if (page) {
    page.innerHTML = S.nav === 'settings' ? settingsPage() : workspacePage();
    bindPage();
  }
}
function bindPage() {
  const c = $('#company-filter');
  if (c)
    c.onchange = e => {
      S.company = e.target.value;
      renderPage();
    };
  const s = $('#status-filter');
  if (s)
    s.onchange = e => {
      S.status = e.target.value;
      renderPage();
    };
  bindSettings();
}
function empty(
  message = 'Your feed starts here.',
  body = 'Upload a post, add its caption and bring your team into the conversation. Everything stays private until your team publishes it separately.',
) {
  return html`<div class="empty-state">
    <div class="empty-icon">▦</div>
    <h2>${message}</h2>
    <p>${body}</p>
    ${has('create')
      ? '<button class="primary" data-action="new-post">＋ Create your first post</button>'
      : ''}${has('manage')
      ? '<button class="ghost" data-action="nav" data-nav="settings">Set up your team →</button>'
      : ''}
  </div>`;
}
function feedView(posts) {
  if (!posts.length)
    return empty(
      S.nav === 'queue'
        ? 'You’re all caught up.'
        : S.nav === 'approved'
          ? 'Nothing ready to publish yet.'
          : S.search || S.status !== 'all'
            ? 'No posts match these filters.'
            : 'Your feed starts here.',
      S.nav === 'queue'
        ? 'Posts will appear here when your stage of review is ready.'
        : 'Create posts for this platform, or switch companies and filters to explore your content.',
    );
  const c = company(S.company) || company(posts[0].company);
  const wf = c?.workflow || [];
  return html`<div class="feed-layout">
    <div class="feed">${posts.map(p => postCard(p)).join('')}</div>
    <aside class="feed-aside">
      <div class="aside-card">
        <div class="row">
          <span class="avatar brand" style="background:${esc(c?.color)}"
            >${esc(initials(c?.name))}</span
          >
          <div>
            <strong class="smalltext">${esc(c?.name)}</strong>
            <div class="tiny muted" style="margin-top:4px">
              ${S.platform === 'all' ? 'All social accounts' : esc(names[S.platform])}
            </div>
          </div>
        </div>
        <hr style="border:0;border-top:1px solid var(--line);margin:20px 0" />
        <h3>Your approval flow</h3>
        ${wf
          .map(
            (s, i) =>
              html`<div class="progress-line">
                <span class="node">${i + 1}</span>
                <div>
                  <p>${esc(s.name)}</p>
                  <small
                    >${esc(role(s.role)?.name)}<br />${s.depends.length
                      ? 'After ' +
                        s.depends.map(d => esc(wf.find(x => x.id === d)?.name)).join(' + ')
                      : 'Can review in parallel'}</small
                  >
                </div>
              </div>`,
          )
          .join('')}
      </div>
      <div class="aside-card tip">
        <h3>✦ Less clicking. More clarity.</h3>
        <p>
          Double-click a post’s image to approve your next available stage. Use feedback to point,
          draw or suggest a change.
        </p>
        <div class="tiny muted">Reactions are informal. ✅ records approval.</div>
      </div>
      <div class="aside-card">
        <h3>Working together</h3>
        <div class="row wrap">
          ${S.data.members
            .slice(0, 7)
            .map(
              m =>
                html`<span class="avatar" title="${esc(m.name)} · ${esc(role(m.role)?.name)}"
                  >${esc(initials(m.name))}</span
                >`,
            )
            .join('')}
        </div>
        <p class="smalltext muted" style="line-height:1.7;margin-bottom:0">
          ${S.data.members.length} team member${S.data.members.length === 1 ? '' : 's'} ·
          ${S.data.companies.length} compan${S.data.companies.length === 1 ? 'y' : 'ies'}
        </p>
      </div>
    </aside>
  </div>`;
}
function mediaMarkup(p, scope = 'feed') {
  const a = p.assets || [];
  if (!a.length) return '';
  const key = scope + ':' + p.id;
  const index = Math.min(S.slides[key] || 0, a.length - 1);
  const asset = a[index];
  const klass = asset.mime.startsWith('video')
    ? p.format === 'Reel' || p.format === 'Short' || p.platform === 'tiktok'
      ? 'short'
      : 'video'
    : asset.mime === 'application/pdf'
      ? 'pdf'
      : p.format === 'Story'
        ? 'story'
        : p.platform === 'instagram'
          ? 'portrait'
          : '';
  const media = asset.mime.startsWith('image')
    ? html`<img
        src="${assetUrl(asset)}"
        alt="${esc(p.title || 'Post media')} — slide ${index + 1}"
        loading="lazy"
        draggable="false"
      />`
    : asset.mime.startsWith('video')
      ? html`<video
          controls
          preload="metadata"
          playsinline
          src="${assetUrl(asset)}"
          aria-label="${esc(asset.name)}"
        ></video>`
      : html`<iframe
          title="${esc(asset.name)}"
          src="${assetUrl(asset)}#page=${S.pdfPage || 1}&toolbar=1"
        ></iframe>`;
  return html`<div class="media ${klass}" data-post-media="${p.id}" data-scope="${scope}">
      ${a.length > 1
        ? html`<span class="slide-counter">${index + 1} / ${a.length}</span>`
        : ''}${media}${a.length > 1
        ? html`<div class="slide-controls">
            <button
              data-action="slide"
              data-id="${p.id}"
              data-scope="${scope}"
              data-delta="-1"
              aria-label="Previous slide"
            >
              ‹</button
            ><button
              data-action="slide"
              data-id="${p.id}"
              data-scope="${scope}"
              data-delta="1"
              aria-label="Next slide"
            >
              ›
            </button>
          </div>`
        : ''}
    </div>
    ${a.length > 1
      ? html`<div class="dots">
          ${a.map((_, i) => html`<span class="${i === index ? 'on' : ''}"></span>`).join('')}
        </div>`
      : ''}`;
}
function postCard(p) {
  const c = company(p.company),
    a = account(c, p.platform);
  const textFirst = ['linkedin', 'x', 'threads', 'facebook'].includes(p.platform);
  const eligible = p.stages.filter(s => s.can_approve);
  const react = p.reactions.find(r => r.user === S.me.user.id)?.emoji;
  return html`<article class="post platform-${p.platform}" id="post-${p.id}">
    <div class="platform-strip">
      <span
        >${esc(c?.name)} ·
        ${esc(p.format)}${p.scheduled ? ' · ' + esc(dateLabel(p.scheduled)) : ''}</span
      >${badge(p)}
    </div>
    <div class="post-head">
      <span class="avatar brand" style="background:${esc(c?.color)}">${esc(initials(a.name))}</span>
      <div>
        <strong
          >${esc(['instagram', 'x', 'threads'].includes(p.platform) ? a.handle : a.name)}</strong
        >
        <div class="meta">
          ${p.platform === 'linkedin' ? 'Company · ' : ''}${p.historical
            ? 'Published content'
            : esc(p.creator_name) + ' · v' + p.version}${p.platform === 'x'
            ? ' · @' + esc(a.handle)
            : ''}
        </div>
      </div>
      <button class="more ghost" data-action="review" data-id="${p.id}" aria-label="Open post">
        ⋯
      </button>
    </div>
    ${textFirst ? html`<div class="caption text-first">${esc(p.caption)}</div>` : ''}${mediaMarkup(
      p,
    )}${p.platform === 'instagram'
      ? '<div class="social-actions"><span>♡</span><span>♧</span><span>➤</span><span>♧</span></div>'
      : ''}${!textFirst
      ? html`<div class="caption">
          ${p.platform === 'instagram'
            ? html`<strong>${esc(a.handle)}</strong>`
            : p.platform === 'youtube'
              ? html`<strong>${esc(p.title)}</strong> `
              : ''}${esc(p.caption)}
        </div>`
      : ''}${['linkedin', 'facebook'].includes(p.platform)
      ? '<div class="row muted smalltext" style="padding:10px 18px;border-top:1px solid var(--line);justify-content:space-around"><span>♡ Like</span><span>♧ Comment</span><span>↗ Share</span></div>'
      : ''}
    <div class="post-footer">
      <div class="row wrap">
        ${eligible.length
          ? html`<button class="approve" data-action="quick-approve" data-id="${p.id}">
              ✓ Approve${eligible.length > 1 ? ' stage' : ''}
            </button>`
          : ''}<button class="feedback" data-action="review" data-id="${p.id}">
          ✎ Feedback${p.comments_count ? ' · ' + p.comments_count : ''}</button
        >${['draft', 'changes', 'rejected'].includes(p.status) &&
        (has('edit_all') || (p.creator === S.me.user.id && has('create')))
          ? html`<button class="ghost" data-action="edit-post" data-id="${p.id}">Edit</button>`
          : ''}
        <div class="grow"></div>
        ${['❤️', '👍', '💡']
          .map(
            e =>
              html`<button
                class="reaction ${react === e ? 'active' : ''}"
                data-action="reaction"
                data-id="${p.id}"
                data-emoji="${e}"
                title="Informal reaction: ${e}"
              >
                ${e}
              </button>`,
          )
          .join('')}
      </div>
      <div class="row spread tiny muted" style="margin-top:10px">
        <span
          >${p.stages.filter(s => s.done).length}/${p.stages.length} review stages
          complete${p.tasks.length
            ? ' · ' +
              p.tasks.filter(t => t.status === 'done').length +
              '/' +
              p.tasks.length +
              ' tasks done'
            : ''}</span
        ><button class="ghost small" data-action="review" data-id="${p.id}">Open post ↗</button>
      </div>
    </div>
  </article>`;
}
function gridView(posts) {
  const c = company(S.company) || company(posts[0]?.company) || S.data.companies[0];
  const a = account(c, S.platform === 'all' ? 'instagram' : S.platform);
  if (!posts.length) return empty();
  return html`<div class="profile">
    <div class="profile-head">
      <span class="avatar brand large" style="background:${esc(c?.color)}"
        >${esc(initials(a.name))}</span
      >
      <div>
        <h2>${esc(a.handle)}</h2>
        <div class="row smalltext">
          <strong>${posts.length} posts</strong><span class="muted">Private preview</span>
        </div>
        <p class="smalltext" style="line-height:1.7;margin-bottom:0">
          <strong>${esc(a.name)}</strong><br />${esc(
            a.bio || 'Planned and published content, side by side.',
          )}
        </p>
      </div>
    </div>
    <div class="row spread smalltext muted" style="padding:12px 0">
      <span
        >▦ ${S.platform === 'all' ? 'All platforms' : esc(names[S.platform])} profile preview</span
      ><span>Newest first</span>
    </div>
    <div class="profile-grid">
      ${posts
        .map(
          p =>
            html`<button
              class="grid-cell"
              data-action="review"
              data-id="${p.id}"
              title="${esc(p.title || p.caption.slice(0, 80))}"
            >
              ${p.assets[0]?.mime.startsWith('image')
                ? html`<img
                    loading="lazy"
                    src="${assetUrl(p.assets[0])}"
                    alt="${esc(p.title || 'Post')}"
                  />`
                : p.assets[0]?.mime.startsWith('video')
                  ? html`<video
                      preload="metadata"
                      src="${assetUrl(p.assets[0])}#t=0.1"
                      muted
                    ></video>`
                  : html`<span class="text-tile"
                      >${p.assets[0]?.mime === 'application/pdf'
                        ? '▤ ' + esc(p.title || p.assets[0].name)
                        : esc((p.caption || p.title).slice(0, 150))}</span
                    >`}<span class="grid-icon"
                >${p.assets.length > 1
                  ? '▣'
                  : p.assets[0]?.mime.startsWith('video')
                    ? '▶'
                    : ''}</span
              ><span class="grid-label">${badge(p)}</span>
            </button>`,
        )
        .join('')}
    </div>
  </div>`;
}
function calendarView(posts) {
  const year = S.month.getFullYear(),
    month = S.month.getMonth();
  const start = new Date(year, month, 1);
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  const days = Array.from({ length: 42 }, (_, i) => {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    return d;
  });
  const key = d =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  return html`<div class="calendar">
      <div class="calendar-header">
        <strong
          >${S.month.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</strong
        >
        <div class="row">
          <button class="small" data-action="month" data-delta="-1">←</button
          ><button class="small" data-action="month" data-delta="0">Today</button
          ><button class="small" data-action="month" data-delta="1">→</button>
        </div>
      </div>
      <div class="calendar-grid">
        ${['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
          .map(d => html`<div class="calendar-day weekday">${d}</div>`)
          .join('')}${days
          .map(
            d =>
              html`<div
                class="calendar-day ${d.getMonth() !== month ? 'outside' : ''} ${key(d) ===
                key(new Date())
                  ? 'today'
                  : ''}"
              >
                <span>${d.getDate()}</span>${posts
                  .filter(p => p.scheduled?.slice(0, 10) === key(d))
                  .map(
                    p =>
                      html`<button
                        class="calendar-item"
                        data-action="review"
                        data-id="${p.id}"
                        title="${esc(p.title || p.caption)}"
                      >
                        ${icons[p.platform]} ${esc(p.title || p.caption.slice(0, 25) || p.format)}
                      </button>`,
                  )
                  .join('')}
              </div>`,
          )
          .join('')}
      </div>
    </div>
    <p class="smalltext muted">
      ${posts.filter(p => !p.scheduled).length} posts have no planned date. Dates are for planning;
      Feffel does not publish posts.
    </p>`;
}
