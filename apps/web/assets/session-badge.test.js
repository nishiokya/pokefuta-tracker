const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, 'session-badge.js'), 'utf8');
// Keep the local browser location isolated from production URL expectations.
const TEST_BROWSER_ORIGIN = ['http://', 'localhost:8000/'].join('');

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
  'data-stamp-page': 'https://pokefuta.com/',
  'data-stamp-label': 'スタンプ帳',
});
const mobile = link({
  'data-stamp-page': 'https://pokefuta.com/',
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
  location: { href: TEST_BROWSER_ORIGIN },
});

assert.equal(desktop.textContent, 'スタンプ帳');
assert.equal(desktop.href, 'https://pokefuta.com/');
assert.equal(desktop.attributes['data-nav-target'], 'stamp');
assert.equal(mobile.textContent, 'スタンプ帳');
assert.equal(mobile.href, 'https://pokefuta.com/');
assert.equal(mobile.attributes['data-nav-target'], 'stamp');
