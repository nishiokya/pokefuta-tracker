/* Run with node --test; no network or browser dependency. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(`${__dirname}/character-work-map.js`, 'utf8');

function element(tag = 'div') {
  return {
    tag, children: [], value: '', textContent: '', events: {},
    append(...items) { this.children.push(...items); },
    appendChild(item) { this.children.push(item); },
    addEventListener(name, callback) { this.events[name] = callback; },
  };
}

const points = [
  { lat: 35, lng: 137, name: '<unsafe>', address: '<address>', anchor: 'spot-a', region: '中部',
    photo_url: 'https://example.com/a.jpg', photo_source_url: 'https://pokefuta.com/design-manholes/a' },
  { lat: 43, lng: 142, name: '写真なし', address: '北海道', anchor: 'spot-b', region: '北海道・東北', photo_url: '' },
];

function run(data = points, { leaflet = true, filters = true, defer = false } = {}) {
  const ids = Object.fromEntries(['cw-map', 'cw-map-data', 'cw-map-status', 'cw-map-region', 'cw-map-photos', 'cw-map-count']
    .map(id => [id, element()]));
  ids['cw-map-data'].textContent = JSON.stringify(data);
  if (!filters) for (const id of ['cw-map-region', 'cw-map-photos', 'cw-map-count']) delete ids[id];
  const markers = [], bounds = [], tileEvents = {};
  const map = { fitBounds(b, options) { assert.ok(b.length); bounds.push({ b, options }); } };
  const L = {
    map() { return map; },
    tileLayer() { return { addTo() { return this; }, on(event, cb) { tileEvents[event] = cb; } }; },
    marker(coords, options) {
      const marker = {
        options: { ...options, icon: 'default' }, icon: 'default', visible: false,
        bindPopup(popup) { this.popup = popup; return this; },
        addTo() { this.visible = true; return this; },
        remove() { this.visible = false; },
        setIcon(icon) { this.icon = icon; return this; },
      };
      markers.push(marker); return marker;
    },
    divIcon(options) { return options; },
    featureGroup(items) { return { getBounds() { return items; } }; },
  };
  let observer;
  const window = leaflet ? { L } : {};
  const context = { window, L, document: { getElementById: id => ids[id], createElement: element } };
  if (defer) {
    context.IntersectionObserver = class {
      constructor(callback) { observer = this; this.callback = callback; }
      observe() {}
      disconnect() { this.disconnected = true; }
    };
    window.IntersectionObserver = context.IntersectionObserver;
  }
  vm.runInNewContext(source, context);
  return { ids, markers, bounds, tileEvents, get observer() { return observer; },
    change(id, value) { ids[id].value = value; ids[id].events.change(); } };
}

test('region and photo filters combine, report zero matches, and restore all markers', () => {
  const app = run();
  assert.equal(app.markers.length, 2);
  assert.equal(app.ids['cw-map-region'].children.length, 2);
  app.change('cw-map-photos', 'with');
  assert.deepEqual(app.markers.map(m => m.visible), [true, false]);
  app.change('cw-map-region', '北海道・東北');
  assert.deepEqual(app.markers.map(m => m.visible), [false, false]);
  assert.equal(app.ids['cw-map-count'].textContent, '0 / 2枚を表示');
  assert.match(app.ids['cw-map-status'].textContent, /条件に合う場所がありません/);
  assert.equal(app.bounds.at(-1).b.length, 2);
  app.change('cw-map-photos', 'without');
  assert.deepEqual(app.markers.map(m => m.visible), [false, true]);
  app.change('cw-map-region', '');
  app.change('cw-map-photos', 'all');
  assert.deepEqual(app.markers.map(m => m.visible), [true, true]);
  assert.equal(app.ids['cw-map-count'].textContent, '2 / 2枚を表示');
  assert.doesNotMatch(app.ids['cw-map-status'].textContent, /条件に合う場所がありません/);
});

test('photo marker uses the circular class and broken images fall back to the standard pin', () => {
  const app = run();
  const image = app.markers[0].icon.html;
  assert.equal(image.className, 'cw-map-photo-marker');
  assert.equal(image.alt, '<unsafe>');
  assert.equal(app.markers[1].icon, 'default');
  image.onerror();
  assert.equal(app.markers[0].icon, 'default');
  assert.equal(app.markers[0].visible, true);
});

test('popups preserve local and dedicated map links and add public photo-library links', () => {
  const app = run([...points, { ...points[0], href: '../../gmanhole_map.html#gundam-1', photo_source_url: '' }]);
  assert.equal(app.markers[0].popup.children[0].textContent, '<unsafe>');
  assert.equal(app.markers[0].popup.children[2].href, '#spot-a');
  assert.equal(app.markers[0].popup.children[3].href, points[0].photo_source_url);
  assert.equal(app.markers[1].popup.children.length, 3);
  assert.equal(app.markers[2].popup.children[2].href, '../../gmanhole_map.html#gundam-1');
  assert.equal(app.markers[2].popup.children.length, 3);
});

test('one point, legacy pages without filters, no coordinates, and missing Leaflet degrade safely', () => {
  const single = run([points[0]], { filters: false });
  assert.equal(single.bounds[0].options.maxZoom, 14);
  const empty = run([]);
  assert.equal(empty.markers.length, 0);
  assert.match(empty.ids['cw-map-status'].textContent, /座標を確認中/);
  const missing = run(points, { leaflet: false });
  assert.equal(missing.markers.length, 0);
  assert.match(missing.ids['cw-map-status'].textContent, /地図を読み込めませんでした/);
  single.tileEvents.tileerror();
  assert.match(single.ids['cw-map-status'].textContent, /背景地図の一部/);
});

test('map initialization waits until it approaches the viewport', () => {
  const app = run(points, { defer: true });
  assert.equal(app.markers.length, 0);
  app.observer.callback([{ isIntersecting: false }]);
  assert.equal(app.markers.length, 0);
  app.observer.callback([{ isIntersecting: true }]);
  assert.equal(app.markers.length, 2);
  assert.equal(app.observer.disconnected, true);
});
