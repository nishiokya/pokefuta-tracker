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

  window.PokefutaAnalytics = {
    enabled: enabled,
    init: init,
    setContext: setContext,
    trackEvent: trackEvent
  };
  window.trackEvent = trackEvent;
})();
