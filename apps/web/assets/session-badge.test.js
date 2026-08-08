const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, 'session-badge.js'), 'utf8');
// Keep the local browser location isolated from production URL expectations.
const TEST_BROWSER_ORIGIN = ['http://', 'localhost:8000/'].join('');

const LOGIN_URL = 'https://pokefuta.com/login?from=data';

function element(attributes) {
  return {
    attributes: { ...attributes },
    href: LOGIN_URL,
    textContent: '',
    getAttribute(name) {
      return this.attributes[name] ?? null;
    },
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
    removeAttribute(name) {
      delete this.attributes[name];
    },
    get hidden() {
      return 'hidden' in this.attributes;
    },
  };
}

/** ヘッダーに注入される認証まわりの DOM を最小限で再現する */
function chrome() {
  const guest = element({});
  const authed = element({ hidden: '' });
  const name = element({});
  const loginLink = element({ 'data-login-link': '' });
  const stampTab = element({ 'data-login-link': '' });

  const document = {
    cookie: '',
    readyState: 'complete',
    addEventListener() {},
    querySelector(selector) {
      if (selector === '[data-auth-guest]') return guest;
      if (selector === '[data-auth-user]') return authed;
      if (selector === '[data-auth-name]') return name;
      return null;
    },
    querySelectorAll(selector) {
      if (selector === '[data-login-link]') return [loginLink, stampTab];
      return [];
    },
  };

  return { guest, authed, name, loginLink, stampTab, document };
}

function run(document) {
  vm.runInNewContext(source, {
    URL,
    Uint8Array,
    TextDecoder,
    atob,
    document,
    location: { href: TEST_BROWSER_ORIGIN },
  });
}

// ── ログイン中: 表示名のピルに切り替わる ───────────────────
{
  const dom = chrome();
  const session = {
    user: {
      id: 'user-1',
      email: 'fallback@example.com',
      user_metadata: { display_name: 'たこトレーナー' },
    },
  };
  dom.document.cookie = `sb-kbwzwgsjqvflgfauzcpn-auth-token=${encodeURIComponent(JSON.stringify(session))}`;
  run(dom.document);

  assert.equal(dom.name.textContent, 'たこトレーナー');
  assert.equal(dom.authed.hidden, false, 'ログイン中は認証ピルを出す');
  assert.equal(dom.guest.hidden, true, 'ログイン中はログイン/新規登録を隠す');
  // ログイン中はナビ項目のラベルを書き換えない（認証とナビを分離した）
  assert.equal(dom.stampTab.textContent, '');
  assert.equal(dom.stampTab.href, LOGIN_URL);
}

// ── display_name が無ければメールのローカル部を使う ────────
{
  const dom = chrome();
  const session = { user: { id: 'user-2', email: 'takoyaki@example.com' } };
  dom.document.cookie = `sb-kbwzwgsjqvflgfauzcpn-auth-token=${encodeURIComponent(JSON.stringify(session))}`;
  run(dom.document);

  assert.equal(dom.name.textContent, 'takoyaki');
}

// ── 未ログイン: 戻り先を redirect に積む ────────────────────
{
  const dom = chrome();
  run(dom.document);

  assert.equal(dom.guest.hidden, false, '未ログインはログイン/新規登録を出す');
  assert.equal(dom.authed.hidden, true, '未ログインは認証ピルを隠す');
  for (const link of [dom.loginLink, dom.stampTab]) {
    const url = new URL(link.href);
    assert.equal(url.searchParams.get('redirect'), TEST_BROWSER_ORIGIN);
  }
}

console.log('session-badge: すべてのケースが通過');
