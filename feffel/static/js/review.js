'use strict';
// Review dialog: feedback, tasks, history, annotation, approvals and decisions.
async function review(id, tab = 'feedback') {
  const p = await api('/api/posts/' + id);
  S.strokes = [];
  S.pin = null;
  S.selectedText = '';
  S.reply = null;
  S.pdfPage = 1;
  S.drawMode = '';
  showReview(p, tab);
}
function showReview(p, tab = 'feedback', revision) {
  const r = revision ? { ...p, ...revision.data, assets: revision.data.assets } : p;
  S.reviewTab = tab;
  S.drawMode = '';
  const c = company(p.company);
  const index = S.slides['review:' + p.id] || 0;
  const asset = r.assets[index];
  modal(
    p.title || 'Review post',
    html`<div class="review-layout">
      <div>
        <div class="row spread" style="margin-bottom:15px">
          <span class="row"
            ><span class="platform-symbol">${icons[p.platform]}</span
            ><strong class="smalltext">${esc(names[p.platform])} · ${esc(p.format)}</strong></span
          >${badge(p)}
        </div>
        ${revision
          ? html`<div class="version-alert">
              Viewing version ${revision.version}, saved by ${esc(revision.name)}. Feedback will be
              attached to this version.
              <button class="small" data-action="current-version">Return to current</button>
            </div>`
          : ''}
        <div class="annotation-toolbar">
          <button data-action="draw-mode" data-mode="pen">✎ Draw</button
          ><button data-action="draw-mode" data-mode="pin">⌖ Pin</button
          ><input
            type="color"
            id="draw-color"
            value="#ef4669"
            aria-label="Annotation colour"
          /><button data-action="clear-drawing">Clear</button
          ><span class="tiny muted" id="annotation-hint">Draw or pin directly on an image.</span>
        </div>
        <div class="review-media" id="review-media">
          ${mediaMarkup(r, 'review')}<canvas
            id="annotation-canvas"
            aria-label="Draw feedback on this media"
          ></canvas>
        </div>
        ${asset?.mime === 'application/pdf'
          ? '<div class="row" style="margin-top:8px"><label style="margin:0">PDF feedback page</label><input id="pdf-page" type="number" min="1" max="9999" value="${S.pdfPage||1}" style="width:80px"><span class="tiny muted">Choose the page you are commenting on.</span></div>'
          : ''}<label
          >Caption
          <span class="muted" style="font-weight:400"
            >· select text to suggest a change</span
          ></label
        >
        <div class="caption caption-select" id="review-caption">${esc(r.caption)}</div>
        <div id="selection-context" class="tiny muted" style="margin:8px 0"></div>
        <div class="row wrap" style="margin-top:18px">
          ${has('edit_all') || (p.creator === S.me.user.id && has('create'))
            ? html`<button data-action="edit-post" data-id="${p.id}">Edit post</button>`
            : ''}${['approved', 'published'].includes(p.status) && has('export')
            ? html`<button data-action="export" data-id="${p.id}">
                ↓ Download publishing pack
              </button>`
            : ''}${['draft', 'changes', 'rejected'].includes(p.status) &&
          (has('edit_all') || (p.creator === S.me.user.id && has('create')))
            ? html`<button class="primary" data-action="submit-post" data-id="${p.id}">
                Submit for review →
              </button>`
            : ''}${has('archive') && p.status !== 'published'
            ? html`<button class="ghost small" data-action="archive" data-id="${p.id}">
                ${p.status === 'archived' ? 'Restore' : 'Archive'}
              </button>`
            : ''}
        </div>
        <p class="tiny muted">
          By ${esc(p.creator_name)} · Current version ${p.version} · Last updated
          ${esc(timeLabel(p.updated))}
        </p>
      </div>
      <aside class="review-sidebar">
        <div class="view-tabs" style="margin:0 0 18px">
          ${['feedback', 'tasks', 'history']
            .map(
              t =>
                html`<button
                  data-action="review-tab"
                  data-tab="${t}"
                  class="${tab === t ? 'active' : ''}"
                >
                  ${t[0].toUpperCase() + t.slice(1)}
                </button>`,
            )
            .join('')}
        </div>
        <div id="review-tab-body">
          ${tab === 'feedback'
            ? feedbackPanel(p, r)
            : tab === 'tasks'
              ? tasksPanel(p)
              : historyPanel(p)}
        </div>
      </aside>
    </div>`,
    '',
    true,
  );
  S.review = p;
  S.reviewVersion = r.version;
  S.revision = revision;
  S.reviewTab = tab;
  setupAnnotation(r);
  bindReviewForms();
}
function feedbackPanel(p, r) {
  return html`<h3>Approval progress</h3>
    ${p.stages
      .map(
        s =>
          html`<div class="progress-line ${s.done ? 'done' : ''}">
            <span class="node">${s.done ? '✓' : s.ready ? '•' : '⌑'}</span>
            <div class="grow">
              <p>${esc(s.name)}</p>
              <small
                >${esc(role(s.role)?.name)}${s.blocked_empty
                  ? ' · No eligible reviewer assigned'
                  : s.done
                    ? ' · Approved'
                    : p.status === 'draft'
                      ? ' · On submission'
                      : s.ready
                        ? ' · Ready for review'
                        : ' · Waiting for earlier stages'}</small
              >
            </div>
            ${s.can_approve
              ? html`<button
                  class="green small"
                  data-action="approve-stage"
                  data-id="${p.id}"
                  data-stage="${s.id}"
                >
                  ✓
                </button>`
              : ''}
          </div>`,
      )
      .join('')}${p.stages.some(s => s.can_approve)
      ? html`<div class="row wrap">
          <button class="small" data-action="request-changes" data-id="${p.id}">
            ✎ Request changes</button
          ><button class="small danger" data-action="reject-post" data-id="${p.id}">
            ⛔ Reject
          </button>
        </div>`
      : ''}${has('override') && !['published', 'archived', 'approved'].includes(p.status)
      ? html`<button
          class="ghost small"
          data-action="override"
          data-id="${p.id}"
          style="margin-top:10px"
        >
          Final approval override
        </button>`
      : ''}
    <h3>Feedback <span class="muted">(${p.comments.length})</span></h3>
    <div class="row tiny muted" id="feedback-context">
      Version ${r.version}${S.reply ? ' · Reply' : ''}
    </div>
    <form id="comment-form">
      <textarea
        id="comment-body"
        name="body"
        rows="3"
        placeholder="What’s working? What needs a little love? Use @Name to mention a teammate."
      ></textarea>
      <div class="row spread" style="margin-top:8px">
        <span class="tiny muted">Drawings and selected text attach automatically.</span
        ><button class="primary small" type="submit">Send feedback</button>
      </div>
    </form>
    <div id="comments">
      ${p.comments.length
        ? p.comments.map(c => commentMarkup(c)).join('')
        : '<p class="smalltext muted" style="line-height:1.8">A fresh start. Be the first to leave feedback.</p>'}
    </div>`;
}
function commentMarkup(c) {
  const ctx = c.context || {};
  const context = [
    `v${c.version}`,
    ctx.asset_index !== undefined ? 'Slide ' + (ctx.asset_index + 1) : '',
    ctx.pdf_page ? 'PDF page ' + ctx.pdf_page : '',
    ctx.time !== undefined
      ? Math.floor(ctx.time / 60) + ':' + String(Math.floor(ctx.time % 60)).padStart(2, '0')
      : '',
    ctx.strokes?.length ? 'Drawing' : '',
    ctx.pin ? 'Pin' : '',
    ctx.selected_text ? 'Selected caption' : '',
  ]
    .filter(Boolean)
    .join(' · ');
  return html`<div class="comment ${c.resolved ? 'resolved' : ''} ${c.parent ? 'reply' : ''}">
    <div class="row">
      <span class="avatar" style="width:25px;height:25px;font-size:10px"
        >${esc(initials(c.name))}</span
      ><strong class="smalltext">${esc(c.name)}</strong><span class="grow"></span
      ><span class="tiny muted">${esc(dateLabel(c.created))}</span>
    </div>
    <button class="context ghost" data-action="show-annotation" data-comment="${c.id}">
      ${esc(context)}</button
    >${ctx.selected_text
      ? html`<blockquote
          class="smalltext muted"
          style="margin:10px 0;padding-left:10px;border-left:2px solid var(--purple)"
        >
          ${esc(ctx.selected_text)}
        </blockquote>`
      : ''}
    <div class="body">${esc(c.body || 'Drawing annotation')}</div>
    <div class="comment-actions">
      <button data-action="reply" data-comment="${c.id}">Reply</button>${c.user === S.me.user.id ||
      has('review') ||
      has('edit_all')
        ? html`<button
            data-action="resolve"
            data-comment="${c.id}"
            data-resolved="${c.resolved ? '0' : '1'}"
          >
            ${c.resolved ? 'Reopen' : '✓ Resolve'}
          </button>`
        : ''}
    </div>
  </div>`;
}
function tasksPanel(p) {
  return html`<h3>Creative + marketing, together.</h3>
    <p class="smalltext muted" style="line-height:1.7">
      Work in parallel. All tasks must be complete before submitting the post for review.
    </p>
    ${p.tasks
      .map(
        t =>
          html`<div class="task">
            <div class="row spread">
              <span class="pill">${esc(t.kind)}</span
              ><select
                class="task-status"
                data-task="${t.id}"
                aria-label="Task status"
                ${t.assignee === S.me.user.id || has('edit_all') || p.creator === S.me.user.id
                  ? ''
                  : 'disabled'}
              >
                ${[
                  ['todo', 'To do'],
                  ['doing', 'In progress'],
                  ['done', 'Complete'],
                ]
                  .map(
                    ([v, n]) =>
                      html`<option value="${v}" ${t.status === v ? 'selected' : ''}>${n}</option>`,
                  )
                  .join('')}
              </select>
            </div>
            <p class="smalltext" style="line-height:1.6"><strong>${esc(t.title)}</strong></p>
            <div class="tiny muted">
              ${esc(memberName(t.assignee))}${t.due ? ' · Due ' + esc(dateLabel(t.due)) : ''}
            </div>
            ${t.notes ? html`<p class="smalltext">${esc(t.notes)}</p>` : ''}<button
              class="ghost small"
              data-action="task-notes"
              data-task="${t.id}"
            >
              Edit notes
            </button>
          </div>`,
      )
      .join('') || '<p class="smalltext muted">No tasks added yet.</p>'}${[
      'draft',
      'changes',
      'rejected',
    ].includes(p.status) &&
    (has('edit_all') || p.creator === S.me.user.id)
      ? html`<form id="task-form">
          <label>New task</label
          ><input name="title" placeholder="e.g. Finish carousel layout" required maxlength="300" />
          <div class="form-grid">
            <div>
              <label>Workstream</label
              ><select name="kind">
                <option>Creative</option>
                <option>Marketing</option>
                <option>Legal</option>
                <option>Other</option>
              </select>
            </div>
            <div>
              <label>Assigned to</label
              ><select name="assignee">
                <option value="">Unassigned</option>
                ${S.data.members
                  .filter(m => canSeePost(m, p))
                  .map(m => html`<option value="${m.user}">${esc(m.name)}</option>`)
                  .join('')}
              </select>
            </div>
          </div>
          <label>Due date</label><input type="date" name="due" /><button
            class="primary small"
            style="margin-top:12px"
          >
            Add task
          </button>
        </form>`
      : ''}`;
}
function historyPanel(p) {
  return html`<h3>Previous versions</h3>
    <div class="revision-list">
      ${p.revisions
        .map(
          r =>
            html`<div class="revision-row row">
              <div class="grow">
                <strong class="smalltext">Version ${r.version}</strong>
                <div class="tiny muted" style="margin-top:5px">
                  ${esc(r.name)} · ${esc(timeLabel(r.created))}
                </div>
              </div>
              <button class="small" data-action="revision" data-version="${r.version}">View</button>
            </div>`,
        )
        .join('')}
    </div>
    <h3>Review decisions</h3>
    ${p.decisions
      .map(
        d =>
          html`<div class="history-entry">
            <strong>${esc(d.name)} · ${esc(d.action)}</strong
            ><span class="muted"
              >v${d.version} · ${esc(d.stage)} · ${esc(timeLabel(d.created))}</span
            >${d.note ? '<div>' + esc(d.note) + '</div>' : ''}
          </div>`,
      )
      .join('') || '<p class="smalltext muted">No decisions recorded.</p>'}
    <h3>Activity trail</h3>
    ${p.history
      .map(
        h =>
          html`<div class="history-entry">
            <strong>${esc(h.event)}</strong
            ><span class="muted">${esc(h.name)} · ${esc(timeLabel(h.created))}</span>${h.detail
              ? '<div>' + esc(h.detail) + '</div>'
              : ''}
          </div>`,
      )
      .join('')}`;
}
function setupAnnotation(p) {
  const canvas = $('#annotation-canvas'),
    container = $('#review-media');
  if (!canvas || !container) return;
  const ctx = canvas.getContext('2d');
  function resize() {
    const media = $('.media', container);
    if (!media) return;
    const rect = media.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(rect.width * devicePixelRatio));
    canvas.height = Math.max(1, Math.round(rect.height * devicePixelRatio));
    canvas.style.height = rect.height + 'px';
    draw();
  }
  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const s of S.strokes) {
      if (!Array.isArray(s.points)) continue;
      ctx.strokeStyle = s.color || '#ef4669';
      ctx.lineWidth = 3 * devicePixelRatio;
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      ctx.beginPath();
      s.points.forEach((pt, i) => {
        const x = pt[0] * canvas.width,
          y = pt[1] * canvas.height;
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      });
      ctx.stroke();
    }
    if (S.pin) {
      ctx.fillStyle = '#ef4669';
      ctx.beginPath();
      ctx.arc(
        S.pin[0] * canvas.width,
        S.pin[1] * canvas.height,
        10 * devicePixelRatio,
        0,
        Math.PI * 2,
      );
      ctx.fill();
      ctx.fillStyle = 'white';
      ctx.font = `bold ${12 * devicePixelRatio}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.fillText('!', S.pin[0] * canvas.width, S.pin[1] * canvas.height + 4 * devicePixelRatio);
    }
  }
  let current = null;
  const point = e => {
    const r = canvas.getBoundingClientRect();
    return [
      Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)),
      Math.max(0, Math.min(1, (e.clientY - r.top) / r.height)),
    ];
  };
  canvas.onpointerdown = e => {
    if (!S.drawMode) return;
    canvas.setPointerCapture(e.pointerId);
    if (S.drawMode === 'pin') {
      S.pin = point(e);
      draw();
    } else {
      current = { color: $('#draw-color').value, points: [point(e)] };
      S.strokes.push(current);
    }
  };
  canvas.onpointermove = e => {
    if (current && current.points.length < 5000) {
      current.points.push(point(e));
      draw();
    }
  };
  canvas.onpointerup = () => (current = null);
  canvas.onpointercancel = () => (current = null);
  const ro = new ResizeObserver(resize);
  ro.observe(container);
  S.modalCleanup = () => ro.disconnect();
  S.redraw = draw;
  resize();
  $('#review-caption').onmouseup = () => {
    const sel = getSelection();
    if (sel?.toString().trim() && $('#review-caption').contains(sel.anchorNode)) {
      S.selectedText = sel.toString().slice(0, 5000);
      $('#selection-context').textContent = 'Selected: “' + S.selectedText.slice(0, 100) + '”';
    }
  };
  if ($('#pdf-page'))
    $('#pdf-page').onchange = e => {
      S.pdfPage = Math.max(1, Number(e.target.value) || 1);
      const frame = $('iframe', container);
      if (frame)
        frame.src = assetUrl(p.assets[S.slides['review:' + p.id] || 0]) + '#page=' + S.pdfPage;
    };
}
function bindReviewForms() {
  const p = S.review;
  if (!p) return;
  const form = $('#comment-form');
  if (form)
    form.onsubmit = async e => {
      e.preventDefault();
      const text = $('#comment-body').value;
      const video = $('#review-media video');
      const index = S.slides['review:' + p.id] || 0;
      const ctx = { strokes: S.strokes, pin: S.pin, selected_text: S.selectedText };
      if (p.assets.length) ctx.asset_index = index;
      if (video) ctx.time = video.currentTime;
      if ($('#pdf-page')) ctx.pdf_page = S.pdfPage || 1;
      try {
        const result = await api('/api/posts/' + p.id + '/comment', {
          body: text,
          context: ctx,
          version: S.reviewVersion,
          parent: S.reply,
        });
        S.strokes = [];
        S.pin = null;
        S.selectedText = '';
        S.reply = null;
        await load(true);
        showReview(result, S.reviewTab, S.revision);
        toast('Feedback added.');
      } catch (err) {
        toast(err.message);
      }
    };
  const task = $('#task-form');
  if (task)
    task.onsubmit = async e => {
      e.preventDefault();
      try {
        const result = await api(
          '/api/posts/' + p.id + '/task',
          Object.fromEntries(new FormData(e.target)),
        );
        await load(true);
        showReview(result, 'tasks');
      } catch (err) {
        toast(err.message);
      }
    };
  $$('.task-status').forEach(
    el =>
      (el.onchange = async e => {
        try {
          const result = await api('/api/posts/' + p.id + '/task-update', {
            id: e.target.dataset.task,
            status: e.target.value,
          });
          await load(true);
          showReview(result, 'tasks');
        } catch (err) {
          toast(err.message);
        }
      }),
  );
}
async function changePost(id, action, body = {}, keepReview = false) {
  const p = S.review?.id === id ? S.review : S.data.posts.find(p => p.id === id);
  const result = await api('/api/posts/' + id + '/' + action, { lock: p.lock, ...body });
  await load(true);
  render();
  if (keepReview) showReview(result, S.reviewTab);
  return result;
}
async function approve(id, stage) {
  const p = S.review?.id === id ? S.review : S.data.posts.find(p => p.id === id);
  const stages = p.stages.filter(s => s.can_approve);
  if (!stages.length) {
    toast('This post has no review stage assigned to you yet.');
    return;
  }
  if (!stage && stages.length > 1) {
    await review(id);
    toast('Choose which stage to approve.');
    return;
  }
  const keep = S.review?.id === id;
  const result = await changePost(
    id,
    'decision',
    { stage: stage || stages[0].id, action: 'approve' },
    keep,
  );
  toast(
    result.status === 'approved'
      ? 'All reviews complete. Ready to publish.'
      : 'Your approval is recorded.',
    async () => {
      try {
        await changePost(id, 'undo', {}, keep);
        toast('Approval undone.');
      } catch (e) {
        toast(e.message);
      }
    },
  );
}
async function decisionDialog(id, action) {
  const p = await api('/api/posts/' + id);
  const stages = p.stages.filter(s => s.can_approve);
  const title =
    action === 'override'
      ? 'Final approval override'
      : action === 'changes'
        ? 'Request changes'
        : 'Reject post';
  modal(
    title,
    html`<form id="decision-form">
      ${action !== 'override'
        ? html`<label>Review stage</label
            ><select name="stage">
              ${stages.map(s => html`<option value="${s.id}">${esc(s.name)}</option>`).join('')}
            </select>`
        : '<p class="intro">This records your final authority and approves the current version. The normal review trail remains visible.</p>'}<label
        >${action === 'override' ? 'Reason for overriding' : 'What needs to change?'}</label
      ><textarea
        name="note"
        required
        maxlength="5000"
        placeholder="Give the team enough detail to act on your feedback."
      ></textarea>
    </form>`,
    html`<button data-action="close-modal">Cancel</button
      ><button class="primary" form="decision-form" type="submit">${title}</button>`,
  );
  $('#decision-form').onsubmit = async e => {
    e.preventDefault();
    try {
      const b = Object.fromEntries(new FormData(e.target));
      await api('/api/posts/' + id + '/' + (action === 'override' ? 'override' : 'decision'), {
        lock: p.lock,
        ...b,
        action,
      });
      closeModal();
      await load();
      toast(
        action === 'override'
          ? 'Final approval recorded.'
          : 'Decision recorded and sent back to the creator.',
      );
    } catch (err) {
      toast(err.message);
    }
  };
}
