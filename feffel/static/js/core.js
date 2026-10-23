'use strict';
// Shared state, constants, tiny helpers, API client, toast and modal shell.
// File viewers and private/sandboxed browsers may deny localStorage entirely.
const memoryPreferences = new Map();
const preferences = {
  getItem(key) {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return memoryPreferences.get(key) ?? null;
    }
  },
  setItem(key, value) {
    memoryPreferences.set(key, String(value));
    try {
      window.localStorage.setItem(key, String(value));
    } catch {
      /* preferences are optional */
    }
  },
};
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
// Tagged template for HTML strings: behaves exactly like an untagged template literal,
// but lets editors and Prettier recognise and format the markup.
const html = (strings, ...values) => strings.reduce((out, s, i) => out + values[i - 1] + s);
const esc = v =>
  String(v ?? '').replace(
    /[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
const icons = {
  instagram: '◎',
  facebook: 'f',
  linkedin: 'in',
  x: '𝕏',
  tiktok: '♪',
  youtube: '▶',
  pinterest: 'p',
  threads: '@',
};
const names = {
  instagram: 'Instagram',
  facebook: 'Facebook',
  linkedin: 'LinkedIn',
  x: 'X / Twitter',
  tiktok: 'TikTok',
  youtube: 'YouTube',
  pinterest: 'Pinterest',
  threads: 'Threads',
};
const labels = {
  draft: 'Draft',
  review: 'In review',
  approved: 'Approved',
  changes: 'Changes requested',
  rejected: 'Rejected',
  published: 'Published',
  archived: 'Archived',
};
const S = {
  me: null,
  org: preferences.getItem('feffel-org') || '',
  data: null,
  company: 'all',
  platform: 'instagram',
  view: 'feed',
  nav: 'workspace',
  status: 'all',
  search: '',
  slides: {},
  month: new Date(new Date().getFullYear(), new Date().getMonth(), 1),
  settingsTab: 'companies',
  editor: null,
  review: null,
  reviewTab: 'feedback',
  drawMode: '',
  strokes: [],
  pin: null,
  selectedText: '',
  reply: null,
  modalCleanup: null,
  theme: preferences.getItem('feffel-theme') || 'light',
};
document.documentElement.classList.toggle('dark', S.theme === 'dark');
let toastTimer, refreshTimer;
function toast(message, undo) {
  const el = $('#toast');
  el.replaceChildren(document.createTextNode(message));
  if (undo) {
    const b = document.createElement('button');
    b.textContent = 'Undo';
    b.onclick = undo;
    el.append(b);
  }
  el.classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('visible'), undo ? 10000 : 5000);
}
async function api(path, body, method) {
  const headers = { 'X-Org-ID': S.org };
  if (S.me?.csrf) headers['X-CSRF-Token'] = S.me.csrf;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(path, {
    method: method || (body === undefined ? 'GET' : 'POST'),
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Request failed');
  return data;
}
function has(p) {
  return S.data?.permissions.includes(p);
}
function company(id) {
  return S.data?.companies.find(c => c.id === id);
}
function role(id) {
  return S.data?.roles.find(r => r.id === id);
}
function memberName(id) {
  return S.data?.members.find(m => m.user === id)?.name || 'Unassigned';
}
function initials(name) {
  return String(name || 'F')
    .split(/\s+/)
    .slice(0, 2)
    .map(x => x[0])
    .join('')
    .toUpperCase();
}
function assetUrl(a) {
  return (
    '/file/' +
    encodeURIComponent(S.org) +
    '/' +
    encodeURIComponent(typeof a === 'string' ? a : a.id)
  );
}
function dateLabel(value) {
  if (!value) return 'No date set';
  const d = new Date(value);
  return isNaN(d)
    ? value
    : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}
function timeLabel(value) {
  if (!value) return '';
  return new Date(value).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}
function account(c, platform) {
  return {
    name: c?.accounts?.[platform]?.name || c?.name || 'Brand',
    handle: c?.accounts?.[platform]?.handle || c?.handle || 'brand',
    bio: c?.accounts?.[platform]?.bio || '',
  };
}
function badge(p) {
  return html`<span class="pill ${esc(p.status)}">${esc(labels[p.status])}</span>`;
}
function setBusy(form, on) {
  $$('button[type=submit]', form).forEach(b => (b.disabled = on));
}

function modal(title, body, footer = '', wide = false) {
  closeModal();
  $('#modal-root').innerHTML = html`<div class="modal-overlay">
    <section
      class="modal ${wide ? 'wide' : ''}"
      role="dialog"
      aria-modal="true"
      aria-label="${esc(title)}"
      tabindex="-1"
    >
      <header class="modal-header">
        <h2>${esc(title)}</h2>
        <button class="ghost" data-action="close-modal" aria-label="Close">✕</button>
      </header>
      <div class="modal-body">${body}</div>
      ${footer ? html`<footer class="modal-footer">${footer}</footer>` : ''}
    </section>
  </div>`;
  S.previousFocus = document.activeElement;
  $('.modal').focus();
}
function closeModal() {
  if (S.modalCleanup) S.modalCleanup();
  S.modalCleanup = null;
  $('#modal-root').innerHTML = '';
  S.review = null;
  S.previousFocus?.focus?.();
}
