# Database Setup Guide

## Current Status
✅ **Supabase Connected**: https://kbwzwgsjqvflgfauzcpn.supabase.co
✅ **Tables Created**: manhole, app_user, visit, photo
❌ **Data Insertion Blocked**: Row Level Security (RLS) enabled
❌ **Service Role Key**: Missing from .env.local

## Options to Insert Manhole Data

### Option 1: Add Service Role Key (Recommended)
1. Go to Supabase Dashboard → Settings → API
2. Copy the `service_role` key (secret key)
3. Add to `.env.local`:
   ```
   SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
   ```
4. Run the insert API:
   ```bash
   curl -X POST http://localhost:3000/api/seed-manholes
   ```

### Option 2: Temporarily Disable RLS
1. Go to Supabase Dashboard → Table Editor → manhole table
2. Click the shield icon next to the table name
3. Toggle "Enable RLS" to OFF temporarily
4. Run the insert API:
   ```bash
   curl -X POST http://localhost:3000/api/insert-manholes
   ```
5. **Remember to re-enable RLS afterwards!**

### Option 3: Manual SQL Insert
Execute this SQL directly in Supabase SQL Editor:

```sql
INSERT INTO manhole (id, title, prefecture, municipality, location, pokemons) VALUES
(1, 'ピカチュウマンホール', '神奈川県', '横浜市', 'POINT(139.6317 35.4595)', ARRAY['ピカチュウ']),
(2, 'イーブイマンホール', '東京都', '渋谷区', 'POINT(139.7006 35.6598)', ARRAY['イーブイ']),
(3, 'ポッチャママンホール', '北海道', '札幌市', 'POINT(141.3469 43.0642)', ARRAY['ポッチャマ']),
(4, 'カビゴンマンホール', '大阪府', '大阪市', 'POINT(135.5023 34.6686)', ARRAY['カビゴン']),
(5, 'ゲンガーマンホール', '京都府', '京都市', 'POINT(135.7681 35.0056)', ARRAY['ゲンガー']);
```

### Option 4: Configure RLS Policies
Create an insert policy in Supabase SQL Editor:

```sql
-- Allow anonymous inserts for development
CREATE POLICY "allow_anonymous_insert" ON public.manhole
FOR INSERT TO anon
WITH CHECK (true);
```

## After Data Insertion

Verify the data was inserted:
```bash
curl http://localhost:3000/api/insert-manholes
```

Test the main API:
```bash
curl http://localhost:3000/api/manholes
```

The app should now show real data instead of sample data!

## Current API Endpoints

- **GET /api/test-supabase** - Connection test
- **GET /api/manholes** - Main manholes API (with fallback)
- **POST /api/insert-manholes** - Insert data (RLS blocked)
- **POST /api/seed-manholes** - Insert with service key (needs key)

## Recommended Steps

1. **Get service role key** from Supabase dashboard
2. **Add to .env.local**
3. **Run seed API** to insert data
4. **Test application** - all pages should work with real data
5. **Configure RLS policies** for production security

The easiest approach is Option 1 (service role key) as it's the most secure and doesn't require manual SQL or disabling security features.