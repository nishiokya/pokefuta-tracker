'use client';

import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Manhole } from '@/types/database';

// Fix for default markers in Leaflet
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

interface MapComponentProps {
  center: { lat: number; lng: number };
  manholes: Manhole[];
  onManholeClick: (manhole: Manhole) => void;
  userLocation?: { lat: number; lng: number } | null;
}

export default function MapComponent({
  center,
  manholes,
  onManholeClick,
  userLocation
}: MapComponentProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const markersLayerRef = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!mapRef.current) return;

    // Initialize map
    const map = L.map(mapRef.current, {
      center: [center.lat, center.lng],
      zoom: parseInt(process.env.NEXT_PUBLIC_MAP_DEFAULT_ZOOM || '10'),
      zoomControl: true,
      attributionControl: true,
    });

    mapInstanceRef.current = map;

    // Add tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    // Create markers layer
    const markersLayer = L.layerGroup().addTo(map);
    markersLayerRef.current = markersLayer;

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, []);

  // Update map center when center prop changes
  useEffect(() => {
    if (mapInstanceRef.current) {
      mapInstanceRef.current.setView([center.lat, center.lng]);
    }
  }, [center]);

  // Update user location marker
  useEffect(() => {
    if (!mapInstanceRef.current || !userLocation) return;

    const userIcon = L.divIcon({
      className: 'user-location-marker',
      html: `
        <div style="
          width: 20px;
          height: 20px;
          background: linear-gradient(45deg, #ff6b6b, #4ecdc4);
          border: 3px solid white;
          border-radius: 50%;
          box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        "></div>
      `,
      iconSize: [20, 20],
      iconAnchor: [10, 10]
    });

    const userMarker = L.marker([userLocation.lat, userLocation.lng], {
      icon: userIcon,
      zIndexOffset: 1000
    }).addTo(mapInstanceRef.current);

    return () => {
      userMarker.remove();
    };
  }, [userLocation]);

  // Update manhole markers
  useEffect(() => {
    if (!markersLayerRef.current) return;

    // Clear existing markers
    markersLayerRef.current.clearLayers();

    // Add manhole markers
    manholes.forEach((manhole) => {
      if (manhole.latitude && manhole.longitude) {
        const isVisited = manhole.is_visited;

        // Create custom icon based on visit status
        const markerIcon = L.divIcon({
          className: `manhole-marker ${isVisited ? 'marker-visited' : 'marker-unvisited'}`,
          html: `
            <div style="
              width: 24px;
              height: 24px;
              background: ${isVisited ? '#4ecdc4' : '#ff6b6b'};
              border: 3px solid white;
              border-radius: 50%;
              box-shadow: 0 2px 8px rgba(0,0,0,0.3);
              opacity: ${isVisited ? '1' : '0.7'};
              display: flex;
              align-items: center;
              justify-content: center;
              font-size: 12px;
              color: white;
              font-weight: bold;
            ">
              ${isVisited ? '✓' : '?'}
            </div>
          `,
          iconSize: [24, 24],
          iconAnchor: [12, 12]
        });

        const marker = L.marker([manhole.latitude, manhole.longitude], {
          icon: markerIcon
        });

        // Add popup
        const popupContent = `
          <div class="p-2">
            <h3 class="font-bold text-sm mb-1">${manhole.name || 'ポケふた'}</h3>
            ${manhole.description ? `<p class="text-xs text-gray-600 mb-2">${manhole.description}</p>` : ''}
            <div class="text-xs">
              <div class="mb-1">
                <span class="font-semibold">場所:</span> ${manhole.prefecture || ''} ${manhole.city || ''}
              </div>
              ${manhole.address ? `<div class="mb-1"><span class="font-semibold">住所:</span> ${manhole.address}</div>` : ''}
              <div class="mb-2">
                <span class="badge-pokemon">
                  ${isVisited ? '訪問済み' : '未訪問'}
                </span>
              </div>
              <button
                onclick="window.location.href='/manhole/${manhole.id}'"
                class="btn-pokemon-secondary text-xs px-3 py-1"
              >
                詳細を見る
              </button>
            </div>
          </div>
        `;

        marker.bindPopup(popupContent, {
          maxWidth: 250,
          className: 'pokemon-popup'
        });

        // Add click handler
        marker.on('click', () => {
          onManholeClick(manhole);
        });

        markersLayerRef.current?.addLayer(marker);
      }
    });
  }, [manholes, onManholeClick]);

  return (
    <div
      ref={mapRef}
      className="map-container w-full h-full"
      style={{ minHeight: '400px' }}
    />
  );
}