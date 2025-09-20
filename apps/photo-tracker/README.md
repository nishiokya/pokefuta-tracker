# 🗾 ポケふた写真トラッカー

ポケモンマンホール（ポケふた）の訪問記録と写真を管理するPWAアプリケーション

## 📱 概要

家族や個人の「訪問したポケモンマンホール」の写真・訪問記録を、スマホからサクッと登録・閲覧・共有できる仕組みです。

既存のポケふた位置データ（自作スクレイパのJSONなど）と連携し、地図上での可視化・重複防止・未訪問の発見を支援します。

## ✨ 主な機能

### MVP機能
- 📧 **Emailログイン** - Supabase Auth
- 📸 **写真アップロード** - 自動位置/日時抽出（EXIF）
- 🎯 **近傍マッチング** - 近くのポケふた候補提示→確定
- 🗺️ **地図表示** - 訪問済/未訪問を色分け
- 🔍 **検索/フィルタ** - 県・市・ポケモン別

### 将来機能
- 📱 LINE OAuth + Bot通知
- 🔗 アルバム共有（署名URL）
- 🏆 バッジ/統計（県/市達成、年間訪問数）
- 👨‍👩‍👧‍👦 家族グループ共有
- 🔄 公式データの自動クロール更新

## 🏗️ 技術スタック

- **Frontend**: Next.js 14 + TypeScript + Tailwind CSS
- **Backend**: Supabase (Auth + Database + Storage)
- **Database**: PostgreSQL + PostGIS (地理拡張)
- **Maps**: Leaflet + React Leaflet
- **PWA**: next-pwa
- **Deployment**: Vercel

## 📊 データベース設計

```sql
-- ユーザー（Supabase Auth拡張）
app_user (id, auth_uid, display_name, stats...)

-- ポケふたマスタ（スクレイプデータ）
manhole (id, title, prefecture, location, pokemons...)

-- 訪問記録
visit (id, user_id, manhole_id, shot_location, shot_at, note...)

-- 写真
photo (id, visit_id, storage_key, exif, thumbnails...)

-- 共有リンク
shared_link (id, visit_id, token, expires_at...)
```

## 🚀 セットアップ

### 前提条件

- Node.js 18+
- npm または yarn
- Supabaseプロジェクト

### インストール

1. 依存関係のインストール：
```bash
npm install
```

2. 環境変数の設定：
```bash
cp .env.example .env.local
```

3. Supabaseの設定：
   - Supabaseプロジェクトを作成
   - データベースマイグレーションを実行
   - Storageバケットを作成

4. 開発サーバーの起動：
```bash
npm run dev
```

### 環境変数

```bash
# Supabase
NEXT_PUBLIC_SUPABASE_URL=your_supabase_project_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_key

# Storage
SUPABASE_BUCKET=photos
STORAGE_PROVIDER=supabase

# App Configuration
NEXT_PUBLIC_APP_URL=http://localhost:3000
POKEFUTA_DATA_URL=/api/manholes
```

## 📱 PWA機能

- **オフライン対応**: IndexedDBで写真を一時保存
- **カメラアクセス**: ネイティブカメラ起動
- **位置情報**: GPS/EXIF座標取得
- **プッシュ通知**: 将来実装予定

## 🗺️ マップ機能

- **ベースレイヤ**: OpenStreetMap
- **マーカー**: 訪問済み（●）/ 未訪問（○）
- **クラスタリング**: ズームレベル別グループ化
- **フィルタ**: 都道府県/ポケモン別表示

## 📸 写真処理

1. **アップロード**: ドラッグ&ドロップ or カメラ
2. **EXIF解析**: 位置情報・撮影日時抽出
3. **重複検出**: SHA-256ハッシュ比較
4. **サムネイル生成**: 320px/800px/1600px
5. **ストレージ保存**: Supabase Storage

## 🔍 近傍マッチング

1. **位置取得**: EXIF GPS or 端末現在地
2. **候補検索**: 半径100m以内のマンホール
3. **ユーザー選択**: 候補リストから確定
4. **新規登録**: 該当なしの場合は仮ID保存

## 🛡️ セキュリティ

- **RLS**: Row Level Security で自分のデータのみアクセス
- **署名URL**: 期限付きファイルアクセス
- **EXIF**: 公開時は位置情報を市区町村レベルに丸め

## 📊 コスト見積もり

- **Vercel**: $0-20/月（Hobby→Pro）
- **Supabase**: $0-25/月（Free→Pro）
- **ドメイン**: ¥1,000/年
- **合計**: ¥1,000-5,000/月程度

## 🧪 テスト

```bash
# 型チェック
npm run type-check

# Lint
npm run lint

# ビルドテスト
npm run build
```

## 📄 ライセンス

MIT License

## 👥 貢献

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 🐛 バグ報告・機能要求

GitHub Issuesをご利用ください。

---

🤖 **Generated with [Claude Code](https://claude.ai/code)**