'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { MapPin, Camera, Navigation } from 'lucide-react';
import { Manhole } from '@/types/database';

const MapComponent = dynamic(
  () => import('@/components/Map/MapComponent'),
  {
    ssr: false,
    loading: () => (
      <div className="w-full h-full flex items-center justify-center">
        <div className="loading-pokemon">
          <div className="w-12 h-12 rounded-full bg-gradient-to-r from-pokemon-red to-pokemon-blue loading-spin"></div>
        </div>
      </div>
    )
  }
);

export default function MapPage() {
  const [manholes, setManholes] = useState<Manhole[]>([]);
  const [userLocation, setUserLocation] = useState<{ lat: number; lng: number } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Get user location
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          setUserLocation({
            lat: position.coords.latitude,
            lng: position.coords.longitude
          });
        },
        (error) => {
          console.warn('Location access denied:', error);
          // Default to Japan center
          setUserLocation({
            lat: parseFloat(process.env.NEXT_PUBLIC_MAP_DEFAULT_CENTER_LAT || '36.0'),
            lng: parseFloat(process.env.NEXT_PUBLIC_MAP_DEFAULT_CENTER_LNG || '138.0')
          });
        }
      );
    }

    // Load manhole data
    loadManholes();
  }, []);

  const loadManholes = async () => {
    try {
      const response = await fetch('/api/manholes');
      if (response.ok) {
        const data = await response.json();
        setManholes(data);
      }
    } catch (error) {
      console.error('Failed to load manholes:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleManholeClick = (manhole: Manhole) => {
    // Navigate to manhole detail page
    window.location.href = `/manhole/${manhole.id}`;
  };

  const centerOnUser = () => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          setUserLocation({
            lat: position.coords.latitude,
            lng: position.coords.longitude
          });
        },
        (error) => {
          console.error('Failed to get location:', error);
        }
      );
    }
  };

  return (
    <div className="min-h-screen safe-area-inset">
      {/* Header */}
      <div className="bg-gradient-to-r from-pokemon-red via-pokemon-blue to-pokemon-yellow p-4 text-white">
        <div className="container-pokemon">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <MapPin className="w-6 h-6" />
              <h1 className="text-xl font-bold text-shadow-pokemon">ポケふたマップ</h1>
            </div>
            <button
              onClick={centerOnUser}
              className="btn-pokemon-secondary"
              title="現在地に移動"
            >
              <Navigation className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Map Container */}
      <div className="flex-1 relative">
        <div className="absolute inset-0">
          {userLocation && (
            <MapComponent
              center={userLocation}
              manholes={manholes}
              onManholeClick={handleManholeClick}
              userLocation={userLocation}
            />
          )}
        </div>

        {/* Loading Overlay */}
        {loading && (
          <div className="absolute inset-0 bg-white/80 backdrop-blur-sm flex items-center justify-center z-10">
            <div className="text-center">
              <div className="loading-pokemon mb-4">
                <div className="w-16 h-16 rounded-full bg-gradient-to-r from-pokemon-red to-pokemon-blue loading-spin mx-auto"></div>
              </div>
              <p className="text-pokemon-darkBlue font-semibold">マップを読み込み中...</p>
            </div>
          </div>
        )}

        {/* Stats Overlay */}
        <div className="absolute top-4 left-4 right-4 z-10">
          <div className="card-pokemon p-3">
            <div className="flex justify-between text-sm">
              <div className="text-center">
                <div className="font-bold text-pokemon-darkBlue">{manholes.length}</div>
                <div className="text-gray-600">総数</div>
              </div>
              <div className="text-center">
                <div className="font-bold text-pokemon-red">
                  {manholes.filter(m => m.is_visited).length}
                </div>
                <div className="text-gray-600">訪問済み</div>
              </div>
              <div className="text-center">
                <div className="font-bold text-pokemon-blue">
                  {manholes.filter(m => !m.is_visited).length}
                </div>
                <div className="text-gray-600">未訪問</div>
              </div>
            </div>
          </div>
        </div>

        {/* Camera Button */}
        <div className="absolute bottom-20 right-4 z-10">
          <button
            onClick={() => window.location.href = '/camera'}
            className="w-16 h-16 btn-pokemon rounded-full flex items-center justify-center shadow-pokemon-hover"
            title="写真を撮影"
          >
            <Camera className="w-8 h-8" />
          </button>
        </div>
      </div>
    </div>
  );
}