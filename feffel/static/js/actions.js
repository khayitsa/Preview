'use strict';
// Notifications, export, the central click handler, global listeners and auto-refresh.
async function notifications() {
  const list = S.data.notifications;
  modal(
    'Your notifications',
    list.length
      ? list
          .map(
            n =>
              html`<div
                class="notification ${n.seen ? '' : 'unread'}"
                data-action="notification-open"
                data-id="${esc(n.post || '')}"
              >
                ${esc(n.body)}
                <div class="tiny muted">${esc(timeLabel(n.created))}</div>
              </div>`,
          )
          .join('')
      : '<div class="empty-state"><h2>You’re up to date.</h2><p>Feedback, review requests and task updates will appear here.</p></div>',
  );
  await api('/api/notifications/read', {});
  await load(true);
}
async function downloadPack(id) {
  const r = await fetch('/api/posts/' + id + '/export', { headers: { 'X-Org-ID': S.org } });
  if (!r.ok) {
    const e = await r.json();
    throw new Error(e.error);
  }
  const blob = await r.blob(),
    url = URL.createObjectURL(blob),
    a = document.createElement('a');
  a.href = url;
  a.download = 'feffel-publishing-pack-' + id.slice(0, 8) + '.zip';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
async function handleAction(el) {
  const a = el.dataset.action,
    id = el.dataset.id;
  if (a === 'retry') return boot();
  if (a === 'dismiss-invite') {
    history.replaceState({}, '', location.pathname);
    return boot();
  }
  if (a === 'auth-mode') return renderAuth(el.dataset.mode);
  if (a === 'nav') {
    S.nav = el.dataset.nav;
    if (S.nav === 'queue' || S.nav === 'tasks' || S.nav === 'approved') {
      S.platform = 'all';
      S.status = 'all';
      S.company = 'all';
    }
    return render();
  }
  if (a === 'theme') {
    S.theme = S.theme === 'dark' ? 'light' : 'dark';
    preferences.setItem('feffel-theme', S.theme);
    document.documentElement.classList.toggle('dark', S.theme === 'dark');
    return;
  }
  if (a === 'logout') {
    await api('/api/logout', {});
    S.data = null;
    S.org = '';
    closeModal();
    return boot();
  }
  if (a === 'platform') {
    S.platform = el.dataset.platform;
    return renderPage();
  }
  if (a === 'view') {
    S.view = el.dataset.view;
    return renderPage();
  }
  if (a === 'month') {
    const delta = Number(el.dataset.delta);
    S.month = delta
      ? new Date(S.month.getFullYear(), S.month.getMonth() + delta, 1)
      : new Date(new Date().getFullYear(), new Date().getMonth(), 1);
    return renderPage();
  }
  if (a === 'new-post') return createEditor();
  if (a === 'edit-post') return createEditor(id);
  if (a === 'close-modal') return closeModal();
  if (a === 'review' || a === 'notification-open') return id ? review(id) : undefined;
  if (a === 'notifications') return notifications();
  if (a === 'slide') {
    const scope = el.dataset.scope,
      key = scope + ':' + id;
    const p =
      scope === 'review'
        ? S.revision
          ? { ...S.review, ...S.revision.data }
          : S.review
        : S.data.posts.find(x => x.id === id);
    if (!p) return;
    S.slides[key] =
      ((S.slides[key] || 0) + Number(el.dataset.delta) + p.assets.length) % p.assets.length;
    if (scope === 'review') {
      S.strokes = [];
      S.pin = null;
      const current = S.review;
      showReview(current, S.reviewTab, S.revision);
    } else {
      const old = $('#post-' + id);
      if (old) old.outerHTML = postCard(p);
    }
    return;
  }
  if (a === 'upload-remove') {
    S.editor.assets.splice(Number(el.dataset.index), 1);
    return renderUploads();
  }
  if (a === 'upload-move') {
    const from = Number(el.dataset.index),
      to = from + Number(el.dataset.delta);
    if (to >= 0 && to < S.editor.assets.length)
      [S.editor.assets[from], S.editor.assets[to]] = [S.editor.assets[to], S.editor.assets[from]];
    return renderUploads();
  }
  if (a === 'quick-approve' || a === 'approve-stage') return approve(id, el.dataset.stage);
  if (a === 'reaction') {
    const p = S.data.posts.find(x => x.id === id);
    const emoji =
      p.reactions.find(r => r.user === S.me.user.id)?.emoji === el.dataset.emoji
        ? ''
        : el.dataset.emoji;
    return changePost(id, 'reaction', { emoji });
  }
  if (a === 'review-tab') {
    const p = S.review;
    return showReview(p, el.dataset.tab, S.revision);
  }
  if (a === 'request-changes') return decisionDialog(id, 'changes');
  if (a === 'reject-post') return decisionDialog(id, 'reject');
  if (a === 'override') return decisionDialog(id, 'override');
  if (a === 'submit-post') {
    await changePost(id, 'submit', {}, true);
    return toast('Submitted to the review chain.');
  }
  if (a === 'archive') {
    await changePost(id, 'archive');
    closeModal();
    return toast('Archive status updated.');
  }
  if (a === 'export') return downloadPack(id);
  if (a === 'draw-mode') {
    const asset = (S.revision?.data.assets || S.review.assets)[
      S.slides['review:' + S.review.id] || 0
    ];
    if (!asset?.mime.startsWith('image'))
      return toast(
        'Drawing and pins work on images. Use timestamps for videos or a page number for PDF feedback.',
      );
    S.drawMode = S.drawMode === el.dataset.mode ? '' : el.dataset.mode;
    $('#annotation-canvas').classList.toggle('drawing', !!S.drawMode);
    $$('[data-action=draw-mode]').forEach(b =>
      b.classList.toggle('active', b.dataset.mode === S.drawMode),
    );
    $('#annotation-hint').textContent =
      S.drawMode === 'pen'
        ? 'Draw on the image, then send feedback.'
        : S.drawMode === 'pin'
          ? 'Click an exact spot, then send feedback.'
          : 'Draw or pin directly on an image.';
    return;
  }
  if (a === 'clear-drawing') {
    S.strokes = [];
    S.pin = null;
    S.redraw?.();
    return;
  }
  if (a === 'reply') {
    S.reply = el.dataset.comment;
    $('#feedback-context').textContent =
      'Replying to ' + S.review.comments.find(c => c.id === S.reply)?.name;
    $('#comment-body').focus();
    return;
  }
  if (a === 'resolve') {
    const p = S.review;
    const result = await api('/api/posts/' + p.id + '/resolve', {
      id: el.dataset.comment,
      resolved: el.dataset.resolved === '1',
    });
    await load(true);
    return showReview(result, 'feedback', S.revision);
  }
  if (a === 'revision') {
    const p = S.review,
      r = p.revisions.find(r => r.version === Number(el.dataset.version));
    S.strokes = [];
    S.pin = null;
    S.slides['review:' + p.id] = 0;
    return showReview(p, 'history', r);
  }
  if (a === 'current-version') {
    const p = S.review;
    S.strokes = [];
    S.pin = null;
    S.slides['review:' + p.id] = 0;
    return showReview(p, 'feedback');
  }
  if (a === 'show-annotation') {
    const p = S.review,
      c = p.comments.find(c => c.id === el.dataset.comment),
      revision = p.revisions.find(r => r.version === c.version);
    S.slides['review:' + p.id] = c.context.asset_index || 0;
    S.strokes = c.context.strokes || [];
    S.pin = c.context.pin || null;
    S.pdfPage = c.context.pdf_page || 1;
    showReview(p, 'feedback', c.version !== p.version ? revision : undefined);
    const video = $('#review-media video');
    if (video && c.context.time !== undefined) {
      video.onloadedmetadata = () => (video.currentTime = c.context.time);
    }
    $('#selection-context').textContent = c.context.selected_text
      ? 'Caption feedback: “' + c.context.selected_text + '”'
      : 'Showing saved annotation by ' + c.name;
    return;
  }
  if (a === 'task-notes') {
    const p = S.review,
      t = p.tasks.find(t => t.id === el.dataset.task);
    modal(
      'Task notes',
      html`<form id="notes-form">
        <p class="intro">${esc(t.title)}</p>
        <label>Notes</label><textarea name="notes">${esc(t.notes)}</textarea>
      </form>`,
      html`<button data-action="close-modal">Cancel</button
        ><button class="primary" form="notes-form" type="submit">Save notes</button>`,
    );
    $('#notes-form').onsubmit = async e => {
      e.preventDefault();
      try {
        const result = await api('/api/posts/' + p.id + '/task-update', {
          id: t.id,
          status: t.status,
          notes: new FormData(e.target).get('notes'),
        });
        await load(true);
        showReview(result, 'tasks');
      } catch (err) {
        toast(err.message);
      }
    };
    return;
  }
  if (a === 'settings-tab') {
    S.settingsTab = el.dataset.tab;
    return renderPage();
  }
  if (a === 'company-edit') return companyDialog(id);
  if (a === 'account-edit') return accountDialog(el.dataset.company, el.dataset.platform);
  if (a === 'invite') return memberDialog();
  if (a === 'member-edit') return memberDialog(id);
  if (a === 'member-reset') return resetLinkDialog(id);
  if (a === 'member-remove') {
    const m = S.data.members.find(x => x.id === id);
    modal(
      'Remove member access',
      html`<p class="intro">
        Remove ${esc(m.name)} from this organisation? Their feedback and review history will remain.
        You can invite them again later.
      </p>`,
      html`<button data-action="close-modal">Cancel</button
        ><button class="danger" data-action="member-remove-confirm" data-id="${id}">
          Remove access
        </button>`,
    );
    return;
  }
  if (a === 'member-remove-confirm') return saveSettings('remove-member', { id });
  if (a === 'invite-revoke') {
    await api('/api/admin/revoke-invite', { id });
    await load();
    return toast('Invitation revoked.');
  }
  if (a === 'role-edit') return roleDialog(id);
  if (a === 'copy-invite') {
    const input = $('#invite-link');
    try {
      await navigator.clipboard.writeText(input.value);
      toast('Link copied.');
    } catch {
      input.select();
      toast('Select and copy the invitation link.');
    }
    return;
  }
  if (a === 'stage-add') {
    S.workflowDraft = readStages();
    S.workflowDraft.push({
      id: 'stage_' + crypto.getRandomValues(new Uint32Array(1))[0].toString(16),
      name: 'New review stage',
      role: S.data.roles.find(r => r.permissions.includes('review'))?.id,
      depends: [],
      mode: 'any',
      allow_self: true,
    });
    $('#stages-editor').innerHTML = stagesEditor();
    return;
  }
  if (a === 'stage-remove') {
    S.workflowDraft = readStages();
    const removed = S.workflowDraft.splice(Number(el.dataset.index), 1)[0];
    S.workflowDraft.forEach(s => (s.depends = s.depends.filter(d => d !== removed.id)));
    $('#stages-editor').innerHTML = stagesEditor();
    return;
  }
  if (a === 'workflow-save') {
    S.workflowDraft = readStages();
    await api('/api/admin/workflow', { company: S.workflowCompany, stages: S.workflowDraft });
    await load();
    return toast('Approval workflow saved.');
  }
}
document.addEventListener('click', e => {
  const el = e.target.closest('[data-action]');
  if (el) {
    e.preventDefault();
    Promise.resolve(handleAction(el)).catch(err =>
      err.status === 401 && S.data ? sessionLost() : toast(err.message),
    );
  }
});
document.addEventListener('dblclick', e => {
  if (e.target.closest('button,video,iframe,canvas') || !e.target.closest('.media')) return;
  const el = e.target.closest('[data-post-media]');
  if (el?.dataset.scope === 'feed') approve(el.dataset.postMedia).catch(err => toast(err.message));
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && $('.modal')) {
    closeModal();
    return;
  }
  if (e.key === 'Tab' && $('.modal')) {
    const focusable = $$(
      'button:not(:disabled),a,input:not(:disabled),textarea:not(:disabled),select:not(:disabled),[tabindex="0"]',
      $('.modal'),
    ).filter(el => el.offsetParent !== null);
    const first = focusable[0],
      last = focusable.at(-1);
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last?.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first?.focus();
    }
  }
});
// Refresh the shared workspace without interrupting an editor or a focused search.
refreshTimer = setInterval(async () => {
  if (
    S.data &&
    S.nav !== 'settings' &&
    !$('.modal') &&
    document.activeElement?.id !== 'search' &&
    !document.hidden
  ) {
    try {
      const y = scrollY;
      await load();
      scrollTo(0, y);
    } catch (err) {
      // A transient failure retries on the next interval; a lost session needs signing in again.
      if (err.status === 401) sessionLost();
    }
  }
}, 45000);
