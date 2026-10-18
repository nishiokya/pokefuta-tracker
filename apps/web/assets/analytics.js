(function () {
  'use strict';

  var MEASUREMENT_ID = 'G-K18NR4GZG2';
  var PRODUCTION_HOSTS = ['data.pokefuta.com'];
  var enabled = PRODUCTION_HOSTS.indexOf(window.location.hostname.toLowerCase()) !== -1;
  var initialized = false;
  // 表示している言語版。/en/・/zh-TW/・/zh-CN/・/ko/ の下ならその言語、ほかは日本語。
  // page_path は言語をまたいで同じ（/top・/map …）なので、言語別に見るときはこれで分ける。
  // GA4 の予約語 language（ブラウザの言語）とは別物。
  // GA4 のカスタムディメンション登録が要る（docs/analytics-page-lang.md）。
  var PAGE_LANGS = ['en', 'zh-TW', 'zh-CN', 'ko'];
  var langMatch = window.location.pathname.match(/^\/([^/]+)\//);
  var pageLang = langMatch && PAGE_LANGS.indexOf(langMatch[1]) !== -1 ? langMatch[1] : 'ja';
  var context = { site_type: 'map', page_lang: pageLang };

  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () {
    if (enabled) window.dataLayer.push(arguments);
  };

  function loadGtag() {
    if (document.querySelector('script[data-pokefuta-ga4]')) return;
    var script = document.createElement('script');
    script.async = true;
    script.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(MEASUREMENT_ID);
    script.dataset.pokefutaGa4 = 'true';
    document.head.appendChild(script);
  }

  function init(params) {
    var config = Object.assign({ site_type: 'map', page_lang: pageLang }, params || {});
    context = Object.assign({}, config);
    delete context.send_page_view;
    if (!enabled) return false;

    loadGtag();
    if (!initialized) {
      window.gtag('js', new Date());
      window.gtag('set', 'linker', {
        domains: ['data.pokefuta.com', 'pokefuta.com'],
        accept_incoming: true
      });
      // trackEvent を通らない gtag('event', ...) にも付ける
      window.gtag('set', { page_lang: pageLang });
      initialized = true;
    }

    window.gtag('config', MEASUREMENT_ID, config);
    return true;
  }

  function setContext(params) {
    context = Object.assign({}, context, params || {});
    delete context.send_page_view;
  }

  function trackEvent(name, params) {
    if (!enabled) return;
    window.gtag('event', name, Object.assign({}, context, params || {}));
  }

  // data-track 属性を持つ要素のクリックを送る。生成ページごとに同じ委譲を直書きしないため。
  // defaults はページ共通の引数（event_category・surface など）。data-surface があればそちらを優先する。
  // options.detail: 掲載位置・コンテンツID・写真状態（data-position / data-content-id / data-photo-state）も送る
  function bindClickTracking(defaults, options) {
    var base = defaults || {};
    var detail = Boolean(options && options.detail);
    document.addEventListener('click', function (event) {
      var link = event.target.closest && event.target.closest('[data-track]');
      if (!link) return;
      var data = link.dataset;
      var params = { destination: data.destination || '' };
      if (detail) {
        params.position = Number(data.position || 0);
        params.content_id = data.contentId || '';
        params.photo_state = data.photoState || '';
      }
      if (data.surface) params.surface = data.surface;
      trackEvent(data.track, Object.assign({}, base, params));
      // 改名したイベントを旧名でも送り、過去データと並べて見られるようにする
      if (data.legacyTrack) {
        trackEvent(data.legacyTrack, Object.assign({}, base, {
          destination: params.destination,
          surface: params.surface || base.surface
        }));
      }
    });
  }

  window.PokefutaAnalytics = {
    enabled: enabled,
    pageLang: pageLang,
    init: init,
    setContext: setContext,
    trackEvent: trackEvent,
    bindClickTracking: bindClickTracking
  };
  window.trackEvent = trackEvent;
})();
