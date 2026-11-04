// Android だけ、「経路案内」を geo: で開いて Google マップのピンに蓋の名前を出す。
//
// Google マップの URL（maps/search/?api=1&query=緯度,経度）にはピンの名前を渡す手段がなく、
// 開いた先には座標しか出ない。Android の geo: は q=緯度,経度(名前) で名前を付けられる。
// iPhone は geo: を開けないので、今の URL のまま。
//
// 対象: data-geo-label を持ち、href が座標の maps/search のリンク。
// 押した瞬間に href を差し替えるので、ページの HTML と計測（data-track・onclick）はそのまま。
(function () {
  var ua = navigator.userAgent || '';
  if (!/Android/i.test(ua)) return;
  // アプリ内ブラウザ（WebView）は geo: を開けず、何も起きないことがある。そこは今の URL で開く
  if (/; wv\)|Line\/|Instagram|FBAN|FBAV|FB_IAB/.test(ua)) return;

  var COORD = /^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$/;

  function geoUrl(href, label) {
    var url;
    try {
      url = new URL(href, location.href);
    } catch (e) {
      return '';
    }
    if (!/(^|\.)google\.[a-z.]+$/.test(url.hostname) || url.pathname !== '/maps/search/') return '';
    var match = COORD.exec(url.searchParams.get('query') || '');
    if (!match) return '';
    // 名前の中の半角かっこは geo: の区切りと混ざるので全角にする
    var name = String(label).replace(/\(/g, '（').replace(/\)/g, '）').replace(/\s+/g, ' ').trim();
    if (!name) return '';
    return 'geo:0,0?q=' + match[1] + ',' + match[2] + '(' + encodeURIComponent(name) + ')';
  }

  document.addEventListener('click', function (event) {
    var link = event.target.closest && event.target.closest('a[data-geo-label]');
    if (!link) return;
    var geo = geoUrl(link.getAttribute('href') || '', link.getAttribute('data-geo-label') || '');
    if (!geo) return;
    link.setAttribute('href', geo);
    // 新しいタブで geo: を開くと空のタブが残る
    link.removeAttribute('target');
  }, true);

  window.PokefutaGeoLink = { geoUrl: geoUrl };
})();
