'use strict';
// Post editor dialog and media upload list.
async function createEditor(id) {
  let p;
  if (id) p = await api('/api/posts/' + id);
  S.editor = { id: p?.id, lock: p?.lock, assets: p?.assets ? [...p.assets] : [], p };
  const c = p?.company || (S.company === 'all' ? S.data.companies[0]?.id : S.company);
  const platform = p?.platform || (S.platform === 'all' ? 'instagram' : S.platform);
  modal(
    p ? 'Edit post' : 'Create something worth sharing',
    html`<form id="post-form">
      <div class="form-grid">
        <div>
          <label>Company</label
          ><select name="company" ${p ? 'disabled' : ''}>
            ${S.data.companies
              .map(
                x =>
                  html`<option value="${x.id}" ${c === x.id ? 'selected' : ''}>
                    ${esc(x.name)}
                  </option>`,
              )
              .join('')}
          </select>
        </div>
        <div>
          <label>Platform</label
          ><select name="platform" id="editor-platform">
            ${Object.entries(names)
              .map(
                ([k, n]) =>
                  html`<option value="${k}" ${platform === k ? 'selected' : ''}>${n}</option>`,
              )
              .join('')}
          </select>
        </div>
        <div>
          <label>Format</label
          ><select name="format" id="editor-format">
            ${S.me.platforms[platform]
              .map(f => html`<option ${p?.format === f ? 'selected' : ''}>${f}</option>`)
              .join('')}
          </select>
        </div>
        <div>
          <label>Planned / published date</label
          ><input
            name="scheduled"
            type="datetime-local"
            value="${esc(p?.scheduled?.slice(0, 16) || '')}"
          />
        </div>
      </div>
      <label>Internal post title</label
      ><input
        name="title"
        maxlength="300"
        placeholder="Give your team a little context…"
        value="${esc(p?.title || '')}"
      /><label>Caption / post text</label
      ><textarea
        name="caption"
        id="editor-caption"
        rows="6"
        maxlength="50000"
        placeholder="Write your caption, hashtags and all…"
      >
${esc(p?.caption || '')}</textarea
      >
      <div class="row spread tiny muted" style="margin-top:6px">
        <span>Each platform has its own caption and media.</span
        ><span id="caption-count">${(p?.caption || '').length} characters</span>
      </div>
      <label>Media</label>
      <div class="dropzone" id="dropzone" role="button" tabindex="0">
        ↑ Drop your files here, or <strong>browse</strong>
        <div class="tiny" style="margin-top:6px">
          Photos, videos and PDFs · multiple files become a carousel
        </div>
      </div>
      <input
        class="hidden"
        id="file-input"
        type="file"
        multiple
        accept="image/jpeg,image/png,image/gif,image/webp,video/mp4,video/quicktime,video/webm,application/pdf"
      />
      <div id="upload-progress" class="smalltext muted"></div>
      <div class="upload-list" id="upload-list"></div>
      ${!p
        ? '<label class="row"><input name="historical" type="checkbox"> This post is already published (historical content)</label>'
        : '<div class="notice" style="margin-top:18px">Changes to the caption, format or media require renewed approval. Feedback and previous versions stay available.</div>'}
      <div id="editor-error"></div>
    </form>`,
    html`<button data-action="close-modal">Cancel</button
      ><button class="primary" type="submit" form="post-form" id="save-post">
        Save ${p ? 'changes' : 'post'}
      </button>`,
  );
  renderUploads();
  $('#editor-platform').onchange = e => {
    $('#editor-format').innerHTML = S.me.platforms[e.target.value]
      .map(f => html`<option>${f}</option>`)
      .join('');
  };
  $('#editor-caption').oninput = e =>
    ($('#caption-count').textContent = e.target.value.length + ' characters');
  const drop = $('#dropzone'),
    input = $('#file-input');
  drop.onclick = () => input.click();
  drop.onkeydown = e => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      input.click();
    }
  };
  input.onchange = () => uploadFiles(input.files);
  drop.ondragover = e => {
    e.preventDefault();
    drop.classList.add('drag');
  };
  drop.ondragleave = () => drop.classList.remove('drag');
  drop.ondrop = e => {
    e.preventDefault();
    drop.classList.remove('drag');
    uploadFiles(e.dataTransfer.files);
  };
  $('#post-form').onsubmit = async e => {
    e.preventDefault();
    $('#save-post').disabled = true;
    try {
      const b = Object.fromEntries(new FormData(e.target));
      b.assets = S.editor.assets.map(a => a.id);
      b.historical = !!b.historical;
      b.lock = S.editor.lock;
      await api(S.editor.id ? '/api/posts/' + S.editor.id + '/edit' : '/api/posts', b);
      closeModal();
      await load();
      toast('Post saved.');
    } catch (err) {
      $('#editor-error').innerHTML = html`<div class="error">${esc(err.message)}</div>`;
    } finally {
      if ($('#save-post')) $('#save-post').disabled = false;
    }
  };
}
async function uploadFiles(files) {
  const editor = S.editor;
  if (!editor) return;
  $('#save-post').disabled = true;
  $('#dropzone').style.pointerEvents = 'none';
  try {
    for (let i = 0; i < files.length; i++) {
      if (editor.assets.length >= 35) throw new Error('Maximum 35 files per post.');
      if (!$('#upload-progress')) return;
      $('#upload-progress').textContent = `Uploading ${i + 1} of ${files.length}: ${files[i].name}`;
      const r = await fetch('/api/upload', {
        method: 'POST',
        headers: {
          'X-Org-ID': S.org,
          'X-CSRF-Token': S.me.csrf,
          'X-File-Name': encodeURIComponent(files[i].name),
          'Content-Type': 'application/octet-stream',
        },
        body: files[i],
      });
      const a = await r.json();
      if (!r.ok) throw new Error(a.error);
      editor.assets.push(a);
      renderUploads();
    }
    $('#upload-progress').textContent = 'Upload complete.';
  } catch (e) {
    toast(e.message);
  } finally {
    if ($('#save-post')) $('#save-post').disabled = false;
    if ($('#dropzone')) $('#dropzone').style.pointerEvents = '';
  }
}
function renderUploads() {
  const el = $('#upload-list');
  if (!el) return;
  el.innerHTML = S.editor.assets
    .map(
      (a, i) =>
        html`<div class="upload-item">
          ${a.mime.startsWith('image')
            ? html`<img src="${assetUrl(a)}" alt="${esc(a.name)}" />`
            : a.mime.startsWith('video')
              ? html`<video src="${assetUrl(a)}" preload="metadata"></video>`
              : '<div style="height:85px;display:grid;place-items:center;font-size:30px">▤</div>'}
          <div class="file-name" title="${esc(a.name)}">${i + 1}. ${esc(a.name)}</div>
          <div class="actions">
            <button data-action="upload-move" data-index="${i}" data-delta="-1" title="Move left">
              ←</button
            ><button data-action="upload-move" data-index="${i}" data-delta="1" title="Move right">
              →</button
            ><button data-action="upload-remove" data-index="${i}" title="Remove">✕</button>
          </div>
        </div>`,
    )
    .join('');
}
