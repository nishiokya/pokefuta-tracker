/* A work guide already contains its public, coordinate-checked spots. No API fetch. */
(() => {
  'use strict';
  const container = document.getElementById('cw-map');
  const data = document.getElementById('cw-map-data');
  const status = document.getElementById('cw-map-status');
  if (!container || !data || !status) return;

  function initialize() {
    if (!window.L) {
      status.textContent = '地図を読み込めませんでした。設置場所一覧の地図リンクをご利用ください。';
      return;
    }
    const points = JSON.parse(data.textContent);
    if (!points.length) {
      status.textContent = '座標を確認中です。設置場所一覧から住所と案内をご確認ください。';
      return;
    }
    const map = L.map(container, { scrollWheelZoom: false });
    const tiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    tiles.on('tileerror', () => {
      status.textContent = '背景地図の一部を読み込めませんでした。設置場所一覧もご利用いただけます。';
    });
    const markers = points.map(point => {
      const popup = document.createElement('div');
      const name = document.createElement('strong');
      name.textContent = point.name;
      const address = document.createElement('p');
      address.textContent = point.address;
      const link = document.createElement('a');
      link.href = '#' + point.anchor;
      link.textContent = '写真・設置場所の案内を見る';
      popup.append(name, address, link);
      return L.marker([point.lat, point.lng], { title: point.name, alt: point.name + 'のふたマス' })
        .bindPopup(popup).addTo(map);
    });
    map.fitBounds(L.featureGroup(markers).getBounds(), { padding: [30, 30], maxZoom: 14 });
    status.textContent = points.length + '枚の設置場所を表示しています。ピンを選ぶと詳しい案内が開きます。';
  }

  // Delay map tiles until the map approaches the viewport; the hero photo comes first.
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        observer.disconnect();
        initialize();
      }
    }, { rootMargin: '200px' });
    observer.observe(container);
  } else {
    initialize();
  }
})();
