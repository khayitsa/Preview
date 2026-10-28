'use strict';
// Startup, data loading and the sign-in / sign-up / invitation screens.
async function boot() {
  try {
    S.me = await api('/api/me');
    if (new URLSearchParams(location.search).get('reset')) {
      renderAuth('reset'); // a password reset link works whether or not anyone is signed in
      return;
    }
    if (!S.me.user) {
      renderAuth();
      return;
    }
    if (new URLSearchParams(location.search).get('invite')) {
      renderSignedInNotice();
      return;
    }
    if (!S.me.organisations.length) {
      renderStuck(
        'You’re not part of an organisation',
        `${S.me.user.email} isn’t a member of any organisation. An administrator may have removed your access. Ask for a new invitation, or sign out to use a different account.`,
      );
      return;
    }
    if (!S.me.organisations.some(x => x.org === S.org)) S.org = S.me.organisations[0]?.org || '';
    preferences.setItem('feffel-org', S.org);
    await load();
  } catch (e) {
    renderStuck('Couldn’t connect to Feffel', e.message);
  }
}
// The server no longer recognises the session (expired, signed out elsewhere, server reset).
function sessionLost() {
  S.data = null;
  S.me = null;
  closeModal();
  boot();
  toast('You were signed out. Please sign in again.');
}
// A full-page message with a way out: retry, and sign out when someone is signed in.
function renderStuck(title, message) {
  $('#app').innerHTML = html`<div class="empty-state">
    <h2>${esc(title)}</h2>
    <p>${esc(message)}</p>
    <button data-action="retry">Try again</button>
    ${S.me?.user ? '<button class="ghost" data-action="logout">Sign out</button>' : ''}
  </div>`;
}
async function load(quiet = false) {
  S.data = await api('/api/state');
  if (S.company !== 'all' && !company(S.company)) S.company = 'all';
  if (!quiet) render();
}
// Left-hand brand panel shared by the sign-in, sign-up and invitation screens.
function authArt() {
  return html`<div class="auth-art">
    <div class="row">
      <span class="logoicon">f</span><span class="brandword">feffel<i>.</i></span>
    </div>
    <div>
      <p>GOOD CONTENT DESERVES A BETTER PROCESS.</p>
      <h1>Feels like a feed.<br />Works like <em>a team.</em></h1>
      <p>
        Your brands, your people, your next great post. One calm place to bring it all together.
      </p>
    </div>
    <div class="row smalltext muted"><span>✦</span> A better place to review.</div>
    <div class="orb"></div>
  </div>`;
}
// An invitation link was opened while someone is already signed in: say so instead of silently
// ignoring the invitation, and let them pick which account to use.
function renderSignedInNotice() {
  $('#app').innerHTML = html`<div class="auth-page">
    ${authArt()}
    <div class="auth-box">
      <div class="row" style="margin-bottom:35px">
        <span class="logoicon">f</span><span class="brandword">feffel<i>.</i></span>
      </div>
      <h2>You’re already signed in.</h2>
      <p class="intro">
        You’re signed in as <strong>${esc(S.me.user.name)}</strong> (${esc(S.me.user.email)}).
        This invitation is for a specific email address — to accept it, sign out first and use
        the account it was sent to.
      </p>
      <button class="primary" data-action="logout">Sign out and accept invitation →</button>
      <div class="auth-switch">
        <button data-action="dismiss-invite">Stay signed in and continue to Feffel</button>
      </div>
    </div>
  </div>`;
}
// "Forgot password" (asks for an emailed link) and the screen that link opens.
function renderPasswordScreen(mode) {
  const token = new URLSearchParams(location.search).get('reset');
  const reset = mode === 'reset';
  S.authMode = mode;
  $('#app').innerHTML = html`<div class="auth-page">
    ${authArt()}
    <div class="auth-box">
      <div class="row" style="margin-bottom:35px">
        <span class="logoicon">f</span><span class="brandword">feffel<i>.</i></span>
      </div>
      <h2>${reset ? 'Choose a new password.' : 'Forgot your password?'}</h2>
      <p class="intro">
        ${reset
          ? 'Enter the email this link was made for and a new password. You’ll be signed out everywhere else.'
          : 'Enter your work email and we’ll send you a link to choose a new one.'}
      </p>
      <form id="auth-form">
        <div id="auth-error"></div>
        <label for="auth-email">Work email</label
        ><input id="auth-email" name="email" type="email" required autocomplete="email" />
        ${reset
          ? html`<label for="auth-password">New password</label
              ><input id="auth-password" name="password" type="password" minlength="12"
                maxlength="256" required autocomplete="new-password" /><label
                for="auth-confirm"
                >Confirm new password</label
              ><input id="auth-confirm" name="confirm" type="password" minlength="12"
                maxlength="256" required autocomplete="new-password" />
              <div class="required-note">At least 12 characters.</div>`
          : ''}
        <button class="primary" type="submit">${reset ? 'Set new password →' : 'Send reset link →'}</button>
      </form>
      <div class="auth-switch">
        <button data-action="auth-mode" data-mode="login">Back to sign in</button>
      </div>
    </div>
  </div>`;
  $('#auth-form').onsubmit = async e => {
    e.preventDefault();
    const f = e.currentTarget;
    const b = Object.fromEntries(new FormData(f));
    if (reset && b.password !== b.confirm) {
      $('#auth-error').innerHTML = html`<div class="error">The two passwords don’t match.</div>`;
      return;
    }
    setBusy(f, true);
    try {
      if (reset) {
        await api('/api/reset-password', { email: b.email, password: b.password, token });
        history.replaceState({}, '', location.pathname);
        S.authNotice = 'Password updated. Sign in with your new password.';
        renderAuth('login');
      } else {
        await api('/api/forgot-password', { email: b.email });
        f.innerHTML = html`<div class="notice">
          ${S.me?.email_available
            ? 'If there’s an account for that address, a reset link is on its way. It works for one hour.'
            : 'This server can’t send email yet. Ask your organisation’s administrator for a password reset link.'}
        </div>`;
      }
    } catch (err) {
      $('#auth-error').innerHTML = html`<div class="error">${esc(err.message)}</div>`;
    } finally {
      if (f.isConnected) setBusy(f, false);
    }
  };
}
function renderAuth(mode) {
  const invite = new URLSearchParams(location.search).get('invite');
  mode = mode || (invite ? 'invite' : 'login');
  if (mode === 'forgot' || mode === 'reset') return renderPasswordScreen(mode);
  S.authMode = mode;
  $('#app').innerHTML = html`<div class="auth-page">
    ${authArt()}
    <div class="auth-box">
      <div class="row" style="margin-bottom:35px">
        <span class="logoicon">f</span><span class="brandword">feffel<i>.</i></span>
      </div>
      <h2>
        ${mode === 'login'
          ? 'Welcome back.'
          : mode === 'invite'
            ? 'Join your team.'
            : 'Make room for good work.'}
      </h2>
      <p class="intro">
        ${mode === 'login'
          ? 'Your next great post is waiting.'
          : mode === 'invite'
            ? 'Accept your invitation to start collaborating.'
            : 'Create your organisation. Bring your whole team.'}
      </p>
      <form id="auth-form">
        <div id="auth-error">
          ${mode === 'login' && S.authNotice ? html`<div class="notice">${esc(S.authNotice)}</div>` : ''}
        </div>
        ${mode !== 'login'
          ? '<label for="auth-name">Your name</label><input id="auth-name" name="name" required maxlength="100" autocomplete="name">'
          : ''}${mode === 'register'
          ? '<label for="auth-org">Organisation name</label><input id="auth-org" name="organisation" required maxlength="150" placeholder="Your company or group">'
          : ''}<label for="auth-email">Work email</label
        ><input id="auth-email" name="email" type="email" required autocomplete="email" /><label
          for="auth-password"
          >Password</label
        ><input
          id="auth-password"
          name="password"
          type="password"
          minlength="12"
          maxlength="256"
          required
          autocomplete="${mode === 'login' ? 'current-password' : 'new-password'}"
        />
        <div class="required-note">
          ${mode === 'invite'
            ? 'Already have an account? Use its existing password.'
            : 'At least 12 characters.'}
        </div>
        <button class="primary" type="submit">
          ${mode === 'login'
            ? 'Sign in →'
            : mode === 'invite'
              ? 'Accept invitation →'
              : 'Create organisation →'}
        </button>
      </form>
      ${mode !== 'invite'
        ? html`<div class="auth-switch">
            ${mode === 'login' ? 'New to Feffel?' : 'Already have an account?'}
            <button data-action="auth-mode" data-mode="${mode === 'login' ? 'register' : 'login'}">
              ${mode === 'login' ? 'Create an organisation' : 'Sign in'}
            </button>
          </div>`
        : ''}
      ${mode === 'login'
        ? html`<div class="auth-switch">
            <button data-action="auth-mode" data-mode="forgot">Forgot your password?</button>
          </div>`
        : ''}
    </div>
  </div>`;
  $('#auth-form').onsubmit = async e => {
    e.preventDefault();
    const f = e.currentTarget;
    setBusy(f, true);
    try {
      const b = Object.fromEntries(new FormData(f));
      if (invite) b.token = invite;
      await api(
        mode === 'login'
          ? '/api/login'
          : mode === 'invite'
            ? '/api/accept-invite'
            : '/api/register',
        b,
      );
      if (invite) history.replaceState({}, '', location.pathname);
      S.authNotice = '';
      await boot();
    } catch (err) {
      $('#auth-error').innerHTML = html`<div class="error">${esc(err.message)}</div>`;
    } finally {
      setBusy(f, false);
    }
  };
}
