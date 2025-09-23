'use client';

import { useState, useEffect } from 'react';
import { ArrowLeft, Download, Share, Trash2, Camera, MapPin, Calendar } from 'lucide-react';
import { format } from 'date-fns';
import { ja } from 'date-fns/locale';
import { Manhole } from '@/types/database';

interface Visit {
  id: string;
  manhole: Manhole;
  visited_at: string;
  photos: {
    id: string;
    url: string;
    thumbnail_url: string;
    metadata?: {
      camera?: string;
      lens?: string;
      datetime?: string;
      latitude?: number;
      longitude?: number;
    };
  }[];
  notes?: string;
}

interface PageProps {
  params: {
    id: string;
  };
}

export default function VisitPhotosPage({ params }: PageProps) {
  const [visit, setVisit] = useState<Visit | null>(null);
  const [selectedPhotoIndex, setSelectedPhotoIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [showFullscreen, setShowFullscreen] = useState(false);

  useEffect(() => {
    loadVisit();
  }, [params.id]);

  const loadVisit = async () => {
    try {
      // In a real app, this would fetch from Supabase
      // For now, generate sample data
      const sampleVisit: Visit = {
        id: params.id,
        manhole: {
          id: 1,
          title: 'ピカチュウマンホール',
          prefecture: '神奈川県',
          municipality: '横浜市',
          location: 'POINT(139.6317 35.4595)',
          pokemons: ['ピカチュウ'],
          detail_url: null,
          prefecture_site_url: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          name: 'ピカチュウマンホール',
          description: 'ピカチュウが描かれた可愛いマンホール',
          city: '横浜市',
          address: '横浜市みなとみらい21',
          latitude: 35.4595,
          longitude: 139.6317,
          is_visited: true
        },
        visited_at: new Date().toISOString(),
        photos: Array.from({ length: 6 }, (_, i) => ({
          id: `photo-${i + 1}`,
          url: `/api/placeholder/photo/${i + 1}`,
          thumbnail_url: `/api/placeholder/thumb/${i + 1}`,
          metadata: {
            camera: 'iPhone 15 Pro',
            lens: 'Main Camera',
            datetime: new Date(Date.now() - i * 60000).toISOString(),
            latitude: 35.4595 + (Math.random() - 0.5) * 0.001,
            longitude: 139.6317 + (Math.random() - 0.5) * 0.001
          }
        })),
        notes: 'とても美しいピカチュウのマンホールでした！観光客も多く、人気のスポットです。'
      };

      setVisit(sampleVisit);
    } catch (error) {
      console.error('Failed to load visit:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleShare = async () => {
    if (navigator.share && visit) {
      try {
        await navigator.share({
          title: `${visit.manhole.name} の写真`,
          text: `${visit.manhole.name}を訪問しました！`,
          url: window.location.href
        });
      } catch (error) {
        console.log('Sharing cancelled');
      }
    } else {
      // Fallback to copying URL
      navigator.clipboard.writeText(window.location.href);
      alert('URLをクリップボードにコピーしました');
    }
  };

  const handleDownload = (photoUrl: string, photoId: string) => {
    // In a real app, this would download the actual image
    const link = document.createElement('a');
    link.href = photoUrl;
    link.download = `pokefuta-${visit?.manhole.name || 'photo'}-${photoId}.jpg`;
    link.click();
  };

  if (loading) {
    return (
      <div className="min-h-screen safe-area-inset flex items-center justify-center">
        <div className="text-center">
          <div className="loading-pokemon mb-4">
            <div className="w-16 h-16 rounded-full bg-gradient-to-r from-pokemon-red to-pokemon-blue loading-spin mx-auto"></div>
          </div>
          <p className="text-pokemon-darkBlue font-semibold">写真を読み込み中...</p>
        </div>
      </div>
    );
  }

  if (!visit) {
    return (
      <div className="min-h-screen safe-area-inset flex items-center justify-center">
        <div className="text-center">
          <Camera className="w-16 h-16 mx-auto mb-4 text-gray-400" />
          <h3 className="text-lg font-semibold text-gray-700 mb-2">
            訪問記録が見つかりません
          </h3>
          <button
            onClick={() => window.history.back()}
            className="btn-pokemon"
          >
            戻る
          </button>
        </div>
      </div>
    );
  }

  const selectedPhoto = visit.photos[selectedPhotoIndex];

  return (
    <div className="min-h-screen safe-area-inset">
      {/* Header */}
      <div className="bg-gradient-to-r from-pokemon-red via-pokemon-blue to-pokemon-yellow p-4 text-white">
        <div className="container-pokemon">
          <div className="flex items-center justify-between">
            <button
              onClick={() => window.history.back()}
              className="flex items-center gap-2 text-white hover:text-pokemon-yellow transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
              <span>戻る</span>
            </button>
            <div className="flex items-center gap-2">
              <button
                onClick={handleShare}
                className="p-2 rounded-lg bg-white/20 hover:bg-white/30 transition-colors"
              >
                <Share className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Visit Info */}
      <div className="bg-white border-b border-gray-200 p-4">
        <div className="container-pokemon">
          <h1 className="text-xl font-bold text-pokemon-darkBlue mb-2">
            {visit.manhole.name}
          </h1>
          <div className="flex items-center gap-4 text-sm text-gray-600">
            <div className="flex items-center gap-1">
              <MapPin className="w-4 h-4" />
              <span>{visit.manhole.prefecture} {visit.manhole.city}</span>
            </div>
            <div className="flex items-center gap-1">
              <Calendar className="w-4 h-4" />
              <span>
                {format(new Date(visit.visited_at), 'yyyy年M月d日', { locale: ja })}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <Camera className="w-4 h-4" />
              <span>{visit.photos.length}枚</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Photo */}
      <div className="bg-black">
        <div className="container-pokemon">
          <div className="relative aspect-square md:aspect-video">
            <div
              className="absolute inset-0 bg-gradient-to-br from-pokemon-blue to-pokemon-red flex items-center justify-center cursor-pointer"
              onClick={() => setShowFullscreen(true)}
            >
              <Camera className="w-16 h-16 text-white" />
            </div>

            {/* Photo Controls */}
            <div className="absolute top-4 right-4 flex gap-2">
              <button
                onClick={() => handleDownload(selectedPhoto.url, selectedPhoto.id)}
                className="p-2 rounded-lg bg-black/50 text-white hover:bg-black/70 transition-colors"
              >
                <Download className="w-5 h-5" />
              </button>
            </div>

            {/* Navigation */}
            {visit.photos.length > 1 && (
              <>
                <button
                  onClick={() => setSelectedPhotoIndex(Math.max(0, selectedPhotoIndex - 1))}
                  disabled={selectedPhotoIndex === 0}
                  className="absolute left-4 top-1/2 -translate-y-1/2 p-2 rounded-lg bg-black/50 text-white hover:bg-black/70 transition-colors disabled:opacity-50"
                >
                  <ArrowLeft className="w-6 h-6" />
                </button>
                <button
                  onClick={() => setSelectedPhotoIndex(Math.min(visit.photos.length - 1, selectedPhotoIndex + 1))}
                  disabled={selectedPhotoIndex === visit.photos.length - 1}
                  className="absolute right-4 top-1/2 -translate-y-1/2 p-2 rounded-lg bg-black/50 text-white hover:bg-black/70 transition-colors disabled:opacity-50 rotate-180"
                >
                  <ArrowLeft className="w-6 h-6" />
                </button>
              </>
            )}

            {/* Photo Counter */}
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-black/50 text-white px-3 py-1 rounded-full text-sm">
              {selectedPhotoIndex + 1} / {visit.photos.length}
            </div>
          </div>
        </div>
      </div>

      {/* Photo Thumbnails */}
      <div className="bg-gray-50 border-b border-gray-200 p-4">
        <div className="container-pokemon">
          <div className="flex gap-2 overflow-x-auto pb-2">
            {visit.photos.map((photo, index) => (
              <button
                key={photo.id}
                onClick={() => setSelectedPhotoIndex(index)}
                className={`flex-shrink-0 w-16 h-16 rounded-lg overflow-hidden border-2 transition-colors ${
                  index === selectedPhotoIndex
                    ? 'border-pokemon-blue'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <div className="w-full h-full bg-gradient-to-br from-pokemon-lightBlue to-pokemon-blue flex items-center justify-center">
                  <Camera className="w-6 h-6 text-white" />
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Photo Info */}
      <div className="container-pokemon py-6 space-y-6">
        {/* Photo Metadata */}
        {selectedPhoto.metadata && (
          <div className="card-pokemon p-4">
            <h3 className="font-bold text-pokemon-darkBlue mb-3">写真情報</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              {selectedPhoto.metadata.camera && (
                <div>
                  <span className="font-semibold text-gray-700">カメラ:</span>
                  <span className="ml-2 text-gray-600">{selectedPhoto.metadata.camera}</span>
                </div>
              )}
              {selectedPhoto.metadata.lens && (
                <div>
                  <span className="font-semibold text-gray-700">レンズ:</span>
                  <span className="ml-2 text-gray-600">{selectedPhoto.metadata.lens}</span>
                </div>
              )}
              {selectedPhoto.metadata.datetime && (
                <div>
                  <span className="font-semibold text-gray-700">撮影日時:</span>
                  <span className="ml-2 text-gray-600">
                    {format(new Date(selectedPhoto.metadata.datetime), 'yyyy年M月d日 HH:mm', { locale: ja })}
                  </span>
                </div>
              )}
              {selectedPhoto.metadata.latitude && selectedPhoto.metadata.longitude && (
                <div>
                  <span className="font-semibold text-gray-700">位置:</span>
                  <span className="ml-2 text-gray-600">
                    {selectedPhoto.metadata.latitude.toFixed(6)}, {selectedPhoto.metadata.longitude.toFixed(6)}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Visit Notes */}
        {visit.notes && (
          <div className="card-pokemon p-4">
            <h3 className="font-bold text-pokemon-darkBlue mb-3">メモ</h3>
            <p className="text-gray-700">{visit.notes}</p>
          </div>
        )}

        {/* Manhole Info */}
        <div className="card-pokemon p-4">
          <h3 className="font-bold text-pokemon-darkBlue mb-3">マンホール情報</h3>
          <div className="space-y-2">
            <div>
              <span className="font-semibold text-gray-700">名前:</span>
              <span className="ml-2 text-gray-600">{visit.manhole.name}</span>
            </div>
            <div>
              <span className="font-semibold text-gray-700">場所:</span>
              <span className="ml-2 text-gray-600">
                {visit.manhole.prefecture} {visit.manhole.city}
              </span>
            </div>
            {visit.manhole.address && (
              <div>
                <span className="font-semibold text-gray-700">住所:</span>
                <span className="ml-2 text-gray-600">{visit.manhole.address}</span>
              </div>
            )}
            {visit.manhole.description && (
              <div>
                <span className="font-semibold text-gray-700">説明:</span>
                <span className="ml-2 text-gray-600">{visit.manhole.description}</span>
              </div>
            )}
          </div>
          <div className="mt-4">
            <button
              onClick={() => window.location.href = `/manhole/${visit.manhole.id}`}
              className="btn-pokemon-secondary"
            >
              マンホール詳細を見る
            </button>
          </div>
        </div>
      </div>

      {/* Fullscreen Modal */}
      {showFullscreen && (
        <div className="fixed inset-0 bg-black z-50 flex items-center justify-center">
          <button
            onClick={() => setShowFullscreen(false)}
            className="absolute top-4 right-4 text-white text-2xl z-10"
          >
            ×
          </button>
          <div className="w-full h-full flex items-center justify-center p-4">
            <div className="max-w-full max-h-full bg-gradient-to-br from-pokemon-blue to-pokemon-red rounded-lg flex items-center justify-center">
              <Camera className="w-32 h-32 text-white" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}