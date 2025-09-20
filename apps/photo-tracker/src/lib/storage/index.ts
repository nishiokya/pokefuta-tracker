import { SupabaseStorageAdapter } from './supabase';
import type { StorageAdapter, StorageConfig } from './types';

export function createStorageAdapter(config?: StorageConfig): StorageAdapter {
  const provider = config?.provider ?? (process.env.STORAGE_PROVIDER as any) ?? 'supabase';
  const bucket = config?.bucket ?? process.env.SUPABASE_BUCKET ?? 'photos';

  switch (provider) {
    case 'supabase':
      return new SupabaseStorageAdapter(bucket);
    case 's3':
      // TODO: Implement S3StorageAdapter
      throw new Error('S3 storage adapter not implemented yet');
    case 'r2':
      // TODO: Implement R2StorageAdapter
      throw new Error('R2 storage adapter not implemented yet');
    default:
      throw new Error(`Unknown storage provider: ${provider}`);
  }
}

// Default storage adapter
export const storage = createStorageAdapter();

// Storage key utilities
export function generateStorageKey(type: 'original' | 'thumb', size?: number): string {
  const date = new Date();
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const uuid = crypto.randomUUID();

  if (type === 'thumb' && size) {
    return `photos/thumb/${size}/${year}/${month}/${uuid}.jpg`;
  }

  return `photos/original/${year}/${month}/${uuid}.jpg`;
}

export function parseStorageKey(key: string) {
  const parts = key.split('/');
  if (parts.length < 4) {
    throw new Error('Invalid storage key format');
  }

  const [, type, sizeOrYear, year, month, filename] = parts;

  if (type === 'thumb') {
    return {
      type: 'thumb' as const,
      size: parseInt(sizeOrYear),
      year: parseInt(year),
      month: parseInt(month),
      filename,
    };
  }

  return {
    type: 'original' as const,
    size: null,
    year: parseInt(sizeOrYear),
    month: parseInt(year), // Note: month is in the year position for original
    filename: month, // Note: filename includes month/filename for original
  };
}

export * from './types';
export { SupabaseStorageAdapter };