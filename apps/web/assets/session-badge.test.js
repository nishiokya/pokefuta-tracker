const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, 'session-badge.js'), 'utf8');

function link(attributes) {
  return {
    attributes: { ...attributes },
    href: 'https://pokefuta.com/login?from=data',
    textContent: 'ログイン',
    getAttribute(name) {
      return this.attributes[name] ?? null;
    },
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
  };
}

const desktop = link({
  'data-profile-page': 'https://pokefuta.com/profile',
  'data-stamp-label': 'スタンプ帳',
});
const mobile = link({
  'data-stamp-page': 'https://pokefuta.com/visits',
  'data-stamp-label': 'スタンプ帳',
});
const session = {
  user: {
    id: 'user-1',
    email: 'fallback@example.com',
    user_metadata: { display_name: 'たこトレーナー' },
  },
};
const cookie = `sb-kbwzwgsjqvflgfauzcpn-auth-token=${encodeURIComponent(JSON.stringify(session))}`;

vm.runInNewContext(source, {
  URL,
  Uint8Array,
  TextDecoder,
  atob,
  document: {
    cookie,
    readyState: 'complete',
    querySelectorAll: () => [desktop, mobile],
  },
  location: { href: 'http://localhost:8000/' },
});

assert.equal(desktop.textContent, 'たこトレーナー');
assert.equal(desktop.href, 'https://pokefuta.com/profile');
assert.equal(desktop.attributes['data-nav-target'], 'profile');
assert.equal(mobile.textContent, 'スタンプ帳');
assert.equal(mobile.href, 'https://pokefuta.com/visits');
assert.equal(mobile.attributes['data-nav-target'], 'stamp');
