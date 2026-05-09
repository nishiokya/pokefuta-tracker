# 都道府県主体ポケモンマンホール クリーニング

## 概要

このドキュメントでは、ポケモンマンホールデータから都道府県主体のページURLを抽出・クリーニングするプロセスについて説明します。

## 問題

元のデータでは、`pokemons`フィールドに実際のポケモン名と都道府県ページへのリンク表記が混在していました：

```json
{
  "pokemons": ["カブト", "ローカルActs岩手県ページへ"]
}
```

## ソリューション

### 1. クリーニングスクリプト: `clean_prefecture_urls.py`

**機能:**
- `pokemons`フィールドから「ローカルActs{都道府県}ページへ」パターンを検出
- 都道府県URLを`prefecture_site_url`フィールドに移動
- `is_prefecture_site`フラグを`true`に設定
- 実際のポケモン名のみを`pokemons`フィールドに保持

**使用方法:**
```bash
python3 clean_prefecture_urls.py \
  --input pokefuta.ndjson \
  --output pokefuta_cleaned.ndjson \
  --log-level INFO
```

**結果（実行例）:**
```
Starting prefecture URL cleaning
Input: pokefuta.ndjson
Output: pokefuta_cleaned.ndjson
Loaded 470 records

ID 10: Extracted prefecture URL: ローカルActs岩手県ページへ
  - Cleaned pokemons: ['カブト']
ID 11: Extracted prefecture URL: ローカルActs岩手県ページへ
  - Cleaned pokemons: ['プテラ']
...

Cleaning complete:
  - Cleaned: 323
  - Unchanged: 147
  - Failed: 0
```

### 2. スキーマ更新

`schema/database.sql`に以下のフィールドを追加：

```sql
prefecture_site_url text,              -- 都道府県主体のページURL
is_prefecture_site boolean default false, -- 都道府県主体かどうか
```

## データ処理結果

### 統計情報

**都道府県別の都道府県主体マンホール件数:**

| 都道府県 | 件数 |
|---------|------|
| 北海道 | 50 |
| 福島県 | 43 |
| 宮城県 | 37 |
| 岩手県 | 36 |
| 三重県 | 31 |
| 宮崎県 | 26 |
| 鳥取県 | 20 |
| 高知県 | 18 |
| 香川県 | 18 |
| 福井県 | 17 |
| 沖縄県 | 17 |
| 長崎県 | 10 |

**合計:**
- 処理対象レコード: 470
- クリーニング対象: 323 (68.7%)
- 都道府県主体: 12都道府県
- 変更なし: 147 (31.3%)

### クリーニング前後の比較

**クリーニング前:**
```json
{
  "id": "10",
  "pokemons": ["カブト", "ローカルActs岩手県ページへ"],
  "prefecture_site_url": "",
  "is_prefecture_site": false
}
```

**クリーニング後:**
```json
{
  "id": "10",
  "pokemons": ["カブト"],
  "prefecture_site_url": "ローカルActs岩手県ページへ",
  "is_prefecture_site": true
}
```

## 使用例

### クエリ例: 都道府県主体のマンホール取得

```bash
# 都道府県主体のマンホール一覧
cat pokefuta_cleaned.ndjson | jq 'select(.is_prefecture_site == true)'

# 岩手県の都道府県主体マンホール
cat pokefuta_cleaned.ndjson | jq 'select(.is_prefecture_site == true and .prefecture == "岩手県")'

# 都道府県別集計
cat pokefuta_cleaned.ndjson | \
  jq -r 'select(.is_prefecture_site == true) | .prefecture' | \
  sort | uniq -c | sort -rn
```

## ファイル構成

- `clean_prefecture_urls.py` - 都道府県URLをpokemons から抽出するスクリプト
- `prefecture_url_mapping.py` - 都道府県URLの対応表（テキスト表記 → 実URL）
- `replace_prefecture_urls.py` - テキスト表記を実URLに置換するスクリプト
- `pokefuta.ndjson` - 元のデータ（変更なし）
- `pokefuta_cleaned.ndjson` - クリーニング済みデータ（URLはテキスト表記）
- `pokefuta_with_urls.ndjson` - 最終データ（URLを実URLに置換済み）
- `schema/database.sql` - 更新されたスキーマ定義

## 今後の改善

### 処理パイプライン

**ステップ1: クリーニング**
```bash
python3 clean_prefecture_urls.py \
  --input pokefuta.ndjson \
  --output pokefuta_cleaned.ndjson
```

**ステップ2: URL置換**
```bash
python3 replace_prefecture_urls.py \
  --input pokefuta_cleaned.ndjson \
  --output pokefuta_with_urls.ndjson
```

### 対応する都道府県URLs

| 都道府県 | URL |
|---------|-----|
| 北海道 | https://local.pokemon.jp/municipality/hokkaido/ |
| 岩手県 | https://local.pokemon.jp/municipality/iwate/ |
| 宮城県 | https://local.pokemon.jp/municipality/miyagi/ |
| 福島県 | https://local.pokemon.jp/municipality/fukushima/ |
| 鳥取県 | https://local.pokemon.jp/municipality/tottori/ |
| 福井県 | https://local.pokemon.jp/municipality/fukui/ |
| 香川県 | https://local.pokemon.jp/municipality/kagawa/ |
| 三重県 | https://local.pokemon.jp/municipality/mie/ |
| 高知県 | https://local.pokemon.jp/municipality/kochi/ |
| 長崎県 | https://local.pokemon.jp/municipality/nagasaki/ |
| 宮崎県 | https://local.pokemon.jp/municipality/miyazaki/ |
| 沖縄県 | https://local.pokemon.jp/municipality/okinawa/ |

### URLパターン

```
https://local.pokemon.jp/municipality/{prefecture_code}/
```

県コードはローマ字の小文字版です（hokkaido, iwate, kagawa など）

## 今後の改善

1. **データ統合**
   - クリーニング済みデータをメインのNDJSONに統合
   - 重複排除とマージ処理

2. **品質管理**
   - 抽出されたURLの妥当性チェック
   - ポケモン名の標準化

3. **自動化**
   - スクレイピング時にこのクリーニングを自動適用
   - 定期的なメンテナンス処理の実装

## トラブルシューティング

### URLパターンが抽出されない場合

- パターン：`ローカルActs{都道府県}ページへ`に合致しているか確認
- 都道府県の正式名称（県/府/道/都を含む）が入っているか確認
- ログレベルを`DEBUG`に設定して詳細を確認

```bash
python3 clean_prefecture_urls.py \
  --input pokefuta.ndjson \
  --output pokefuta_cleaned.ndjson \
  --log-level DEBUG
```

### スキーママイグレーション

PostgreSQL環境での適用：

```sql
ALTER TABLE manhole 
ADD COLUMN prefecture_site_url text,
ADD COLUMN is_prefecture_site boolean DEFAULT false;
```
