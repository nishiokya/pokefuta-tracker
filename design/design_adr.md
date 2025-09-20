# 目的

家族や個人の「訪問したポケモンマンホール（ポケふた）」の写真・訪問記録を、スマホからサクッと登録・閲覧・共有できる仕組み。

既存のポケふた位置データ（自作スクレイパのJSONなど）と連携し、地図上での可視化・重複防止・未訪問の発見を支援。

コストは低〜中（数百円〜数千円/月）。メンテ容易、将来の機能拡張（ワークフロー・共有アルバム・公開ページ）に耐える。

# 全体像（2パス設計）


推奨ベースライン（Supabase + Vercel + Next.js）

# コンポーネント

Next.js PWA：

機能：ログイン、写真アップ（カメラ起動可）、位置取得（GPS/EXIF）、地図表示、訪問一覧、検索/フィルタ、未訪問サジェスト。

オフライン：IndexedDBに一時保存→再送（バックグラウンド同期）。

Supabase：

Auth（Email magic link + Optional: LINE OAuth）

Postgres（地理拡張：PostGIS）

Storage（原本・サムネ）

Edge Functions（EXIF抽出、重複検出、メタ補正）

Vercel：

SSR/ISRで高速配信、Vercel Cron でバッチ（未訪問ランキング作成など）。

Leaflet：

ポケふたベースレイヤ（自作JSON）を読み込み、訪問済みを上書き描画。クラスタリング（leaflet.markercluster）。

## データモデル（Postgres/PostGIS）

```
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

```

追加インデックス/ビュー

近傍検索：select ... order by ST_Distance(shot_location, ST_SetSRID(ST_MakePoint(:lng,:lat),4326)) limit 20;

未訪問候補ビュー：manhole − visit joinで差集合。

## ストレージ構成（Supabase Storage）

バケット：photos/original/YYYY/MM/ と photos/thumb/（Cloudflare Images等で自動変換も可）

ポリシー：ユーザー自身の写真は読み書き許可、公開共有用は署名URL（期限付き）。

# 登録フロー

撮影→アップロード（複数選択OK）

EXIF解析（Edge Functions）

GPS→visit.shot_location、撮影日時→shot_at

SHA-256で重複判定→既存ならマージ

近傍マッチング（半径100m）

manhole.location と位置が近い候補を提示→ユーザーが該当を選択

なければ「新規/未登録」として仮IDで保存→後で統合可

サムネ生成（長辺1600/800/320）

地図に反映（訪問済みは色変更・カウント）

UIワイヤ（簡易）

ホーム：未訪問トップ10（自宅/現在地から近い順）／最近の訪問

＋登録：写真選択→位置・日付自動→マンホール確定→タグ/メモ→保存

マップ：訪問済み（◎）/未訪問（○）を色分け。フィルタ（都道府県/ポケモン/訪問年）

詳細：写真カルーセル、同行者、ノート、天気（当時の履歴APIで任意）

共有：1件/アルバム単位で公開リンク（署名URL）

LINE連携拡張（任意）

Messaging API Bot：

「写真を送る」→Webhook（Vercel Function）→画像を一旦S3/Supabaseに保存・EXIF処理

Botが「候補はこれ？」カルーセルでmanhole候補を提示→ボタン選択で確定

LIFF App：

位置・カメラ・プロフィールをJSで取得→上記WebコンポーネントをLINE内に埋め込み

認証：LINE LoginをSupabase AuthのOAuthとして設定

通知：訪問集計の週報・未訪問近傍のプッシュ通知（頻度は控えめ）

コスト目安（ラフ）

Vercel Hobby→Pro：0〜$20/月

Supabase：フリープラン→Pro $25/月（ストレージ/DB増に応じて）

ドメイン：¥1,000/年程度

Mapタイル：無料枠内 or 数百円〜

写真1万枚・転送月数十GBでも、概ね ¥1,000〜¥5,000/月 レンジに収まる見込み。

セキュリティ/プライバシ

RLS（Row Level Security）で visit/photo は 自分の行のみアクセス

署名URLの有効期限短め、共有停止はレコードのrevoked_atで即時無効化

EXIFのGPSは「公開用は自動マスク（市区町村まで）」

運用と拡張

バックアップ：DBは日次スナップショット、画像はバージョンニング

CI/CD：GitHub Actions → Vercel/Supabaseマイグレーション自動適用

監視：Vercel/Edge Functionsのメトリクス、Sentryでエラー収集

家族アカウント：ファミリー共有スペース（グループID）とロール（Owner/Writer/Viewer）

ガメフィケーション：県制覇バッジ、連続訪問日数、希少ポケモン発見ポイント

データ公開：自分の訪問ヒートマップを公開ページに（SEOオフ、noindex）

APIスケッチ

POST   /api/upload            -- 署名URL発行 or 直接受信
POST   /api/ingest            -- EXIF解析・重複チェック・近傍候補返却
POST   /api/visit             -- 訪問確定
GET    /api/map?bbox=...      -- タイル/GeoJSON配信用（訪問+未訪問）
GET    /api/visits?filters... -- リスト・検索
POST   /api/share/:visit_id   -- 署名URL生成

リポジトリ構成（例）

repo/
  apps/
    web/                 # Next.js (PWA)
    worker/              # Supabase Edge Functions / Lambda
  packages/
    ui/                  # 共通UIコンポーネント
    schema/              # DBマイグレーション (sqlc / drizzle)
    lib/                 # EXIF, Geo, 署名URL, 重複検知
  infra/
    supabase/            # supabase config
    vercel/              # vercel.json, cron
  data/
    manhole.master.json  # ポケふたマスタ（定期更新）

技術的論点と意思決定メモ

EXIF vs 端末位置：EXIFが信頼できない端末あり→アップ時に端末の現在地取得し、距離閾値で補正/選択。

重複判定：画像ハッシュ（SHA-256）＋感度を落としたpHashで近似重複（ブラー・トリミング耐性）。

オフライン：画像はIndexedDBに分割保存（browser-image-compression）→回線復帰で順次アップ。

地図描画：訪問済みはアイコン（著作権配慮でマンホール型）に、未訪問は薄色リング。ズームでクラスタ。

パフォーマンス：サムネ先行ロード、原本は遅延。OGP向けに640px版を用意。

最小機能セット（MVP）

Emailログイン

写真アップ＋自動位置/日時抽出

近傍のポケふた候補提示→確定

地図で訪問済/未訪問を色分け

リスト/検索（県・市・ポケモン）

次フェーズ

LINE OAuth + Bot通知

アルバム共有（署名URL）

バッジ/統計（県/市達成、年間訪問数）

家族グループ共有

公式データの自動クロール更新（週次）

作業ブレイクダウン（初版2〜3日想定の実装量目安）

Day1: スキーマ・Supabase初期化、Next.js雛形、Auth、アップロードUI

Day2: EXIF/位置→近傍候補→確定、地図描画（訪問済/未訪問）

Day3: サムネ生成、検索/フィルタ、共有リンク、軽いスタイル

リスクと対策

位置誤差：屋内/ビル陰→半径閾値を広げユーザー選択で最終確定

著作権：ポケモン画像は使用不可→マンホール型の汎用アイコンで表現

家族のプライバシ：公開リンクはデフォルトOFF、位置は町丁目まで丸め

参考実装メモ（サーバレスEXIF処理の疑似コード）

// /functions/ingest.ts (Supabase Edge Function)
import exifr from 'exifr';
import sharp from 'sharp';
export async function handle(file) {
  const buf = await file.arrayBuffer();
  const sha = sha256(buf);
  const exif = await exifr.parse(Buffer.from(buf));
  const gps = exif?.latitude && exif?.longitude ? { lat: exif.latitude, lng: exif.longitude } : null;
  await saveOriginalToStorage(sha, buf);
  const thumb = await sharp(buf).resize({ width: 1600, withoutEnlargement: true }).jpeg({ quality: 82 }).toBuffer();
  await saveThumbToStorage(sha, thumb);
  const candidates = await findNearbyManholes(gps ?? clientReportedLocation, 120);
  return { sha, exif, candidates };
}

まとめ

Supabase + Next.js PWAを主軸に、将来 LINE Bot/LIFF を追加する2段構えが最もコスパ・運用性が良い。

データモデルはPostgres+PostGISで堅牢＆クエリ柔軟。

オフライン耐性・重複検出・位置補正・共有リンクまでをMVP範囲で設計済み。

既存のポケふたJSONを地図に重ね、未訪問可視化→行動促進まで一気通貫。



ストレージ戦略（無料→有料のスムーズ移行）

方針：まずは Supabase Storage に置き、無料枠の逼迫を検知したら S3 か Cloudflare R2 に切替。切替はアダプタ層で吸収し、アプリ側コードは不変にします。

1) パス命名規約（将来互換）

物理配置に依存しない仮想キーを採用：photos/original/{yyyy}/{mm}/{sha256}.jpg、photos/thumb/{size}/{yyyy}/{mm}/{sha256}.jpg

DB には storage_provider（supabase/s3/r2）と storage_key（上記キー）を保存。

alter table photo add column if not exists storage_provider text default 'supabase';
alter table photo add column if not exists storage_key text; -- ex: photos/original/2025/09/abcd...jpg
update photo set storage_key = coalesce(storage_key, storage_path); -- 後方互換

2) ストレージ・アダプタ層

目的：UI/ビジネスロジックは Storage インターフェースに依存。実装を差し替えるだけで移行。

// packages/lib/storage/types.ts
export type PutOptions = { contentType?: string; cacheControl?: string };
export type SignedUrl = { url: string; expiresAt: number };

export interface Storage {
  put: (key: string, data: ArrayBuffer | Buffer | Blob, opts?: PutOptions) => Promise<void>;
  getSignedUrl: (key: string, ttlSec: number) => Promise<SignedUrl>;
  move?: (srcKey: string, dstKey: string) => Promise<void>;
  exists?: (key: string) => Promise<boolean>;
}

Supabase 実装

// packages/lib/storage/supabase.ts
import { createClient } from '@supabase/supabase-js';
import type { Storage } from './types';

const supabase = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.SUPABASE_SERVICE_KEY!);
const BUCKET = process.env.SUPABASE_BUCKET ?? 'photos';

export const supabaseStorage: Storage = {
  async put(key, data, opts) {
    const { error } = await supabase.storage.from(BUCKET).upload(key, data, {
      contentType: opts?.contentType,
      cacheControl: opts?.cacheControl ?? 'public, max-age=31536000, immutable',
      upsert: false,
    });
    if (error) throw error;
  },
  async getSignedUrl(key, ttlSec) {
    const { data, error } = await supabase.storage.from(BUCKET).createSignedUrl(key, ttlSec);
    if (error) throw error;
    return { url: data.signedUrl, expiresAt: Math.floor(Date.now()/1000) + ttlSec };
  },
};

S3（互換）実装雛形

// packages/lib/storage/s3.ts
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import type { Storage } from './types';

const s3 = new S3Client({ region: process.env.AWS_REGION, credentials: { accessKeyId: process.env.AWS_ACCESS_KEY_ID!, secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY! } });
const BUCKET = process.env.S3_BUCKET!;

export const s3Storage: Storage = {
  async put(key, data, opts) {
    await s3.send(new PutObjectCommand({ Bucket: BUCKET, Key: key, Body: data as any, ContentType: opts?.contentType, CacheControl: opts?.cacheControl ?? 'public, max-age=31536000, immutable' }));
  },
  async getSignedUrl(key, ttlSec) {
    const url = await getSignedUrl(s3, new PutObjectCommand({ Bucket: BUCKET, Key: key }), { expiresIn: ttlSec });
    // 実運用では GET 用の署名URL（GetObjectCommand）を使