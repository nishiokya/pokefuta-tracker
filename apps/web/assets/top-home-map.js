/* 図鑑トップ（日本語・英語）のデスクトップ用ヒーロー地図。
 *
 * - 幅 960px 以上のときだけ Leaflet を読み込む。スマホでは Leaflet 本体も地図タイルも通信しない
 * - ピンと件数は生成時に #home-map-data へ埋め込まれた JSON を使う（ndjson / top-feed を取りに行かない）
 * - リサイズでスマホ幅→デスクトップ幅になったら一度だけ初期化する。二重初期化・リスナーの重複登録はしない
 * - 県ピンは map.html の都道府県絞り込みへ遷移する（地図は装飾ではなく全画面マップへの入口）
 */
(function () {
  'use strict';
  var wrap = document.getElementById('home-map-wrap');
  var canvas = document.getElementById('home-map');
  var dataEl = document.getElementById('home-map-data');
  if (!wrap || !canvas || !dataEl || !window.matchMedia) return;

  var LEAFLET_CSS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
  var LEAFLET_CSS_SRI = 'sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=';
  var LEAFLET_JS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
  var LEAFLET_JS_SRI = 'sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=';
  // 本州〜沖縄が収まる範囲。左側の説明パネルの分だけ右に寄せる
  var JAPAN_BOUNDS = [[25.8, 127.4], [45.6, 146.0]];

  var desktop = window.matchMedia('(min-width: 960px)');
  var state = 'idle'; // idle → loading → ready
  var map = null;

  function loadLeaflet(done) {
    if (window.L) { done(); return; }
    var css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = LEAFLET_CSS;
    css.integrity = LEAFLET_CSS_SRI;
    css.crossOrigin = '';
    document.head.appendChild(css);
    var script = document.createElement('script');
    script.src = LEAFLET_JS;
    script.integrity = LEAFLET_JS_SRI;
    script.crossOrigin = '';
    script.onload = done;
    document.head.appendChild(script);
  }

  function panelWidth() {
    var copy = document.querySelector('#home-hero .home-hero__copy');
    return copy ? copy.getBoundingClientRect().width + 48 : 0;
  }

  function fit() {
    map.fitBounds(JAPAN_BOUNDS, { paddingTopLeft: [panelWidth(), 16], paddingBottomRight: [16, 40] });
  }

  function init() {
    var pins;
    try { pins = JSON.parse(dataEl.textContent).pins || []; } catch (e) { pins = []; }
    map = L.map(canvas, {
      zoomControl: false, scrollWheelZoom: false, zoomSnap: 0.25,
      attributionControl: false, keyboard: true,
    });
    // 左上は説明パネルが重なるので、ズームは右上に置く
    L.control.zoom({ position: 'topright' }).addTo(map);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 12 }).addTo(map);
    fit();
    pins.forEach(function (pin) {
      var icon = L.divIcon({
        html: '<span class="prefecture-overview-name"></span><span class="prefecture-overview-count"></span>',
        className: 'prefecture-overview-marker', iconSize: null,
      });
      var marker = L.marker([pin.lat, pin.lng], { icon: icon, title: pin.title, alt: pin.title, keyboard: true }).addTo(map);
      var el = marker.getElement();
      if (el) {
        el.querySelector('.prefecture-overview-name').textContent = pin.label;
        el.querySelector('.prefecture-overview-count').textContent = pin.count;
      }
      marker.on('click', function () {
        if (window.trackEvent) trackEvent('click_map_pin', { surface: 'top_map_hero', prefecture: pin.prefecture });
        location.href = 'map.html?pref=' + encodeURIComponent(pin.prefecture) + '&view=map';
      });
    });
    wrap.classList.add('is-ready');
    state = 'ready';
  }

  function onChange() {
    if (!desktop.matches) return;
    if (state === 'idle') {
      state = 'loading';
      loadLeaflet(init);
    } else if (state === 'ready') {
      // 非表示（スマホ幅）の間にサイズが変わっているので測り直す
      map.invalidateSize();
      fit();
    }
  }

  // 地図の高さは画面の高さで変わるので、窓の大きさが変わったら日本全体を収め直す
  var resizeTimer = null;
  window.addEventListener('resize', function () {
    if (state !== 'ready' || !desktop.matches) return;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { map.invalidateSize(); fit(); }, 200);
  });

  if (desktop.addEventListener) desktop.addEventListener('change', onChange);
  else if (desktop.addListener) desktop.addListener(onChange); // Safari < 14
  onChange();
})();
