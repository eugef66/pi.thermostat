'use strict';
(function () {
  // ------------------------------------------------------------ pure helpers
  var USES_TARGET = { HEAT: true, COOL: true, AUTO: true };
  var MODE_LABEL = { OFF: 'Off', HEAT: 'Heat', COOL: 'Cool', AUTO: 'Auto', FAN: 'Fan' };

  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }
  function stepTarget(t, dir, lo, hi) { return clamp(Math.round(t) + dir, lo, hi); }
  function fmtNum(n) { return Number.isInteger(n) ? String(n) : n.toFixed(1); }
  function ageText(s) {
    if (s < 5) return 'just now';
    if (s < 60) return s + 's ago';
    if (s < 3600) return Math.floor(s / 60) + ' min ago';
    return Math.floor(s / 3600) + ' h ago';
  }
  function retryText(sec) {
    var n = parseInt(sec, 10);
    if (!n || n < 1) return 'a little while';
    if (n < 90) return n + ' seconds';
    return Math.ceil(n / 60) + ' minutes';
  }
  function isDirty(draft, status) {
    if (!status) return false;
    if (draft.mode !== status.mode) return true;
    return !!USES_TARGET[draft.mode] && draft.target !== status.target;
  }
  function buildSetBody(draft, startIso) {
    var body = { mode: draft.mode };
    if (USES_TARGET[draft.mode]) body.target = draft.target;
    if (startIso) body.start_at = startIso;
    return body;
  }
  function activityText(status) {
    var base = { heating: 'Heating', cooling: 'Cooling', fan: 'Fan', idle: 'Idle' }[status.activity] || 'Idle';
    if (status.activity === 'heating' && status.relays && status.relays.heat2) base += ' · stage 2';
    return base;
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function localInputValue(d) {
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
           'T' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { clamp: clamp, stepTarget: stepTarget, fmtNum: fmtNum, ageText: ageText,
      retryText: retryText, isDirty: isDirty, buildSetBody: buildSetBody,
      activityText: activityText, localInputValue: localInputValue };
  }
  if (typeof document === 'undefined') return;

  // --------------------------------------------------------------- app state
  var POLL_MS = 5000;
  var S = {
    caps: null, status: null, csrf: null, draft: { mode: 'OFF', target: 70 },
    online: true, lastOk: 0, busy: false, timer: null, tick: null
  };

  function $(id) { return document.getElementById(id); }
  function show(view) {
    ['view-loading', 'view-login', 'view-main'].forEach(function (v) { $(v).hidden = (v !== view); });
  }
  function toast(msg) {
    var t = $('toast');
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(function () { t.hidden = true; }, 6000);
  }

  // --------------------------------------------------------------------- api
  function api(method, path, body) {
    var opts = { method: method, headers: {}, credentials: 'same-origin', cache: 'no-store' };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    if (method !== 'GET' && S.csrf) opts.headers['X-CSRF-Token'] = S.csrf;
    return fetch(path, opts).then(function (res) {
      var retry = res.headers.get('Retry-After');
      var parse = res.status === 204 ? Promise.resolve(null) : res.json().catch(function () { return null; });
      return parse.then(function (data) {
        if (!res.ok) {
          var e = (data && data.error) || {};
          throw { status: res.status, code: e.code, message: e.message || res.statusText, retryAfter: retry };
        }
        return data;
      });
    }, function () { throw { network: true, message: 'Cannot reach the thermostat' }; });
  }

  // -------------------------------------------------------------- rendering
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function renderBanners() {
    var box = $('banners');
    var items = [];
    var st = S.status;
    if (st && st.fault) items.push(['danger', st.fault.message]);
    if (!S.online) items.push(['warn', "Can't reach the thermostat. Showing the last known values."]);
    else if (st && st.stale) items.push(['warn', "The controller hasn't reported recently, so these values may be out of date."]);
    box.replaceChildren.apply(box, items.map(function (i) {
      var b = el('div', 'banner ' + i[0], i[1]);
      if (i[0] === 'danger') b.setAttribute('role', 'alert');
      return b;
    }));
  }

  function renderLink() {
    var l = $('link');
    if (!S.online) { l.textContent = 'Offline'; l.className = 'link offline'; return; }
    l.className = 'link';
    l.textContent = S.lastOk ? 'Updated ' + ageText(Math.round((Date.now() - S.lastOk) / 1000)) : '';
  }

  function renderModes() {
    var box = $('modes');
    var modes = S.caps.modes;
    if (box.children.length !== modes.length) {       // build once, then only update
      box.replaceChildren.apply(box, modes.map(function (m) {
        var b = el('button', 'mode', MODE_LABEL[m] || m);
        b.type = 'button';
        b.dataset.mode = m;
        b.setAttribute('role', 'radio');
        b.addEventListener('click', function () { onMode(m); });
        return b;
      }));
    }
    for (var i = 0; i < modes.length; i++) {
      box.children[i].setAttribute('aria-checked', modes[i] === S.draft.mode ? 'true' : 'false');
    }
  }

  function renderSetpoint() {
    var uses = !!USES_TARGET[S.draft.mode];
    $('setpoint').classList.toggle('disabled', !uses);
    $('dec').disabled = !uses; $('inc').disabled = !uses;
    $('target').textContent = uses ? fmtNum(S.draft.target) + '°' : '--';
  }

  function renderPending() {
    var p = S.status && S.status.pending;
    $('pending').hidden = !p;
    if (!p) return;
    var when = new Date(p.start_at);
    var whenText = isNaN(when) ? p.start_at :
      when.toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
    var what = MODE_LABEL[p.mode] || p.mode;
    if (USES_TARGET[p.mode]) what += ' ' + fmtNum(p.target) + '°F';
    $('pending-text').textContent = what + ' starts ' + whenText;
  }

  function renderRelays() {
    var st = S.status, c = S.caps;
    var list = [['heat1', 'W1 heat', true], ['heat2', 'W2 heat 2', c.heat_stage_2],
                ['cool', 'Y cool', c.cool], ['fan', 'G fan', c.fan]];
    var ul = $('relays');
    ul.replaceChildren.apply(ul, list.filter(function (r) { return r[2]; }).map(function (r) {
      var on = st.relays[r[0]];
      return el('li', on ? 'on' : '', r[1] + (on ? ' · on' : ' · off'));
    }));
  }

  function renderApply() {
    var dirty = isDirty(S.draft, S.status);
    var later = $('later').checked;
    $('apply').hidden = !(dirty || later);
    $('apply').disabled = S.busy;
    $('schedule').hidden = S.draft.mode === 'OFF';
    if (S.draft.mode === 'OFF') { $('later').checked = false; $('start-at').hidden = true; }
  }

  function render() {
    var st = S.status;
    if (!st) return;
    $('temp').textContent = st.temperature === null ? '--' : fmtNum(st.temperature);
    $('hum').textContent = st.humidity === null ? 'Humidity --' : 'Humidity ' + fmtNum(st.humidity) + '%';
    $('dial').dataset.activity = st.activity;
    $('dial').classList.toggle('dim', !S.online || st.stale);
    $('activity').textContent = activityText(st);
    renderBanners(); renderLink(); renderPending(); renderRelays();
    renderModes(); renderSetpoint(); renderApply();
  }

  function adoptServerDraft() {
    if (!isDirty(S.draft, S.status)) S.draft = { mode: S.status.mode, target: S.status.target };
  }

  // ------------------------------------------------------------------ actions
  function applyStatus(st) {
    S.status = st; S.online = true; S.lastOk = Date.now();
    adoptServerDraft();
    render();
  }

  function toLogin(msg) {
    stopPolling();
    S.status = null; S.csrf = null;
    $('pin').value = '';
    var err = $('login-error');
    err.hidden = !msg; err.textContent = msg || '';
    show('view-login');
    $('pin').focus();
  }

  function refresh() {
    return api('GET', '/api/v1/status').then(applyStatus, function (e) {
      if (e.status === 401) return toLogin('Session ended. Please sign in again.');
      S.online = false;
      if (S.status) render();
    });
  }

  function startPolling() {
    stopPolling();
    S.timer = setInterval(function () { if (document.visibilityState === 'visible') refresh(); }, POLL_MS);
    S.tick = setInterval(function () { if (S.status) { renderLink(); } }, 1000);
  }
  function stopPolling() { clearInterval(S.timer); clearInterval(S.tick); }

  function send(method, path, body) {
    if (S.busy) return Promise.resolve();
    S.busy = true; renderApply();
    return api(method, path, body).then(function (st) {
      applyStatus(st);
      return true;
    }, function (e) {
      if (e.status === 401) toLogin('Session ended. Please sign in again.');
      else toast(e.message || 'Something went wrong');
      return false;
    }).then(function (ok) { S.busy = false; if (S.status) renderApply(); return ok; });
  }

  function onMode(m) {
    if (m === 'OFF') {                       // turning off never waits for "Apply"
      S.draft = { mode: 'OFF', target: S.draft.target };
      return send('POST', '/api/v1/set', { mode: 'OFF' });
    }
    S.draft.mode = m;
    render();
  }

  function onStep(dir) {
    if (!USES_TARGET[S.draft.mode]) return;
    S.draft.target = stepTarget(S.draft.target, dir, S.caps.setpoint_min, S.caps.setpoint_max);
    render();
  }

  function onApply() {
    var startIso = null;
    if ($('later').checked) {
      var v = $('start-at').value;
      var d = v ? new Date(v) : null;
      if (!d || isNaN(d) || d.getTime() <= Date.now()) return toast('Pick a start time in the future');
      startIso = d.toISOString();
    }
    return send('POST', '/api/v1/set', buildSetBody(S.draft, startIso)).then(function (ok) {
      if (ok) { $('later').checked = false; $('start-at').hidden = true; renderApply(); }
    });
  }

  function onLater() {
    var on = $('later').checked;
    var t = $('start-at');
    t.hidden = !on;
    if (on) {
      var soon = new Date(Date.now() + 3600000);
      soon.setMinutes(0, 0, 0);
      t.min = localInputValue(new Date(Date.now() + 60000));
      t.value = localInputValue(soon);
    }
    renderApply();
  }

  // The secret is usually a PIN, so start with the number pad; a passphrase user
  // can switch to the full keyboard, and the choice is remembered on this device.
  function setPinMode(numeric, remember) {
    $('pin').setAttribute('inputmode', numeric ? 'numeric' : 'text');
    $('pin-mode').textContent = numeric ? 'Use letters instead' : 'Use number pad instead';
    if (remember) { try { localStorage.setItem('pinmode', numeric ? 'n' : 't'); } catch (e) { /* private mode */ } }
  }
  function initPinMode() {
    var saved = null;
    try { saved = localStorage.getItem('pinmode'); } catch (e) { /* ignore */ }
    setPinMode(saved !== 't', false);
  }

  function onLogin(ev) {
    ev.preventDefault();
    var btn = $('login-btn');
    btn.disabled = true;
    api('POST', '/api/v1/login', { pin: $('pin').value }).then(function (r) {
      S.csrf = r.csrf_token;
      return enter();
    }, function (e) {
      var err = $('login-error');
      err.hidden = false;
      if (e.status === 401) err.textContent = 'Incorrect PIN.';
      else if (e.status === 429) err.textContent = 'Too many attempts. Try again in ' + retryText(e.retryAfter) + '.';
      else if (e.code === 'not_configured') err.textContent = 'No PIN is set yet. Run "set-pin" on the thermostat.';
      else err.textContent = e.message || 'Could not sign in.';
    }).then(function () { btn.disabled = false; });
  }

  function onLogout() {
    api('POST', '/api/v1/logout').then(null, function () {}).then(function () { toLogin(''); });
  }

  // -------------------------------------------------------------------- start
  function enter() {
    return Promise.all([api('GET', '/api/v1/capabilities'), api('GET', '/api/v1/status')]).then(function (r) {
      S.caps = r[0];
      S.draft = { mode: r[1].mode, target: r[1].target };
      show('view-main');
      applyStatus(r[1]);
      startPolling();
    });
  }

  function boot() {
    $('retry-load').hidden = true;
    $('loading-text').textContent = 'Loading…';
    show('view-loading');
    api('GET', '/api/v1/session').then(function (s) {
      if (!s.authenticated) return toLogin('');
      S.csrf = s.csrf_token;
      return enter();
    }).then(null, function (e) {
      if (e && e.status === 401) return toLogin('');
      $('loading-text').textContent = "Can't reach the thermostat.";
      $('retry-load').hidden = false;
    });
  }

  initPinMode();
  $('pin-mode').addEventListener('click', function () {
    setPinMode($('pin').getAttribute('inputmode') !== 'numeric', true);
    $('pin').focus();
  });
  $('login-form').addEventListener('submit', onLogin);
  $('logout').addEventListener('click', onLogout);
  $('dec').addEventListener('click', function () { onStep(-1); });
  $('inc').addEventListener('click', function () { onStep(1); });
  $('apply').addEventListener('click', onApply);
  $('later').addEventListener('change', onLater);
  $('cancel-pending').addEventListener('click', function () { send('DELETE', '/api/v1/pending'); });
  $('retry-load').addEventListener('click', boot);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && S.status) refresh();
  });
  boot();
})();
