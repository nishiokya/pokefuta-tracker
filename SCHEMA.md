# Pokéfuta Dataset Schema

このドキュメントは `pokefuta.ndjson` (内部完全版) および `docs/pokefuta.ndjson` (公開用アクティブ版) に格納される各レコードのスキーマ仕様を定義します。

## 概要
- 形式: NDJSON (1 行 1 JSON オブジェクト)
- 文字コード: UTF-8
- 行末: `\n`
- ID: 数値文字列 (例: "123")
- 公開版は `status = active` のレコードのみを出力し、削除済みは内部版に保持します。

## フィールド一覧
| フィールド | 型 | 必須 | 説明 | 例 | 備考 |
|-----------|----|------|------|----|------|
| id | string | ✔ | マンホール固有の数値文字列 ID | "123" | URL 中 `/desc/{id}/` から抽出 |
| title | string | ✔ | 日本語タイトル / 見出し (ページ h1/h2) | "鹿児島県/指宿市" | 空文字の場合あり |
| title_en | string | ❌ | 英語版ページからのタイトル | "Poké Lids" | 取得失敗時は空 |
| title_zh | string | ❌ | 中国語版ページからのタイトル | "寶可夢人孔蓋" | 取得失敗時は空 |
| prefecture | string | ❌ | 都道府県 | "鹿児島県" | HTML 推測 + `dataset/title.tsv` 補正 |
| city | string | ❌ | 市区町村 | "指宿市" | 町村名まで判明すれば上書き |
| address | string | ❌ | 公開用住所 (正規化済みを優先) | "鹿児島県指宿市十二町" | `title.tsv` の `address_norm` → `address_raw` → HTML 順に利用 |
| building | string | ❌ | 設置施設・建物名 | "鹿児島中央駅" | `title.tsv` の `building` |
| address_raw | string | ❌ | 手入力の住所 (未正規化) | "鹿児島県鹿児島市中央町1-1" | `title.tsv` の `address_raw` |
| address_norm | string | ❌ | 正規化住所 | "鹿児島県鹿児島市中央町1-1" | `title.tsv` の `address_norm` |
| place_detail | string | ❌ | 施設内の位置や補足 | "駅前広場" | `title.tsv` `place_detail` |
| landmark | string | ❌ | 目印となる地物 | "アミュ広場" | `title.tsv` `landmark` |
| access | string | ❌ | アクセス情報 | "JR鹿児島中央駅直結" | `title.tsv` `access` |
| parking | string | ❌ | 駐車場情報 | "隣接コインパーキング有" | `title.tsv` `parking` |
| nearby_spots | string[] | ❌ | 周辺スポットタグ | ["アミュプラザ鹿児島"] | `title.tsv` `nearby_spots` を `|` 区切りで配列化 |
| tags | string[] | ❌ | カテゴリタグ | ["station","tourism"] | `title.tsv` `tags` |
| source_urls | string[] | ❌ | 参考リンク集 | ["https://example.com/info"] | `title.tsv` `source_urls` |
| verified_at | string (date) | ❌ | メタデータ最終確認日 (JST) | "2025-12-27" | `title.tsv` `verified_at` |
| confidence | number | ❌ | メタデータ確信度 (1-3など) | 3 | `title.tsv` `confidence` |
| city_url | string | ❌ | 市区町村公式 URL (未実装) | "" | 予約 (将来拡張) |
| lat | number | ✔ | 緯度 (WGS84) | 31.237194 | Google Maps リンク `q=` パラメータ抽出 |
| lng | number | ✔ | 経度 (WGS84) | 130.642861 | 同上 |
| pokemons | string[] | ✔ | 日本語ポケモン名一覧 | ["イーブイ"] | ページ内アンカーから簡易抽出 (ノイズ除去) |
| pokemons_en | string[] | ❌ | 英語ポケモン名一覧 | [] | 日本語とインデックス対応 試験的 |
| pokemons_zh | string[] | ❌ | 中国語ポケモン名一覧 | [] | 日本語とインデックス対応 試験的 |
| detail_url | string | ✔ | 元詳細ページ URL | "https://local.pokemon.jp/manhole/desc/123/?is_modal=1" | 直接参照可能 |
| prefecture_site_url | string | ❌ | 都道府県特設サイト URL | "" | 取得できた場合のみ |
| first_seen | string (ISO8601) | ✔ | 初回検出日時 (UTC) | "2025-10-18T00:00:00Z" | 初期化スクリプトまたはアップデータでセット |
| added_at | string (ISO8601) | ✔ | Web UI 最近追加フィルタ用エイリアス | "2025-10-18T00:00:00Z" | = first_seen (変更不可) |
| last_updated | string (ISO8601) | ✔ | 内容が変化した/状態変化した最新の更新日時 | "2025-12-27T06:15:42Z" | 差分や status 変化時のみ更新 (ノイズ削減) |
| status | string | ✔ | レコード状態 | "active" | "active" または "deleted" |

### `dataset/title.tsv` 由来のフィールド
- `building` / `address_raw` / `address_norm` / `place_detail` / `landmark` / `access` / `parking`
- `nearby_spots` / `tags` / `source_urls`
- `verified_at` / `confidence`

これらは手動管理の `dataset/title.tsv` (必要に応じて `title.csv`) から読み込まれ、`apply_title_metadata()` が NDJSON の各レコードへ自動反映します。ファイルを更新するだけでワークフロー実行時に差分が検出され、GitHub Actions が PR を作成します。

### 状態遷移
| 遷移 | 条件 | 影響 |
|------|------|------|
| (なし→active) | 初回取得成功 | first_seen/added_at/last_updated を同一時刻で設定 |
| active→deleted | 過去 active の ID が 404/座標解析失敗 | status=deleted, last_updated を削除確定時刻に更新 |
| deleted→active | 削除扱い ID が再び取得成功 | status=active に戻し last_updated 更新 (差分反映) |

### 差分検出対象フィールド
`CORE_COMPARE_FIELDS`（title / prefecture / city / address / building / address_norm / address_raw / lat / lng / pokemons など）と `status` を比較します。
- 配列フィールド (`pokemons`, `tags`, `nearby_spots`, `source_urls`) は集合ではなく配列比較ですが、スクレイパー/メタデータ更新時は同一順序で書き出すため意図せぬ diff は発生しません。
- `dataset/title.tsv` を編集しただけでも `apply_title_metadata()` が差分として検知し、`last_updated` と CHANGELOG が更新されます。
- 差分なしの定期再取得では `last_updated` を触らず PR ノイズを抑えます。

### レコード例 (active)
```json
{"id":"1","title":"鹿児島県/指宿市","title_en":"Poké Lids","title_zh":"寶可夢人孔蓋","prefecture":"鹿児島県","city":"指宿市","address":"鹿児島県指宿市湊2-5-33","building":"指宿駅前観光案内所","address_raw":"鹿児島県指宿市湊2-5-33","address_norm":"鹿児島県指宿市湊2-5-33","place_detail":"駅前広場","landmark":"指宿駅","access":"JR指宿駅徒歩1分","parking":"駅前駐車場を利用","nearby_spots":["砂むし会館"],"tags":["station","tourism"],"source_urls":["https://example.com/ibusuki"],"verified_at":"2025-12-27","confidence":3,"city_url":"","lat":31.237194,"lng":130.642861,"pokemons":["イーブイ"],"pokemons_en":[],"pokemons_zh":[],"detail_url":"https://local.pokemon.jp/manhole/desc/1/?is_modal=1","prefecture_site_url":"","first_seen":"2025-10-18T00:00:00Z","added_at":"2025-10-18T00:00:00Z","last_updated":"2025-12-27T06:11:32Z","status":"active"}
```

### レコード例 (deleted)
```json
{"id":"42","title":"香川県/多度津町","title_en":"Poké Lids","title_zh":"寶可夢人孔蓋","prefecture":"香川県","city":"多度津町","address":"","city_url":"","lat":34.272282,"lng":133.757247,"pokemons":["ヤドン"],"pokemons_en":[],"pokemons_zh":[],"detail_url":"https://local.pokemon.jp/manhole/desc/42/?is_modal=1","prefecture_site_url":"https://local.pokemon.jp/municipality/kagawa/","first_seen":"2025-09-25T03:10:00.000000+00:00","added_at":"2025-09-25T03:10:00.000000+00:00","last_updated":"2025-10-05T05:00:00.000000+00:00","status":"deleted"}
```
公開版 (`docs/pokefuta.ndjson`) には含まれません。

## 公開版と内部版の違い
| 項目 | 内部版 (apps/scraper/pokefuta.ndjson) | 公開版 (docs/pokefuta.ndjson) |
|------|---------------------------------------|-------------------------------|
| 削除済み | 保持 (status=deleted) | 除外 |
| スキーマ | フル (全フィールド) | 同じ (deleted 除外のみ) |
| 用途 | 履歴・再集計・再生性 | Web 表示 / 軽量配信 |

## ソート規則
内部ファイル書き込み時は以下キーで安定ソート:
1. `int(id)` 昇順
2. `status != 'active'` (active が先)

## 不変性・保証
| 項目 | 保証内容 |
|------|----------|
| id | 一意 / 再利用可能性はサーバ側仕様依存 (重複再出現で復活扱い) |
| first_seen | 一度設定後は変更しない |
| added_at | = first_seen (将来 first_seen と分離しない限り同値) |
| status=deleted | 削除後もレコードは内部版から削除しない (履歴維持) |

## 変更検出アルゴリズム (概要)
1. 1..N の候補 ID に対し詳細ページ取得
2. 404 → 既存 active なら status=deleted
3. HTML 解析失敗 → 上記と同様に削除候補
4. 解析成功 → 新規 or 既存更新
5. フィールド差分計算 → 差分ありなら CHANGELOG 追記

## エラーハンドリング方針
| ケース | 対応 |
|--------|------|
| タイムアウト/5xx | RETRY 後諦め・次 ID へ (既存 active は削除扱いにしない) |
| 部分的パース失敗 (座標なし) | active → deleted 扱い |
| JSON 書き込み失敗 | ログ出力のみ、プロセス継続 (再試行は未実装) |

## 今後の拡張候補フィールド
| フィールド | 型 | 目的 |
|------------|----|------|
| image_urls | string[] | 公式詳細内の画像一覧 |
| city_code | string | 行政コード紐付け |
| geo_source | string | 緯度経度取得手段メタデータ |
| content_hash | string | ページ本文ハッシュ (差分検出精度向上) |
| revision | number | レコード更新回数 |

## 利用上の注意
- NDJSON は巨大化を避けるため差分のみ別ファイルに分離する構成に将来変更する可能性があります。
- 外部再配布時は deleted レコードを除外し最新のみ提供してください。
- 緯度経度は公式ページ内リンク依存のため精度保証はありません (→ 将来はジオコーディング再検証予定)。
- `last_seen` / `source_last_checked` は 2025-10-19 のスキーマ改訂で廃止され `last_updated` に統合されました。

## ライセンス / 法的注意
ポケふた情報は公式サイトの公開情報を機械的に取得しているため、再利用ポリシーやクローリングルールの変更には随時対応が必要です。過度の頻度での再取得は控えてください。

---
最終更新: 2025-12-27
