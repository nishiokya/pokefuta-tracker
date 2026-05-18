# マンホール称号タグ 仕様・管理ドキュメント

マンホール詳細ページに「日本最北のポケふた」「離島のポケふた」のような
**SNS で映える称号タグ** を付与するための仕様書。称号カタログ・算出ロジック・
管理方法・各反映先への出し分けルールを定義する。コード実装はここに記載した設計に従う。

- 対象データ: `docs/pokefuta.ndjson`（公開版・active のみ。`SCHEMA.md` 準拠）
- 反映先: ①詳細ページのバッジ ②X シェア文のハッシュタグ ③OGP 画像
- 単一ソース: 称号は 1 つの関数で算出し、3 反映先すべてが同じ結果を使う（食い違い防止）

---

## 1. 称号カタログ

称号には `key`（内部ID）・`label`（バッジ文言）・`emoji`・`hashtag`（X 用）・
`priority`（数値が大きいほど上位表示）を持たせる。

### ティア1: 自動算出称号（人手メンテ不要）

`docs/pokefuta.ndjson` だけから算出できる。データ更新で自動的に追従するため、
**運用上さわるものは無い**。

| key | label（バッジ） | hashtag | 算出条件 | priority |
|-----|----------------|---------|----------|----------|
| `north_end` | 🧭 日本最北のポケふた | `#日本最北のポケふた` | active 全件で `lat` 最大の1件 | 100 |
| `south_end` | 🧭 日本最南のポケふた | `#日本最南のポケふた` | `lat` 最小の1件 | 100 |
| `east_end` | 🧭 日本最東のポケふた | `#日本最東のポケふた` | `lng` 最大の1件 | 100 |
| `west_end` | 🧭 日本最西のポケふた | `#日本最西のポケふた` | `lng` 最小の1件 | 100 |
| `unique_pokemon` | ⭐ このポケモンは全国でここだけ | `#激レアポケふた` | 同ポケモンが他レコードに無い | 90 |
| `only_in_pref` | 🗾 ○○で唯一のポケふた | `#○○唯一のポケふた` | 同 `prefecture` が自分のみ | 80 |
| `rare_pokemon` | 🌟 レアポケふた（全国○枚） | `#レアポケふた` | 同ポケモンの総数 ≤ 3 | 70 |
| `lone` | 🌲 ぽつんと一枚（30km圏に他なし） | `#秘境ポケふた` | 30km 以内に他マンホール 0 件 | 65 |
| `only_in_city` | 🏘 ○○で唯一のポケふた | `#ご当地ポケふた` | 同 `prefecture+city` が自分のみ かつ `only_in_pref` 不成立 | 60 |
| `pref_top` | 🏆 ○○は設置数日本一（○枚） | `#ポケふた聖地` | `prefecture` 件数が全国最多の県に属する | 55 |
| `newest` | 🆕 最新設置ロット | `#新作ポケふた` | `added_at` が全件中の最新日付に一致 | 50 |
| `pioneer` | 🥇 初期ポケふた | `#元祖ポケふた` | `added_at` の年が最古年に一致 | 45 |

> `label` の `○○` は実行時に `prefecture` / `city` / 件数で置換する。

### ティア2: 離島・地理称号（手動マスタで管理）

判定に必要なデータ（島の所属・海岸線・標高）がリポジトリに無いため、
`dataset/manhole_titles.json` の手動マスタで管理する。

| key | label（バッジ） | hashtag | 判定 | priority |
|-----|----------------|---------|------|----------|
| `remote_island` | 🏝 離島のポケふた（{島名}） | `#離島ポケふた` `#{島名}` | マスタの `islands` に当該 id / `prefecture+city` が登録 | 95 |
| `seaside` | 🌊 海が見えるポケふた | `#海沿いポケふた` | `manhole_titles.json` の `manholes."<id>".tags` に `beach` か `seaside` を含む | 40 |

> `seaside` は新規データ取得をせず統合JSONの `manholes."<id>".tags`（旧 `title.tsv` 由来）の値を再利用するだけの位置づけ。
> 海岸線距離・標高による自動判定は本仕様のスコープ外（将来拡張）。

---

## 2. 算出ロジック（実装時に従う設計）

### 2.1 単一ソースモジュール

新規 `apps/scraper/manhole_titles.py`:

```python
# Title = {"key": str, "label": str, "hashtag": str, "emoji": str, "priority": int}

def build_title_context(manholes: list[dict], master: dict) -> dict:
    """全件を1回走査して算出に必要な集計を作る（最北/最南/最東/最西の id,
    prefecture 件数, ポケモン件数, 最新/最古 added_at, 設置数1位の県 など）。"""

def compute_titles(manhole: dict, ctx: dict,
                    *, nearby_count: int) -> list[dict]:
    """1マンホールの称号リストを priority 降順で返す。
    ティア1は ctx から、ティア2は master（islands / 語彙定義）から判定。"""
```

### 2.2 既存処理の再利用（重複実装しない）

| 必要な集計 | 既存の供給元 |
|-----------|-------------|
| 都道府県別件数 / ポケモン別件数 | `generate_manhole_pages.py` の `pref_index`(:1681) `pokemon_index`(:1694)、OGP `build_stats`(:227) |
| 30km 以内件数 | `generate_manhole_pages.py` `nearby_count`(:1745)、OGP `_nearby_count`(:246) |
| 市区町村別件数 | `generate_manhole_pages.py` `city_index`(:1687) |
| 緯度経度の最大/最小 | `build_title_context` で全件から1回算出（`build_stats` と同じ全件走査の中に同居させる） |

ページ生成・OGP 生成はすでに全件ループと上記インデックスを持つため、
`build_title_context` をそのループの近くで1回呼び、各マンホールで
`compute_titles(...)` を呼ぶだけで追加コストはほぼゼロ。

### 2.3 ノイズ抑制ルール

- `compute_titles` は priority 降順・同点は表に並んだ順で安定ソート。
- `only_in_pref` が成立する時、ページの既存事務バッジ
  `○○県 N枚`（`generate_manhole_pages.py:543-544`）は **抑制**（情報が重複し矛盾するため称号優先）。
- `lone` が成立する時、既存 `30km以内にN件`（:549-550）バッジは抑制（同上）。
- `north_end` 等の4端称号は同点があり得ない（厳密 max/min の1件）。同値が出た場合は
  `id` 昇順で先勝ち、と実装で固定する。

---

## 3. 管理方法

```
docs/pokefuta.ndjson ───────────┐
                                ├─→ build_title_context → compute_titles ─→ ①ページ ②OGP ③シェア文
dataset/manhole_titles.json ────┘
（手動マスタ: 離島リスト＋語彙定義）
```

### 3.1 ティア1（自動算出）— 操作不要

データが更新されれば称号も自動で移る。例: より北のマンホールが追加されたら
`north_end` は自動で新しい id へ移動する。人手の編集対象は無い。

### 3.2 ティア2（手動マスタ）— `dataset/manhole_titles.json`（統合版 v2）

ユーザーが編集する唯一のファイル。旧 `dataset/title.tsv`（id 別メタデータ）と
旧 `dataset/city_link.tsv`（自治体公式 URL）をこの1ファイルに統合した。
構造は4ブロック:

```jsonc
{
  "version": 2,
  "vocabulary": {        // 称号語彙: 文言/絵文字/ハッシュタグ/優先度/有効フラグ
    "north_end":     { "enabled": true, "emoji": "🧭", "label": "日本最北のポケふた", "hashtag": "#日本最北のポケふた", "priority": 100 },
    "remote_island": { "enabled": true, "emoji": "🏝", "label": "離島のポケふた（{island}）", "hashtag": "#離島ポケふた", "priority": 95 }
    /* 全14称号。{prefecture}/{city}/{count}/{island} は実行時に置換 */
  },
  "islands": [           // 離島称号の判定元。ids 優先、無ければ prefecture+city 一致
    { "island": "石垣島", "prefecture": "沖縄県", "city": "石垣", "ids": ["235"] },
    { "island": "佐渡島", "prefecture": "新潟県", "city": "佐渡", "ids": [] }
  ],
  "city_links": [        // 旧 city_link.tsv: 自治体/県の公式ポケふた案内ページ
    { "prefecture": "北海道", "city": "稚内市", "url": "https://www.city.wakkanai.hokkaido.jp/..." }
    /* 31件。city が「（県全体案内）」の行は都道府県全体の案内ページ */
  ],
  "manholes": {          // 旧 title.tsv: id 別の手動メタデータ（空欄は省略）
    "404": { "building": "金シャチ横丁　宗春ゾーン（東門エリア）", "prefecture": "愛知県",
             "city": "名古屋市中区", "address_norm": "愛知県名古屋市中区二の丸1番2・3号",
             "tags": ["food", "tourism"], "verified_at": "2025-12-27", "confidence": 3 }
    /* 39件。tags は `|` 区切りを配列化。confidence は整数 */
  }
}
```

編集操作の早見表:

| やりたいこと | 編集箇所 |
|--------------|----------|
| 離島称号を1件追加 | `islands` に1要素追加 |
| 称号の文言/優先度変更・一時停止 | `vocabulary` の該当キー（`enabled:false` で停止） |
| マンホールのカテゴリタグ追加（例 `seaside`） | `manholes."<id>".tags` に追加 |
| 自治体公式ページ追加・更新 | `city_links` に1要素追加 |

- 編集フローは旧 `title.tsv` と同じ思想（`SCHEMA.md` 「`title.tsv` 由来のフィールド」節）。
  ファイル更新でワークフローが差分検知し PR 化。
- クローラー／ジェネレータ側の **読み込み口の差し替え（旧 TSV → このJSON）は別対応**。
  本作業はデータ統合とドキュメント整備までで、コードは未変更。
- リポジトリに YAML が無いため JSON で統一（`docs/latest-manhole-photos.json` 等の慣習に合わせる）。

### 3.3 統合時に実施した `title.tsv` 修復

統合作業中、旧 `dataset/title.tsv` の **全39行が15列ヘッダーに対し13〜14列**しかなく、
`csv.DictReader`（既存クローラー `load_title_metadata` と同じ）で読むと値が右へズレ、
`parking` が空・`food|tourism` が `nearby_spots`・日付が `source_urls`・
`confidence` が欠落する状態だった（既存クローラーも同じ壊れ方で読んでいた可能性）。

対応（ユーザー判断に基づく）:

1. `dataset/title.tsv` 自体を正しい15列へ再構成して上書き修復。
   - 復元方式: 先頭7列（id..place_detail）は位置で確定、
     末尾は `confidence`=整数・`verified_at`=日付で右アンカー判定、
     `|` を含むカテゴリ値は `tags` 列へ（`parking` ではなく）。
   - 39行すべてで日付＋confidence が揃い、想定外の余り値ゼロを確認済み。
2. 修復後の `title.tsv` を `manhole_titles.json` の `manholes` ブロックへ統合
   （空欄フィールドは省略、`tags` は `|` 区切りを配列化、`confidence` は整数）。

> `food|tourism` 等は SCHEMA 上の `parking`（駐車場の自由文）ではなく
> `tags`（カテゴリタグ）の性質のため、修復時に `tags` 列へ寄せた。
> 称号 `seaside` の判定も今後はこの `manholes."<id>".tags` の `beach`/`seaside` を見る。

### 3.3 SCHEMA.md への追記方針

`SCHEMA.md` に「`dataset/manhole_titles.json` 由来の称号」節を追加し、
本ファイルへの参照と、`islands` / `vocabulary` の編集が PR 化される運用を明記する
（実装フェーズで `SCHEMA.md` を1節追記）。

---

## 4. 反映先ごとの出し分けルール

| 反映先 | 上限 | 仕様 |
|--------|------|------|
| 詳細ページ バッジ | 上位 **3件** | `compute_titles` の上位3件を新クラス（`hero-badge` 風）で描画。§2.3 の抑制ルール適用 |
| X シェア文 ハッシュタグ | 上位 **2件** | 上位2件の `hashtag` を既存 `_x_text`(`generate_manhole_pages.py:554-570`) の `#ポケふた #ポケモンマンホール` の **前** に挿入。LINE 共有 URL は変更不要 |
| OGP 画像 | **1件** | 最上位1件を既存 `_draw_pill`(`generate_manhole_ogp.py:353`) でカラーピル描画。`compose_manhole`(:377) に1行追加。生成負荷を抑えるため1件上限 |

称号が0件のマンホールは従来表示のまま（既存挙動を壊さない）。

---

## 5. 検証（実データ照合）

`docs/pokefuta.ndjson`（active 470 件・2026-05-18 時点）での手計算例。
実装後はこれらが期待通り算出されることを確認する。

| マンホール | 期待される称号（上位） |
|-----------|----------------------|
| id 67 北海道稚内（lat 45.417236） | `north_end` 🧭 日本最北のポケふた |
| id 189 北海道根室（lng 145.598194） | `east_end` 🧭 日本最東のポケふた |
| id 235 沖縄県石垣（lat 24.337418 / lng 124.156947、石垣島） | `south_end`・`west_end`・`remote_island`（石垣島）— priority 上位3に集約 |
| 北海道の任意（全国最多 50 枚） | `pref_top` 🏆 北海道は設置数日本一（50枚） |
| 同ポケモンが1枚しか無いマンホール | `unique_pokemon` ⭐ 全国でここだけ／既存「同じポケモン」事務バッジは抑制 |

検証手順:

1. 本ドキュメントの各 `priority` と §2.3 抑制ルールが「バッジ3 / シェア2 / OGP1」の
   上限と矛盾しないことをレビュー。
2. `dataset/manhole_titles.json` の雛形を読み込み、id 235 が `remote_island`（石垣島）を
   返すこと、id 67 が `north_end` を返すことを実装後にスポット確認。
3. 称号0件マンホールで既存ページ／OGP／シェア文が従来どおりであることを確認。
