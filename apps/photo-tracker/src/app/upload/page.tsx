'use client';

import { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { Camera, Upload, MapPin, CheckCircle, AlertCircle, X } from 'lucide-react';
import exifr from 'exifr';
import imageCompression from 'browser-image-compression';
import { Manhole } from '@/types/database';

interface PhotoMetadata {
  latitude?: number;
  longitude?: number;
  datetime?: string;
  camera?: string;
  lens?: string;
}

interface UploadedPhoto {
  id: string;
  file: File;
  preview: string;
  metadata: PhotoMetadata;
  matchedManhole?: Manhole;
  uploading: boolean;
  uploaded: boolean;
  uploadedImageId?: string;
  error?: string;
}

export default function UploadPage() {
  const [photos, setPhotos] = useState<UploadedPhoto[]>([]);
  const [manholes, setManholes] = useState<Manhole[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
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
    }
  };

  const extractMetadata = async (file: File): Promise<PhotoMetadata> => {
    try {
      const metadata = await exifr.parse(file);
      return {
        latitude: metadata?.latitude,
        longitude: metadata?.longitude,
        datetime: metadata?.DateTimeOriginal || metadata?.DateTime,
        camera: metadata?.Make && metadata?.Model ? `${metadata.Make} ${metadata.Model}` : undefined,
        lens: metadata?.LensModel
      };
    } catch (error) {
      console.warn('Failed to extract EXIF data:', error);
      return {};
    }
  };

  const findNearestManhole = (lat: number, lng: number): Manhole | undefined => {
    if (!manholes.length) return undefined;

    let nearest: Manhole | undefined;
    let minDistance = Infinity;

    manholes.forEach(manhole => {
      if (manhole.latitude && manhole.longitude) {
        const distance = calculateDistance(lat, lng, manhole.latitude, manhole.longitude);
        if (distance < minDistance && distance < 0.1) { // Within 100m
          minDistance = distance;
          nearest = manhole;
        }
      }
    });

    return nearest;
  };

  const calculateDistance = (lat1: number, lng1: number, lat2: number, lng2: number): number => {
    const R = 6371; // Earth's radius in km
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLng = (lng2 - lng1) * Math.PI / 180;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
      Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
      Math.sin(dLng/2) * Math.sin(dLng/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
  };

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    setLoading(true);

    const newPhotos: UploadedPhoto[] = [];

    for (const file of acceptedFiles) {
      const id = Math.random().toString(36).substr(2, 9);
      const preview = URL.createObjectURL(file);
      const metadata = await extractMetadata(file);

      let matchedManhole: Manhole | undefined;
      if (metadata.latitude && metadata.longitude) {
        matchedManhole = findNearestManhole(metadata.latitude, metadata.longitude);
      }

      newPhotos.push({
        id,
        file,
        preview,
        metadata,
        matchedManhole,
        uploading: false,
        uploaded: false
      });
    }

    setPhotos(prev => [...prev, ...newPhotos]);
    setLoading(false);
  }, [manholes]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/*': ['.jpeg', '.jpg', '.png', '.heic', '.heif']
    },
    multiple: true
  });

  const removePhoto = (id: string) => {
    setPhotos(prev => {
      const photo = prev.find(p => p.id === id);
      if (photo) {
        URL.revokeObjectURL(photo.preview);
      }
      return prev.filter(p => p.id !== id);
    });
  };

  const uploadPhoto = async (photoId: string) => {
    const photo = photos.find(p => p.id === photoId);
    if (!photo) return;

    setPhotos(prev => prev.map(p =>
      p.id === photoId ? { ...p, uploading: true, error: undefined } : p
    ));

    try {
      // Compress image
      const compressedFile = await imageCompression(photo.file, {
        maxSizeMB: 2,
        maxWidthOrHeight: 1920,
        useWebWorker: true
      });

      // Prepare form data for upload
      const formData = new FormData();
      formData.append('file', compressedFile);

      // Add manhole ID if matched
      if (photo.matchedManhole) {
        formData.append('manholeId', photo.matchedManhole.id.toString());
      }

      // Add metadata
      const metadata = {
        metadata: {
          ...photo.metadata,
          originalFilename: photo.file.name,
          uploadedAt: new Date().toISOString()
        },
        exif: photo.metadata
      };
      formData.append('metadata', JSON.stringify(metadata));

      // Upload to binary storage API
      const uploadResponse = await fetch('/api/minimal-upload', {
        method: 'POST',
        body: formData
      });

      const uploadResult = await uploadResponse.json();

      if (!uploadResult.success) {
        throw new Error(uploadResult.error || 'Upload failed');
      }

      setPhotos(prev => prev.map(p =>
        p.id === photoId ? {
          ...p,
          uploading: false,
          uploaded: true,
          uploadedImageId: uploadResult.image.id
        } : p
      ));

    } catch (error) {
      console.error('Upload failed:', error);
      setPhotos(prev => prev.map(p =>
        p.id === photoId ? {
          ...p,
          uploading: false,
          error: error.message || 'アップロードに失敗しました'
        } : p
      ));
    }
  };

  const uploadAllPhotos = async () => {
    const unuploadedPhotos = photos.filter(p => !p.uploaded && !p.uploading);
    for (const photo of unuploadedPhotos) {
      await uploadPhoto(photo.id);
    }
  };

  const captureFromCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' }
      });

      // In a real app, you would implement camera capture UI here
      // For now, just show an alert
      alert('カメラ機能は開発中です。ファイルをドロップするか選択してください。');

      stream.getTracks().forEach(track => track.stop());
    } catch (error) {
      console.error('Camera access denied:', error);
      alert('カメラへのアクセスが拒否されました。');
    }
  };

  return (
    <div className="min-h-screen safe-area-inset">
      {/* Header */}
      <div className="bg-gradient-to-r from-pokemon-red via-pokemon-blue to-pokemon-yellow p-4 text-white">
        <div className="container-pokemon">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Upload className="w-6 h-6" />
              <h1 className="text-xl font-bold text-shadow-pokemon">写真アップロード</h1>
            </div>
            <button
              onClick={() => window.history.back()}
              className="btn-pokemon-secondary"
            >
              戻る
            </button>
          </div>
        </div>
      </div>

      <div className="container-pokemon py-6 space-y-6">
        {/* Upload Area */}
        <div className="space-y-4">
          <div
            {...getRootProps()}
            className={`dropzone ${isDragActive ? 'active' : ''}`}
          >
            <input {...getInputProps()} />
            <div className="text-center">
              <Upload className="w-12 h-12 mx-auto mb-4 text-pokemon-blue" />
              <p className="text-lg font-semibold mb-2">
                {isDragActive ? '写真をドロップしてください' : '写真を選択またはドロップ'}
              </p>
              <p className="text-sm text-gray-600 mb-4">
                JPEG, PNG, HEIC形式に対応
              </p>
              <div className="flex gap-4 justify-center">
                <button className="btn-pokemon-secondary">
                  ファイルを選択
                </button>
                <button
                  onClick={captureFromCamera}
                  className="btn-pokemon flex items-center gap-2"
                >
                  <Camera className="w-5 h-5" />
                  カメラで撮影
                </button>
              </div>
            </div>
          </div>

          {loading && (
            <div className="text-center py-4">
              <div className="loading-pokemon mb-2">
                <div className="w-8 h-8 rounded-full bg-gradient-to-r from-pokemon-red to-pokemon-blue loading-spin mx-auto"></div>
              </div>
              <p className="text-sm text-gray-600">写真を処理中...</p>
            </div>
          )}
        </div>

        {/* Photos List */}
        {photos.length > 0 && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-pokemon-darkBlue">
                選択された写真 ({photos.length})
              </h2>
              <button
                onClick={uploadAllPhotos}
                className="btn-pokemon"
                disabled={photos.every(p => p.uploaded || p.uploading)}
              >
                全てアップロード
              </button>
            </div>

            <div className="space-y-4">
              {photos.map((photo) => (
                <div key={photo.id} className="card-pokemon p-4">
                  <div className="flex gap-4">
                    {/* Photo Preview */}
                    <div className="flex-shrink-0">
                      <img
                        src={photo.preview}
                        alt="Preview"
                        className="w-20 h-20 object-cover rounded-lg"
                      />
                    </div>

                    {/* Photo Info */}
                    <div className="flex-1 space-y-2">
                      <div className="flex items-center justify-between">
                        <h3 className="font-semibold">{photo.file.name}</h3>
                        <button
                          onClick={() => removePhoto(photo.id)}
                          className="text-red-500 hover:text-red-700"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>

                      {/* Location Info */}
                      {photo.metadata.latitude && photo.metadata.longitude ? (
                        <div className="flex items-center gap-2 text-sm text-gray-600">
                          <MapPin className="w-4 h-4" />
                          <span>
                            {photo.metadata.latitude.toFixed(6)}, {photo.metadata.longitude.toFixed(6)}
                          </span>
                        </div>
                      ) : (
                        <p className="text-sm text-gray-500">位置情報なし</p>
                      )}

                      {/* Matched Manhole */}
                      {photo.matchedManhole && (
                        <div className="bg-green-50 border border-green-200 rounded-lg p-2">
                          <div className="flex items-center gap-2 text-sm text-green-700">
                            <CheckCircle className="w-4 h-4" />
                            <span className="font-semibold">マンホールを検出:</span>
                          </div>
                          <p className="text-sm text-green-600 mt-1">
                            {photo.matchedManhole.name} ({photo.matchedManhole.city})
                          </p>
                        </div>
                      )}

                      {/* Upload Status */}
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          {photo.uploaded ? (
                            <div className="flex flex-col gap-1">
                              <div className="flex items-center gap-1 text-green-600">
                                <CheckCircle className="w-4 h-4" />
                                <span className="text-sm">アップロード完了</span>
                              </div>
                              {photo.uploadedImageId && (
                                <div className="text-xs text-gray-500">
                                  画像ID: {photo.uploadedImageId}
                                  <a
                                    href={`/api/minimal-upload?id=${photo.uploadedImageId}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="ml-2 text-pokemon-blue hover:underline"
                                  >
                                    表示
                                  </a>
                                </div>
                              )}
                            </div>
                          ) : photo.uploading ? (
                            <div className="flex items-center gap-2">
                              <div className="w-4 h-4 rounded-full bg-gradient-to-r from-pokemon-red to-pokemon-blue loading-spin"></div>
                              <span className="text-sm">アップロード中...</span>
                            </div>
                          ) : photo.error ? (
                            <div className="flex items-center gap-1 text-red-600">
                              <AlertCircle className="w-4 h-4" />
                              <span className="text-sm">{photo.error}</span>
                            </div>
                          ) : (
                            <span className="text-sm text-gray-500">未アップロード</span>
                          )}
                        </div>

                        {!photo.uploaded && !photo.uploading && (
                          <button
                            onClick={() => uploadPhoto(photo.id)}
                            className="btn-pokemon-secondary text-sm px-3 py-1"
                          >
                            アップロード
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}