import { supabase } from '../supabase';
import type { StorageAdapter, PutOptions, SignedUrl } from './types';

export class SupabaseStorageAdapter implements StorageAdapter {
  constructor(private bucket: string = 'photos') {}

  async put(key: string, data: ArrayBuffer | Buffer | Blob, options?: PutOptions): Promise<void> {
    const { error } = await supabase.storage.from(this.bucket).upload(key, data, {
      contentType: options?.contentType,
      cacheControl: options?.cacheControl ?? 'public, max-age=31536000, immutable',
      upsert: false,
      metadata: options?.metadata,
    });

    if (error) {
      console.error('Supabase storage upload error:', error);
      throw new Error(`Failed to upload to Supabase: ${error.message}`);
    }
  }

  async getSignedUrl(key: string, ttlSec: number): Promise<SignedUrl> {
    const { data, error } = await supabase.storage
      .from(this.bucket)
      .createSignedUrl(key, ttlSec);

    if (error) {
      console.error('Supabase storage signed URL error:', error);
      throw new Error(`Failed to create signed URL: ${error.message}`);
    }

    return {
      url: data.signedUrl,
      expiresAt: Math.floor(Date.now() / 1000) + ttlSec,
    };
  }

  async exists(key: string): Promise<boolean> {
    const { data, error } = await supabase.storage
      .from(this.bucket)
      .list(key.split('/').slice(0, -1).join('/'), {
        limit: 1,
        search: key.split('/').pop(),
      });

    if (error) {
      console.error('Supabase storage exists check error:', error);
      return false;
    }

    return data.length > 0;
  }

  async delete(key: string): Promise<void> {
    const { error } = await supabase.storage.from(this.bucket).remove([key]);

    if (error) {
      console.error('Supabase storage delete error:', error);
      throw new Error(`Failed to delete from Supabase: ${error.message}`);
    }
  }

  async move(srcKey: string, dstKey: string): Promise<void> {
    const { error } = await supabase.storage
      .from(this.bucket)
      .move(srcKey, dstKey);

    if (error) {
      console.error('Supabase storage move error:', error);
      throw new Error(`Failed to move in Supabase: ${error.message}`);
    }
  }
}