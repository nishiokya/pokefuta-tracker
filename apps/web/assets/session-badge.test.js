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
  const avatar = element({ 'data-auth-avatar': '' });
  avatar.textContent = '👤';
  avatar.children = [];
  avatar.appendChild = function (child) {
    this.children.push(child);
  };
  const loginLink = element({ 'data-login-link': '' });
  const stampTab = element({
    'data-login-link': '',
    'data-stamp-page': 'https://pokefuta.com/visits?from=data',
  });

  const document = {
    cookie: '',
    readyState: 'complete',
    addEventListener() {},
    querySelector(selector) {
      if (selector === '[data-auth-guest]') return guest;
      if (selector === '[data-auth-user]') return authed;
      if (selector === '[data-auth-name]') return name;
      if (selector === '[data-auth-avatar]') return avatar;
      return null;
    },
    createElement(tag) {
      return { tagName: tag.toUpperCase() };
    },
    querySelectorAll(selector) {
      if (selector === '[data-login-link]') return [loginLink, stampTab];
      return [];
    },
  };

  return { guest, authed, name, avatar, loginLink, stampTab, document };
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
  // ただし遷移先はスタンプ帳へ。ログイン済みなのにログイン画面へ送らない
  assert.equal(dom.stampTab.href, 'https://pokefuta.com/visits?from=data');
  // data-stamp-page を持たないリンクはそのまま
  assert.equal(dom.loginLink.href, LOGIN_URL);
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
  // 認証ボタンは現在ページへ戻す
  assert.equal(new URL(dom.loginLink.href).searchParams.get('redirect'), TEST_BROWSER_ORIGIN);
  // ナビ項目は「本来行きたかった場所」へ。現在ページを積むと
  // ログイン後に図鑑へ戻され、スタンプ帳へ行くのにもう一度タップが要る
  assert.equal(
    new URL(dom.stampTab.href).searchParams.get('redirect'),
    'https://pokefuta.com/visits?from=data'
  );
}

// ── 写真館で選んだアイコン（pf_avatar）: 本人のものだけ出す ────────
{
  const uid = '11111111-1111-4111-8111-111111111111';
  const photo = '22222222-2222-4222-8222-222222222222';
  const session = { user: { id: uid, user_metadata: { display_name: 'たこ' } } };
  const auth = `sb-kbwzwgsjqvflgfauzcpn-auth-token=${encodeURIComponent(JSON.stringify(session))}`;

  const dom = chrome();
  dom.document.cookie = `${auth}; pf_avatar=${uid}.${photo}`;
  run(dom.document);
  assert.equal(dom.avatar.children.length, 1, 'アイコンの画像を入れる');
  assert.equal(dom.avatar.children[0].src, `https://pokefuta.com/api/photo/${photo}?size=small&strict=1`);
  assert.equal(dom.avatar.textContent, '');

  // 別の人のクッキー（同じブラウザでログインし直した）は使わない
  const other = chrome();
  other.document.cookie = `${auth}; pf_avatar=33333333-3333-4333-8333-333333333333.${photo}`;
  run(other.document);
  assert.equal(other.avatar.children.length, 0);
  assert.equal(other.avatar.textContent, '👤');

  // 壊れた値・未ログインでは何もしない
  const broken = chrome();
  broken.document.cookie = `${auth}; pf_avatar=${uid}.not-a-uuid`;
  run(broken.document);
  assert.equal(broken.avatar.children.length, 0);
  const guest = chrome();
  guest.document.cookie = `pf_avatar=${uid}.${photo}`;
  run(guest.document);
  assert.equal(guest.avatar.children.length, 0);
}

console.log('session-badge: すべてのケースが通過');
