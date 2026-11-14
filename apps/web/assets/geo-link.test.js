const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, 'geo-link.js'), 'utf8');
const ANDROID_CHROME = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36';
const ANDROID_WEBVIEW = 'Mozilla/5.0 (Linux; Android 14; Pixel 8; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/130.0 Mobile Safari/537.36';
const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';
const PLACE_URL = 'https://www.google.com/maps/search/?api=1&query=35.54,139.44';

function link(attributes) {
  return {
    attributes: { ...attributes },
    getAttribute(name) {
      return this.attributes[name] ?? null;
    },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
    },
    removeAttribute(name) {
      delete this.attributes[name];
    },
    closest(selector) {
      assert.equal(selector, 'a[data-geo-label]');
      return 'data-geo-label' in this.attributes ? this : null;
    },
  };
}

function load(userAgent) {
  const listeners = [];
  const window = {};
  const context = {
    window,
    navigator: { userAgent },
    location: { href: 'https://data.pokefuta.com/prefectures/kanagawa/' },
    URL,
    document: {
      addEventListener(type, listener, capture) {
        listeners.push({ type, listener, capture });
      },
    },
  };
  vm.runInNewContext(source, context);
  return {
    window,
    listeners,
    click(target) {
      listeners.forEach(({ listener }) => listener({ target }));
    },
  };
}

// Android の Chrome: 押すと名前付きの geo: に変わり、新しいタブは開かない
{
  const page = load(ANDROID_CHROME);
  assert.equal(page.listeners.length, 1);
  assert.equal(page.listeners[0].capture, true);
  const a = link({ href: PLACE_URL, target: '_blank', 'data-geo-label': 'ポケふた ピカチュウ 座間市 (芹沢公園)' });
  page.click(a);
  assert.equal(
    a.getAttribute('href'),
    'geo:0,0?q=35.54,139.44(' + encodeURIComponent('ポケふた ピカチュウ 座間市 （芹沢公園）') + ')',
  );
  assert.equal(a.getAttribute('target'), null);
}

// 名前の無いリンク・座標でない検索・経路のリンクはそのまま
{
  const page = load(ANDROID_CHROME);
  const noLabel = link({ href: PLACE_URL, target: '_blank' });
  page.click(noLabel);
  assert.equal(noLabel.getAttribute('href'), PLACE_URL);

  const { geoUrl } = page.window.PokefutaGeoLink;
  assert.equal(geoUrl('https://www.google.com/maps/search/?api=1&query=%E4%B8%AD%E6%9D%91%E9%A7%85', 'x'), '');
  assert.equal(geoUrl('https://www.google.com/maps/dir/?api=1&destination=35.54,139.44', 'x'), '');
  assert.equal(geoUrl('https://example.com/maps/search/?api=1&query=35.54,139.44', 'x'), '');
  assert.equal(geoUrl(PLACE_URL, '  '), '');
  assert.equal(geoUrl(PLACE_URL.replace('35.54', '-35.54'), 'a'), 'geo:0,0?q=-35.54,139.44(a)');
}

// iPhone とアプリ内ブラウザ（WebView）は何もしない
for (const ua of [IPHONE, ANDROID_WEBVIEW, ANDROID_CHROME + ' Line/14.0.0']) {
  const page = load(ua);
  assert.equal(page.listeners.length, 0, ua);
  assert.equal(page.window.PokefutaGeoLink, undefined);
}

console.log('geo-link tests passed');
