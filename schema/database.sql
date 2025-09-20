-- ユーザー
create table app_user (
  id uuid primary key default gen_random_uuid(),
  auth_uid text unique not null,
  display_name text,
  created_at timestamptz default now()
);

-- ポケふたマスタ（スクレイプ/公式を正規化）
create table manhole (
  id bigint primary key,                 -- 既存IDに合わせる
  title text,
  prefecture text,
  municipality text,
  location geography(Point, 4326),
  pokemons text[],
  detail_url text,
  source_last_checked timestamptz
);
create index on manhole using gist(location);

-- 訪問記録
create table visit (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references app_user(id),
  manhole_id bigint references manhole(id),  -- 既知の場合
  shot_location geography(Point, 4326),      -- EXIF or GPS
  shot_at timestamptz,
  created_at timestamptz default now(),
  note text,
  with_family bool default false,
  tags text[] default '{}',
  weather jsonb,
  unique(user_id, manhole_id, date_trunc('day', shot_at))
);

-- 画像
create table photo (
  id uuid primary key default gen_random_uuid(),
  visit_id uuid references visit(id) on delete cascade,
  storage_path text not null,           -- supabase://bucket/key
  width int,
  height int,
  exif jsonb,
  sha256 char(64),                      -- 重複判定
  created_at timestamptz default now()
);
create unique index on photo(sha256);