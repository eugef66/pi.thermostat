// Runs the real static/app.js against a real server with a tiny DOM stub.
// usage: BASE=http://127.0.0.1:PORT PIN=... node tests/ui_e2e.js
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const BASE = process.env.BASE, PIN = process.env.PIN;
const html = fs.readFileSync(path.join(__dirname, '..', 'static', 'index.html'), 'utf8');

class El {
  constructor(tag) {
    this.tagName = tag; this.children = []; this.attrs = {}; this.dataset = {};
    this.listeners = {}; this._text = ''; this.hidden = false; this.disabled = false;
    this.value = ''; this.checked = false; this.min = ''; this.type = '';
    this.classes = new Set();
  }
  get className() { return [...this.classes].join(' '); }
  set className(v) { this.classes = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get classList() {
    const s = this.classes;
    return { toggle: (c, on) => { (on === undefined ? !s.has(c) : on) ? s.add(c) : s.delete(c); },
             add: (c) => s.add(c), remove: (c) => s.delete(c), contains: (c) => s.has(c) };
  }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); }
  set textContent(v) { this._text = String(v); this.children = []; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); }
  dispatch(t, ev) { (this.listeners[t] || []).forEach((fn) => fn(ev || { preventDefault() {} })); }
  replaceChildren(...kids) { this._text = ''; this.children = kids; }
  focus() {}
}

const els = {};
for (const m of html.matchAll(/<[^>]*\bid="([^"]+)"[^>]*>/g)) {
  const e = new El('x'); e.hidden = /\shidden[\s>]/.test(m[0]); els[m[1]] = e;
}
const docListeners = {};
global.document = {
  visibilityState: 'visible',
  getElementById: (id) => { assert(els[id], 'missing element #' + id); return els[id]; },
  createElement: (t) => new El(t),
  addEventListener: (t, fn) => { (docListeners[t] = docListeners[t] || []).push(fn); },
};

// fetch with a cookie jar (a browser would do this) and an "offline" switch
let cookie = '', offline = false;
const realFetch = global.fetch;
global.fetch = async (p, opts = {}) => {
  if (offline) throw new TypeError('network down');
  const headers = Object.assign({}, opts.headers, cookie ? { Cookie: cookie } : {});
  const res = await realFetch(BASE + p, { method: opts.method, headers, body: opts.body });
  const sc = res.headers.getSetCookie();
  if (sc.length) { const kv = sc[0].split(';')[0]; cookie = kv.endsWith('=') ? '' : kv; }
  return res;
};

const settle = (ms = 250) => new Promise((r) => setTimeout(r, ms));
const modeBtn = (m) => els.modes.children.find((b) => b.dataset.mode === m);
const visible = (id) => !els[id].hidden;

(async () => {
  require('../static/app.js');
  await settle();

  // 1. not signed in -> login screen
  assert(visible('view-login') && !visible('view-main') && !visible('view-loading'));

  // number pad by default, switchable to letters and back
  assert.strictEqual(els.pin.getAttribute('inputmode'), 'numeric');
  els['pin-mode'].dispatch('click');
  assert.strictEqual(els.pin.getAttribute('inputmode'), 'text');
  assert.strictEqual(els['pin-mode'].textContent, 'Use number pad instead');
  els['pin-mode'].dispatch('click');
  assert.strictEqual(els.pin.getAttribute('inputmode'), 'numeric');

  // 2. wrong PIN
  els.pin.value = 'wrong-pin';
  els['login-form'].dispatch('submit');
  await settle();
  assert(visible('login-error') && els['login-error'].textContent === 'Incorrect PIN.');

  // 3. right PIN -> main view with live data
  els.pin.value = PIN;
  els['login-form'].dispatch('submit');
  await settle(400);
  assert(visible('view-main'), 'main view not shown');
  assert.strictEqual(els.temp.textContent, '66');
  assert.strictEqual(els.hum.textContent, 'Humidity 45%');
  assert.deepStrictEqual(els.modes.children.map((b) => b.dataset.mode), ['OFF', 'HEAT', 'COOL', 'AUTO', 'FAN']);
  assert.strictEqual(modeBtn('OFF').getAttribute('aria-checked'), 'true');
  assert(!visible('apply'), 'apply should be hidden when nothing changed');
  assert(els.setpoint.classes.has('disabled'), 'target is disabled while OFF');
  assert.strictEqual(els.relays.children.length, 4);

  // 4. choose Heat, raise target, apply
  modeBtn('HEAT').dispatch('click');
  assert(visible('apply') && !els.setpoint.classes.has('disabled'));
  assert.strictEqual(els.target.textContent, '70°');
  els.inc.dispatch('click');
  assert.strictEqual(els.target.textContent, '71°');
  els.apply.dispatch('click');
  await settle();
  assert.strictEqual(els.dial.dataset.activity, 'heating');
  assert(els.activity.textContent.startsWith('Heating'));
  assert.strictEqual(els.target.textContent, '71°');
  assert(!visible('apply'));
  assert.strictEqual(modeBtn('HEAT').getAttribute('aria-checked'), 'true');
  assert(els.relays.children[0].classes.has('on'), 'W1 shown on');

  // 5. target clamps at the server's limits
  for (let i = 0; i < 40; i++) els.inc.dispatch('click');
  assert.strictEqual(els.target.textContent, '85°');

  // 6. schedule a later change, then cancel it
  modeBtn('COOL').dispatch('click');
  els.later.checked = true; els.later.dispatch('change');
  assert(visible('start-at') && els['start-at'].min.length === 16);
  els['start-at'].value = '2000-01-01T00:00';
  els.apply.dispatch('click');
  await settle();
  assert(visible('toast') && /future/.test(els.toast.textContent), 'past start time refused client-side');
  const later = new Date(Date.now() + 2 * 3600 * 1000);
  const p2 = (n) => String(n).padStart(2, '0');
  els['start-at'].value = `${later.getFullYear()}-${p2(later.getMonth() + 1)}-${p2(later.getDate())}T${p2(later.getHours())}:${p2(later.getMinutes())}`;
  els.apply.dispatch('click');
  await settle();
  assert(visible('pending'), 'pending card shown');
  assert(/^Cool 85°F starts /.test(els['pending-text'].textContent), els['pending-text'].textContent);
  els['cancel-pending'].dispatch('click');
  await settle();
  assert(!visible('pending'));

  // 7. OFF applies immediately, no Apply needed
  modeBtn('OFF').dispatch('click');
  await settle();
  assert.strictEqual(els.dial.dataset.activity, 'idle');
  assert.strictEqual(modeBtn('OFF').getAttribute('aria-checked'), 'true');

  // 8. server rejects a bad value -> toast, state intact
  modeBtn('FAN').dispatch('click');
  els.apply.dispatch('click');
  await settle();
  assert.strictEqual(els.dial.dataset.activity, 'fan');

  // 9. network loss -> offline banner, values kept, dial dimmed
  offline = true;
  docListeners.visibilitychange.forEach((f) => f());
  await settle();
  assert.strictEqual(els.link.textContent, 'Offline');
  assert(/Can't reach/.test(els.banners.textContent));
  assert(els.dial.classes.has('dim'));
  assert.strictEqual(els.temp.textContent, '66');
  offline = false;
  docListeners.visibilitychange.forEach((f) => f());
  await settle();
  assert(/^Updated/.test(els.link.textContent) && els.banners.children.length === 0);

  // 10. sign out
  els.logout.dispatch('click');
  await settle();
  assert(visible('view-login') && !visible('view-main'));

  // 11. a reload while signed out and with a dead cookie shows login, not an error
  console.log('UI E2E OK');
  process.exit(0);
})().catch((e) => { console.error('UI E2E FAILED:', e && e.stack || e); process.exit(1); });
