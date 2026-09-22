(function () {
  'use strict';

  var MOBILE_QUERY = '(max-width: 1023px)';
  var SURFACE = 'mobile_bottom_nav';

  function track(name, params) {
    if (typeof window.trackEvent === 'function') {
      window.trackEvent(name, params);
    }
  }

  function init() {
    var nav = document.querySelector('.site-tabs[data-nav-variant]');
    if (!nav || !window.matchMedia(MOBILE_QUERY).matches) return;

    var variant = nav.dataset.navVariant;
    var tabs = nav.querySelectorAll('[data-nav-item][data-nav-position]');

    track('view_navigation', {
      surface: SURFACE,
      nav_variant: variant,
      nav_item_count: tabs.length
    });

    nav.addEventListener('click', function (event) {
      var tab = event.target.closest('[data-nav-item][data-nav-position]');
      if (!tab || !nav.contains(tab)) return;

      track('click_nav', {
        surface: SURFACE,
        nav: tab.dataset.navItem,
        nav_item: tab.dataset.navItem,
        nav_position: tab.dataset.navPosition,
        nav_variant: variant
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
