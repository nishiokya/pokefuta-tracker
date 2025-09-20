export interface PutOptions {
  contentType?: string;
  cacheControl?: string;
  metadata?: Record<string, string>;
}

export interface SignedUrl {
  url: string;
  expiresAt: number;
}

export interface StorageAdapter {
  put(key: string, data: ArrayBuffer | Buffer | Blob, options?: PutOptions): Promise<void>;
  getSignedUrl(key: string, ttlSec: number): Promise<SignedUrl>;
  move?(srcKey: string, dstKey: string): Promise<void>;
  exists?(key: string): Promise<boolean>;
  delete?(key: string): Promise<void>;
}

export interface StorageConfig {
  provider: 'supabase' | 's3' | 'r2';
  bucket: string;
  options?: Record<string, any>;
}