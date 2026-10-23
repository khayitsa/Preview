/** Build a self-contained preview, including HTML visible when scripts are blocked. */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
// The Flask template is the single source of truth for script and style order
// (the scripts share one global scope).
const template = read('feffel/templates/index.html');
const assets = pattern => [...template.matchAll(pattern)].map(m => 'feffel/static/' + m[1]);
const scripts = assets(/<script[^>]+filename='(js\/[^']+)'/g);
const styles = assets(/<link[^>]+filename='(css\/[^']+)'/g)
  .map(read)
  .join('\n');
const code = scripts
  .map(read)
  .join('\n')
  .replace(/\nboot\(\);\s*$/, '');
const fixtures = ['data.js', 'art.js', 'fixture.js']
  .map(n => read('tests/browser-fixture/' + n))
  .join('\n');
const elements = new Map();
const element = id => {
  if (!elements.has(id))
    elements.set(id, {
      innerHTML: '',
      value: '',
      classList: { toggle() {} },
      focus() {},
      querySelector() {
        return null;
      },
      querySelectorAll() {
        return [];
      },
    });
  return elements.get(id);
};
const document = {
  documentElement: { classList: { toggle() {} } },
  querySelector(s) {
    return [
      '#app',
      '#modal-root',
      '#toast',
      '#org-select',
      '#search',
      '#page',
      '#company-filter',
      '#status-filter',
    ].includes(s)
      ? element(s)
      : null;
  },
  querySelectorAll() {
    return [];
  },
  addEventListener() {},
  activeElement: null,
};
const sandbox = {
  document,
  console,
  Response,
  URLSearchParams,
  location: { search: '', pathname: '/', origin: 'null' },
  setInterval() {},
  setTimeout() {},
  clearTimeout() {},
  structuredClone,
  crypto: globalThis.crypto,
};
sandbox.window = sandbox;
// A sandbox/file viewer can deny access to this property entirely.
Object.defineProperty(sandbox, 'localStorage', {
  get() {
    throw new Error('SecurityError: storage unavailable');
  },
});
const context = vm.createContext(sandbox);
vm.runInContext(fixtures + '\n' + code, context);
await vm.runInContext('boot()', context);
let initial = element('#app').innerHTML;
if (!initial.includes('A little less back-and-forth.') || initial.includes('Couldn’t connect'))
  throw Error('Preview startup failed with blocked storage');
vm.runInContext("S.view='grid';render();", context);
initial = element('#app').innerHTML;
if (!initial.includes('profile-grid') || !initial.includes('data:image/svg+xml'))
  throw Error('Static fallback or embedded images missing');
const marker =
  '<div id="preview-status" style="position:fixed;bottom:12px;right:12px;background:#292337;color:white;padding:9px 14px;border-radius:9px;z-index:99;font:11px system-ui;box-shadow:0 3px 20px #0002">Read-only preview · Open in a browser for interactive controls</div>';
const source =
  fixtures +
  '\n' +
  code +
  "\nboot().then(()=>{const notice=document.querySelector('#preview-status');if(notice)notice.textContent='Read-only preview · Fictional content';});";
const html =
  '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Feffel · Interactive preview</title><style>' +
  styles +
  '</style></head><body><div id="app">' +
  initial +
  '</div><div id="modal-root"></div><div id="toast" role="status" aria-live="polite"></div>' +
  marker +
  '<script>' +
  source.replace(/<\/script/gi, '<\\/script') +
  '</script></body></html>';
fs.writeFileSync(path.join(root, 'Feffel-preview.html'), html);
console.log(
  'Preview built: blocked-storage startup passed; static grid and embedded media are visible without scripts.',
);
