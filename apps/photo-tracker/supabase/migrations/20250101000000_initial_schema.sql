-- Enable PostGIS extension for geographic operations
CREATE EXTENSION IF NOT EXISTS postgis;

-- Enable Row Level Security
ALTER DATABASE postgres SET "app.jwt_secret" TO 'your-jwt-secret';

-- Create custom types
CREATE TYPE weather_condition AS ENUM (
  'sunny', 'cloudy', 'rainy', 'snowy', 'foggy', 'windy', 'stormy'
);

-- Users table (extends Supabase auth.users)
CREATE TABLE app_user (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_uid TEXT UNIQUE NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  display_name TEXT,
  avatar_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  settings JSONB DEFAULT '{}',
  stats JSONB DEFAULT '{
    "total_visits": 0,
    "total_photos": 0,
    "prefectures_visited": [],
    "first_visit": null,
    "last_visit": null
  }'
);

-- Manhole master data (from scraper)
CREATE TABLE manhole (
  id BIGINT PRIMARY KEY,
  title TEXT NOT NULL,
  prefecture TEXT NOT NULL,
  municipality TEXT,
  location GEOGRAPHY(POINT, 4326) NOT NULL,
  pokemons TEXT[] DEFAULT '{}',
  detail_url TEXT,
  prefecture_site_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Visit records
CREATE TABLE visit (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  manhole_id BIGINT REFERENCES manhole(id),
  shot_location GEOGRAPHY(POINT, 4326),
  shot_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  note TEXT,
  with_family BOOLEAN DEFAULT FALSE,
  tags TEXT[] DEFAULT '{}',
  weather JSONB,
  rating INTEGER CHECK (rating >= 1 AND rating <= 5),
  -- Prevent duplicate visits on the same day
  UNIQUE(user_id, manhole_id, DATE_TRUNC('day', shot_at))
);

-- Photo records
CREATE TABLE photo (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  visit_id UUID NOT NULL REFERENCES visit(id) ON DELETE CASCADE,
  storage_provider TEXT DEFAULT 'supabase',
  storage_key TEXT NOT NULL,
  original_name TEXT,
  width INTEGER,
  height INTEGER,
  file_size INTEGER,
  content_type TEXT DEFAULT 'image/jpeg',
  exif JSONB,
  sha256 CHAR(64) UNIQUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  -- Thumbnail variants
  thumbnail_320 TEXT,
  thumbnail_800 TEXT,
  thumbnail_1600 TEXT
);

-- Shared links for public access
CREATE TABLE shared_link (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  visit_id UUID NOT NULL REFERENCES visit(id) ON DELETE CASCADE,
  created_by UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  token TEXT UNIQUE NOT NULL DEFAULT encode(gen_random_bytes(32), 'base64url'),
  title TEXT,
  description TEXT,
  expires_at TIMESTAMPTZ,
  is_active BOOLEAN DEFAULT TRUE,
  view_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_manhole_location ON manhole USING GIST(location);
CREATE INDEX idx_manhole_prefecture ON manhole(prefecture);
CREATE INDEX idx_manhole_pokemons ON manhole USING GIN(pokemons);

CREATE INDEX idx_visit_user_id ON visit(user_id);
CREATE INDEX idx_visit_manhole_id ON visit(manhole_id);
CREATE INDEX idx_visit_shot_location ON visit USING GIST(shot_location);
CREATE INDEX idx_visit_shot_at ON visit(shot_at);
CREATE INDEX idx_visit_created_at ON visit(created_at);

CREATE INDEX idx_photo_visit_id ON photo(visit_id);
CREATE INDEX idx_photo_sha256 ON photo(sha256);
CREATE INDEX idx_photo_created_at ON photo(created_at);

CREATE INDEX idx_shared_link_token ON shared_link(token);
CREATE INDEX idx_shared_link_visit_id ON shared_link(visit_id);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at triggers
CREATE TRIGGER update_app_user_updated_at
  BEFORE UPDATE ON app_user
  FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

CREATE TRIGGER update_manhole_updated_at
  BEFORE UPDATE ON manhole
  FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

CREATE TRIGGER update_visit_updated_at
  BEFORE UPDATE ON visit
  FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

-- Enable Row Level Security
ALTER TABLE app_user ENABLE ROW LEVEL SECURITY;
ALTER TABLE visit ENABLE ROW LEVEL SECURITY;
ALTER TABLE photo ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared_link ENABLE ROW LEVEL SECURITY;

-- RLS Policies

-- app_user: Users can only see and modify their own profile
CREATE POLICY "Users can view own profile" ON app_user
  FOR SELECT USING (auth_uid = auth.uid()::text);

CREATE POLICY "Users can update own profile" ON app_user
  FOR UPDATE USING (auth_uid = auth.uid()::text);

CREATE POLICY "Users can insert own profile" ON app_user
  FOR INSERT WITH CHECK (auth_uid = auth.uid()::text);

-- manhole: Public read access (no RLS needed, but enabled for consistency)
CREATE POLICY "Anyone can view manholes" ON manhole
  FOR SELECT USING (true);

-- visit: Users can only access their own visits
CREATE POLICY "Users can view own visits" ON visit
  FOR SELECT USING (user_id IN (
    SELECT id FROM app_user WHERE auth_uid = auth.uid()::text
  ));

CREATE POLICY "Users can insert own visits" ON visit
  FOR INSERT WITH CHECK (user_id IN (
    SELECT id FROM app_user WHERE auth_uid = auth.uid()::text
  ));

CREATE POLICY "Users can update own visits" ON visit
  FOR UPDATE USING (user_id IN (
    SELECT id FROM app_user WHERE auth_uid = auth.uid()::text
  ));

CREATE POLICY "Users can delete own visits" ON visit
  FOR DELETE USING (user_id IN (
    SELECT id FROM app_user WHERE auth_uid = auth.uid()::text
  ));

-- photo: Users can only access photos from their own visits
CREATE POLICY "Users can view own photos" ON photo
  FOR SELECT USING (visit_id IN (
    SELECT v.id FROM visit v
    JOIN app_user u ON v.user_id = u.id
    WHERE u.auth_uid = auth.uid()::text
  ));

CREATE POLICY "Users can insert own photos" ON photo
  FOR INSERT WITH CHECK (visit_id IN (
    SELECT v.id FROM visit v
    JOIN app_user u ON v.user_id = u.id
    WHERE u.auth_uid = auth.uid()::text
  ));

CREATE POLICY "Users can update own photos" ON photo
  FOR UPDATE USING (visit_id IN (
    SELECT v.id FROM visit v
    JOIN app_user u ON v.user_id = u.id
    WHERE u.auth_uid = auth.uid()::text
  ));

CREATE POLICY "Users can delete own photos" ON photo
  FOR DELETE USING (visit_id IN (
    SELECT v.id FROM visit v
    JOIN app_user u ON v.user_id = u.id
    WHERE u.auth_uid = auth.uid()::text
  ));

-- shared_link: Users can manage their own shared links, everyone can view active links
CREATE POLICY "Users can manage own shared links" ON shared_link
  FOR ALL USING (created_by IN (
    SELECT id FROM app_user WHERE auth_uid = auth.uid()::text
  ));

CREATE POLICY "Anyone can view active shared links" ON shared_link
  FOR SELECT USING (is_active = true AND (expires_at IS NULL OR expires_at > NOW()));

-- Create helpful views

-- View for visit statistics per user
CREATE VIEW user_visit_stats AS
SELECT
  u.id as user_id,
  u.auth_uid,
  u.display_name,
  COUNT(DISTINCT v.id) as total_visits,
  COUNT(DISTINCT v.manhole_id) as unique_manholes,
  COUNT(DISTINCT m.prefecture) as prefectures_visited,
  COUNT(DISTINCT p.id) as total_photos,
  MIN(v.shot_at) as first_visit,
  MAX(v.shot_at) as last_visit
FROM app_user u
LEFT JOIN visit v ON u.id = v.user_id
LEFT JOIN manhole m ON v.manhole_id = m.id
LEFT JOIN photo p ON v.id = p.visit_id
GROUP BY u.id, u.auth_uid, u.display_name;

-- View for unvisited manholes (requires user context)
CREATE OR REPLACE FUNCTION get_unvisited_manholes(user_uuid UUID, nearby_lat DOUBLE PRECISION DEFAULT NULL, nearby_lng DOUBLE PRECISION DEFAULT NULL, radius_km DOUBLE PRECISION DEFAULT 50)
RETURNS TABLE (
  id BIGINT,
  title TEXT,
  prefecture TEXT,
  municipality TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  pokemons TEXT[],
  distance_km DOUBLE PRECISION
) AS $$
BEGIN
  RETURN QUERY
  SELECT
    m.id,
    m.title,
    m.prefecture,
    m.municipality,
    ST_Y(m.location::geometry) as latitude,
    ST_X(m.location::geometry) as longitude,
    m.pokemons,
    CASE
      WHEN nearby_lat IS NOT NULL AND nearby_lng IS NOT NULL THEN
        ST_Distance(m.location, ST_SetSRID(ST_MakePoint(nearby_lng, nearby_lat), 4326)) / 1000
      ELSE NULL
    END as distance_km
  FROM manhole m
  WHERE m.id NOT IN (
    SELECT DISTINCT v.manhole_id
    FROM visit v
    WHERE v.user_id = user_uuid AND v.manhole_id IS NOT NULL
  )
  AND (
    nearby_lat IS NULL OR nearby_lng IS NULL OR
    ST_DWithin(
      m.location,
      ST_SetSRID(ST_MakePoint(nearby_lng, nearby_lat), 4326),
      radius_km * 1000
    )
  )
  ORDER BY
    CASE
      WHEN nearby_lat IS NOT NULL AND nearby_lng IS NOT NULL THEN
        ST_Distance(m.location, ST_SetSRID(ST_MakePoint(nearby_lng, nearby_lat), 4326))
      ELSE m.id
    END;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;