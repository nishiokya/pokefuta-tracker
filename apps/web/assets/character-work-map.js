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
      link.href = point.href || ('#' + point.anchor);
      link.textContent = point.href ? '全国地図で設置場所を見る' : '写真・設置場所の案内を見る';
      popup.append(name, address, link);
      const marker = L.marker([point.lat, point.lng], { title: point.name, alt: point.alt || point.name })
        .bindPopup(popup).addTo(map);
      if (/^https?:\/\//i.test(point.photo_url || '')) {
        const fallback = marker.options.icon;
        const photo = document.createElement('img');
        // divIcon には Leaflet の alt が付かないので、写真自体に名前を持たせる
        photo.alt = point.alt || point.name;
        photo.decoding = 'async';
        photo.loading = 'lazy';
        photo.width = 44;
        photo.height = 44;
        photo.className = 'cw-map-photo-marker';
        photo.onerror = () => marker.setIcon(fallback);
        photo.src = point.photo_url;
        marker.setIcon(L.divIcon({ className: '', html: photo, iconSize: [44, 44], iconAnchor: [22, 22], popupAnchor: [0, -22] }));
      }
      return { marker, point };
    });
    const regionFilter = document.getElementById('cw-map-region');
    const photoFilter = document.getElementById('cw-map-photos');
    const count = document.getElementById('cw-map-count');
    const initialBounds = L.featureGroup(markers.map(item => item.marker)).getBounds();
    if (regionFilter) {
      [...new Set(points.map(point => point.region).filter(Boolean))].forEach(region => {
        const option = document.createElement('option');
        option.value = region;
        option.textContent = region;
        regionFilter.appendChild(option);
      });
    }
    function applyFilters() {
      const region = regionFilter?.value || '';
      const photos = photoFilter?.value || 'all';
      const visible = [];
      for (const { marker, point } of markers) {
        const matches = (!region || point.region === region)
          && (photos === 'all' || (photos === 'with' ? Boolean(point.photo_url) : !point.photo_url));
        if (matches) { marker.addTo(map); visible.push(marker); }
        else marker.remove();
      }
      if (count) count.textContent = visible.length + ' / ' + points.length + '基を表示';
      map.fitBounds(visible.length ? L.featureGroup(visible).getBounds() : initialBounds,
        { padding: [30, 30], maxZoom: 14 });
    }
    regionFilter?.addEventListener('change', applyFilters);
    photoFilter?.addEventListener('change', applyFilters);
    applyFilters();
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
