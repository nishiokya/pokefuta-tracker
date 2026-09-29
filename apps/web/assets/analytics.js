(function () {
  'use strict';

  var MEASUREMENT_ID = 'G-K18NR4GZG2';
  var PRODUCTION_HOSTS = ['data.pokefuta.com'];
  var enabled = PRODUCTION_HOSTS.indexOf(window.location.hostname.toLowerCase()) !== -1;
  var initialized = false;
  var context = { site_type: 'map' };

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
    var config = Object.assign({ site_type: 'map' }, params || {});
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
    init: init,
    setContext: setContext,
    trackEvent: trackEvent,
    bindClickTracking: bindClickTracking
  };
  window.trackEvent = trackEvent;
})();
