export interface Database {
  public: {
    Tables: {
      app_user: {
        Row: {
          id: string;
          auth_uid: string;
          display_name: string | null;
          avatar_url: string | null;
          created_at: string;
          updated_at: string;
          settings: Record<string, any>;
          stats: UserStats;
        };
        Insert: {
          id?: string;
          auth_uid: string;
          display_name?: string | null;
          avatar_url?: string | null;
          settings?: Record<string, any>;
          stats?: UserStats;
        };
        Update: {
          display_name?: string | null;
          avatar_url?: string | null;
          settings?: Record<string, any>;
          stats?: UserStats;
        };
      };
      manhole: {
        Row: {
          id: number;
          title: string;
          prefecture: string;
          municipality: string | null;
          location: string; // PostGIS geography as string
          pokemons: string[];
          detail_url: string | null;
          prefecture_site_url: string | null;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id: number;
          title: string;
          prefecture: string;
          municipality?: string | null;
          location: string;
          pokemons?: string[];
          detail_url?: string | null;
          prefecture_site_url?: string | null;
        };
        Update: {
          title?: string;
          prefecture?: string;
          municipality?: string | null;
          location?: string;
          pokemons?: string[];
          detail_url?: string | null;
          prefecture_site_url?: string | null;
        };
      };
      visit: {
        Row: {
          id: string;
          user_id: string;
          manhole_id: number | null;
          shot_location: string | null;
          shot_at: string;
          created_at: string;
          updated_at: string;
          note: string | null;
          with_family: boolean;
          tags: string[];
          weather: Weather | null;
          rating: number | null;
        };
        Insert: {
          id?: string;
          user_id: string;
          manhole_id?: number | null;
          shot_location?: string | null;
          shot_at: string;
          note?: string | null;
          with_family?: boolean;
          tags?: string[];
          weather?: Weather | null;
          rating?: number | null;
        };
        Update: {
          manhole_id?: number | null;
          shot_location?: string | null;
          shot_at?: string;
          note?: string | null;
          with_family?: boolean;
          tags?: string[];
          weather?: Weather | null;
          rating?: number | null;
        };
      };
      photo: {
        Row: {
          id: string;
          visit_id: string | null;
          manhole_id: number | null;
          storage_provider: string;
          storage_key: string;
          original_name: string | null;
          width: number | null;
          height: number | null;
          file_size: number | null;
          content_type: string;
          exif: ExifData | null;
          sha256: string | null;
          created_at: string;
          thumbnail_320: string | null;
          thumbnail_800: string | null;
          thumbnail_1600: string | null;
          binary_data: ArrayBuffer | null;
          thumbnail_small: ArrayBuffer | null;
          thumbnail_medium: ArrayBuffer | null;
          metadata: Record<string, any> | null;
        };
        Insert: {
          id?: string;
          visit_id?: string | null;
          manhole_id?: number | null;
          storage_provider?: string;
          storage_key?: string;
          original_name?: string | null;
          width?: number | null;
          height?: number | null;
          file_size?: number | null;
          content_type?: string;
          exif?: ExifData | null;
          sha256?: string | null;
          thumbnail_320?: string | null;
          thumbnail_800?: string | null;
          thumbnail_1600?: string | null;
          binary_data?: ArrayBuffer | null;
          thumbnail_small?: ArrayBuffer | null;
          thumbnail_medium?: ArrayBuffer | null;
          metadata?: Record<string, any> | null;
        };
        Update: {
          visit_id?: string | null;
          manhole_id?: number | null;
          storage_provider?: string;
          storage_key?: string;
          original_name?: string | null;
          width?: number | null;
          height?: number | null;
          file_size?: number | null;
          content_type?: string;
          exif?: ExifData | null;
          sha256?: string | null;
          thumbnail_320?: string | null;
          thumbnail_800?: string | null;
          thumbnail_1600?: string | null;
          binary_data?: ArrayBuffer | null;
          thumbnail_small?: ArrayBuffer | null;
          thumbnail_medium?: ArrayBuffer | null;
          metadata?: Record<string, any> | null;
        };
      };
      shared_link: {
        Row: {
          id: string;
          visit_id: string;
          created_by: string;
          token: string;
          title: string | null;
          description: string | null;
          expires_at: string | null;
          is_active: boolean;
          view_count: number;
          created_at: string;
        };
        Insert: {
          id?: string;
          visit_id: string;
          created_by: string;
          token?: string;
          title?: string | null;
          description?: string | null;
          expires_at?: string | null;
          is_active?: boolean;
          view_count?: number;
        };
        Update: {
          title?: string | null;
          description?: string | null;
          expires_at?: string | null;
          is_active?: boolean;
        };
      };
      image: {
        Row: {
          id: string;
          photo_id: string | null;
          manhole_id: number | null;
          filename: string;
          content_type: string;
          file_size: number;
          width: number | null;
          height: number | null;
          binary_data: ArrayBuffer;
          thumbnail_small: ArrayBuffer | null;
          thumbnail_medium: ArrayBuffer | null;
          created_at: string;
          updated_at: string;
          exif_data: ExifData | null;
          metadata: Record<string, any> | null;
        };
        Insert: {
          id?: string;
          photo_id?: string | null;
          manhole_id?: number | null;
          filename: string;
          content_type: string;
          file_size: number;
          width?: number | null;
          height?: number | null;
          binary_data: ArrayBuffer;
          thumbnail_small?: ArrayBuffer | null;
          thumbnail_medium?: ArrayBuffer | null;
          exif_data?: ExifData | null;
          metadata?: Record<string, any> | null;
        };
        Update: {
          photo_id?: string | null;
          manhole_id?: number | null;
          filename?: string;
          content_type?: string;
          file_size?: number;
          width?: number | null;
          height?: number | null;
          binary_data?: ArrayBuffer;
          thumbnail_small?: ArrayBuffer | null;
          thumbnail_medium?: ArrayBuffer | null;
          exif_data?: ExifData | null;
          metadata?: Record<string, any> | null;
        };
      };
    };
    Views: {
      user_visit_stats: {
        Row: {
          user_id: string;
          auth_uid: string;
          display_name: string | null;
          total_visits: number;
          unique_manholes: number;
          prefectures_visited: number;
          total_photos: number;
          first_visit: string | null;
          last_visit: string | null;
        };
      };
    };
    Functions: {
      get_unvisited_manholes: {
        Args: {
          user_uuid: string;
          nearby_lat?: number;
          nearby_lng?: number;
          radius_km?: number;
        };
        Returns: {
          id: number;
          title: string;
          prefecture: string;
          municipality: string | null;
          latitude: number;
          longitude: number;
          pokemons: string[];
          distance_km: number | null;
        }[];
      };
    };
  };
}

export interface UserStats {
  total_visits: number;
  total_photos: number;
  prefectures_visited: string[];
  first_visit: string | null;
  last_visit: string | null;
}

export interface Weather {
  condition: 'sunny' | 'cloudy' | 'rainy' | 'snowy' | 'foggy' | 'windy' | 'stormy';
  temperature?: number;
  humidity?: number;
  description?: string;
}

export interface ExifData {
  make?: string;
  model?: string;
  software?: string;
  dateTime?: string;
  gps?: {
    latitude?: number;
    longitude?: number;
    altitude?: number;
    speed?: number;
    heading?: number;
  };
  camera?: {
    fNumber?: number;
    exposureTime?: string;
    iso?: number;
    focalLength?: number;
    flash?: boolean;
  };
  image?: {
    width?: number;
    height?: number;
    orientation?: number;
    colorSpace?: string;
  };
}

// Helper types for API responses
export interface ManholeWithDistance {
  id: number;
  title: string;
  prefecture: string;
  municipality: string | null;
  latitude: number;
  longitude: number;
  pokemons: string[];
  distance_km: number | null;
}

export interface VisitWithPhotos {
  id: string;
  user_id: string;
  manhole_id: number | null;
  manhole?: Database['public']['Tables']['manhole']['Row'];
  shot_location: string | null;
  shot_at: string;
  created_at: string;
  updated_at: string;
  note: string | null;
  with_family: boolean;
  tags: string[];
  weather: Weather | null;
  rating: number | null;
  photos: Database['public']['Tables']['photo']['Row'][];
}

export interface PhotoUploadProgress {
  file: File;
  progress: number;
  status: 'pending' | 'uploading' | 'processing' | 'completed' | 'error';
  error?: string;
  photoId?: string;
}

export type ManholeCandidate = {
  manhole: Database['public']['Tables']['manhole']['Row'];
  distance: number;
  confidence: number;
};

// Convenience type exports
export type Manhole = Database['public']['Tables']['manhole']['Row'] & {
  name?: string;
  description?: string;
  city?: string;
  address?: string;
  latitude?: number;
  longitude?: number;
  source_url?: string;
  is_visited?: boolean;
  last_visit?: string | null;
  photo_count?: number;
};