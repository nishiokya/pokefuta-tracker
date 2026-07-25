# ポケふた設置場所メタデータ仕様

## 目的

`building` が未設定のポケふたを、再検証可能な根拠と統一したタグ語彙に基づいて補完する。
調査候補を公開データへ直接反映せず、候補作成・レビュー・採用を分離する。

## 正本と生成物

| データ | 役割 | 編集 |
|---|---|---|
| `dataset/manhole_titles.json` | 採用済み手動メタデータの正本 | 手動・Semantic Editor |
| `apps/scraper/pokefuta.ndjson` | 内部完全版 | 自動生成 |
| `docs/pokefuta.ndjson` | 公開用active版 | 自動生成 |
| 調査結果NDJSON | 採用前候補と監査証跡 | 調査エージェント |

`apps/scraper/pokefuta.ndjson` と `docs/*.ndjson` は直接編集しない。

## フィールドの意味

### `building`

訪問者が設置場所を特定するための、公式または広く通用する場所の固有名。
建築物に限らず、公園、駅前広場、道の駅、施設敷地などを含む。

例:

- `中央緑地公園`
- `豊橋駅南口駅前広場`
- `道の駅 紀宝町ウミガメ公園`

無名の道路、歩道、広場など、信頼できる固有名がない場合は無理に設定しない。

### `place_detail`

`building` の内部または周辺における詳細位置。単独では場所を一意に特定しにくい説明を入れる。

例:

- `正面入口横`
- `西口`
- `園内案内所前`

施設名と詳細位置を連結した文章を `building` に入れず、可能な限り分離する。

### `landmark`

設置場所そのものではないが、現地で目印になる地物。最寄り施設を設置場所と誤認しない。

### `tags`

検索、分類、称号生成に用いる管理語彙。既存コードとの互換性のため、値は名前空間を持たない
小文字の英単語またはsnake_caseによるフラットな文字列配列とする。

許可する語彙の機械可読な正本は
`schemas/manhole-tags.schema.json`とする。調査レコードの検証仕様は
`schemas/pokefuta-location-research.schema.json`とする。

## タグ分類

| 分類 | 目的 | 主なタグ |
|---|---|---|
| `place_type` | 設置場所の種別 | `park`, `museum`, `roadside`, `station`, `library`, `market`, `sports`, `camp`, `shrine`, `viewpoint` |
| `geography` | 周辺の地理特性 | `seaside`, `beach`, `lakeside`, `river`, `remote_island`, `nature`, `geosite` |
| `access` | 鉄道などからのアクセス | `in_station`, `station_front`, `near_station`, `far_station`, `rail_access_good` |
| `experience` | 訪問時に期待できる体験 | `tourism`, `food`, `family`, `history`, `culture`, `onsen`, `resort`, `illumination` |
| `relation` | 他マンホールとの関係 | `near_gundam_manhole`, `gundam_manhole_city`, `near_character_manhole`, `character_manhole_city` |
| `data_quality` | 内部の品質・由来管理 | `city_level_address`, `pokemon_lid` |

### タグ付与原則

- タグは名称から推測せず、公式情報、座標、現地写真などで確認できる事実に付ける。
- `place_type` と `geography` は同時に複数付与できる。
- `data_quality` は公開上の魅力や称号として扱わない。
- 算出可能な関係タグは、将来的に手動タグから自動算出へ移す。
- 施設が公園内にあるだけで、すべての体験タグを自動的に付与しない。
- 新しいタグは、意味、付与条件、公開可否をこの文書に追加してから使用する。

### 駅関連タグ

| タグ | 条件 |
|---|---|
| `in_station` | 駅舎、改札内、駅施設の内部に設置 |
| `station_front` | 駅前広場または駅出入口に直接面した場所に設置 |
| `near_station` | 駅構内・駅前ではないが、徒歩圏として定めた距離内 |
| `far_station` | 最寄り駅から遠く、自動車等が実質的な主要アクセス |
| `rail_access_good` | 鉄道で訪問しやすいことを示す表示用タグ |

`near_station` と `far_station` の距離閾値は、実データ検証後に別途確定する。
閾値確定前は機械的な新規付与を行わない。

### 水辺関連タグ

| タグ | 条件 |
|---|---|
| `seaside` | 設置地点または通常の見学位置から海を確認できる |
| `beach` | 海水浴場・砂浜を主目的とする場所に設置 |
| `lakeside` | 湖沼の岸辺または湖畔施設に設置 |
| `river` | 河岸、河川公園など河川との関係が明確 |

海に近いだけでは `seaside` としない。航空写真や距離だけで視認可能性を確定しない。

## 調査結果NDJSON

### 検証

調査結果は、正本への統合前に行単位で検証する。

```bash
python3 apps/tools/validate_location_research.py path/to/research.ndjson
```

正常時は終了コード`0`、検証エラー時は`1`、ファイルやSchemaを読み込めない場合は`2`を返す。
エラーには入力ファイルの行番号を含める。

### 形式

- UTF-8
- 1行1 JSONオブジェクト
- 行末はLF
- `id` は数値文字列
- 同じ調査単位内で `id` は一意
- 調査エージェントは採用済み正本を直接編集しない

### レコード例

```json
{"schema_version":1,"id":"44","candidate":{"building":"候補施設名","place_detail":"正面入口付近","tags":["park","tourism"]},"evidence":[{"url":"https://example.lg.jp/example","source_type":"municipality_official","summary":"自治体が同施設への設置を案内","published_at":null,"checked_at":"2026-07-25"}],"spatial_check":{"method":"official_coordinates","distance_m":4.2},"field_confidence":{"building":3,"place_detail":2,"tags":{"park":3,"tourism":2}},"confidence":2,"decision":"review","issues":[]}
```

### 必須フィールド

| フィールド | 型 | 説明 |
|---|---|---|
| `schema_version` | number | 本仕様のメジャーバージョン。初版は`1` |
| `id` | string | ポケふたID |
| `candidate` | object | 候補となるメタデータ |
| `evidence` | object[] | 根拠と確認日の一覧 |
| `field_confidence` | object | フィールド単位の確信度 |
| `confidence` | number | 候補全体の確信度 |
| `decision` | string | 調査時点の判断 |
| `issues` | string[] | 競合、移設、座標不一致など |

`candidate` は `building`, `place_detail`, `tags` のうち、候補があるものだけを持つ。
不明値を空文字で埋めない。

### `evidence`

| フィールド | 型 | 説明 |
|---|---|---|
| `url` | string | 根拠ページのURL |
| `source_type` | string | 情報源種別 |
| `summary` | string | 根拠の短い要約。転載にならない長さにする |
| `published_at` | string/null | 公開日。判明しない場合はnull |
| `checked_at` | string | JST基準の確認日`YYYY-MM-DD` |

情報源種別の優先順位:

1. `municipality_official` / `prefecture_official`
2. `facility_official`
3. `pokemon_official`
4. `tourism_official`
5. `open_data`
6. `map` / `search_result` / `user_content`

地図、検索結果、投稿コメントだけでは原則として確定しない。

### 空間確認

`spatial_check` は任意とし、実施した場合は方法と距離を記録する。

```json
{"method":"osm_polygon_contains","distance_m":0}
```

単純な最寄りPOIより、施設ポリゴンへの包含を優先する。複合施設、公園内施設、
移設前情報に注意し、資料間の座標差が30mを超える場合は原則レビュー対象とする。

### 確信度

| 値 | 基準 | 扱い |
|---|---|---|
| `3` | 公式資料が設置場所を明記し、住所または座標も一致 | 採用候補 |
| `2` | 独立した複数資料と空間情報が一致するが、明示性が不足 | 要レビュー |
| `1` | 地図、検索、OSMなどによる推定のみ | 保留 |
| `0` | 不一致、移設疑い、無名地点、確認不能 | 未解決 |

トップレベルの `confidence` は、採用予定フィールドの最低確信度とする。
タグごとの確信度は `field_confidence.tags` に記録する。

### 判断

| 値 | 意味 |
|---|---|
| `accept` | 正本へ統合可能 |
| `review` | 別担当または人間の確認が必要 |
| `unresolved` | 妥当な固有名を確認できない |
| `conflict` | 資料間に解消できない不一致がある |
| `relocated` | 移設情報があり、現設置場所の確認が必要 |

`unresolved` は失敗ではなく正当な調査結果として扱う。

## 調査とレビュー

1. 既存タグ、住所、座標、オープンデータから候補を作る。
2. 自治体・施設などの公式情報で確認する。
3. 調査結果NDJSONへ根拠と確信度を記録する。
4. `confidence = 2`、競合全件、`confidence = 3`のランダム10%を別担当が監査する。
5. 親担当だけが採用結果を`dataset/manhole_titles.json`へ統合する。
6. 生成処理を実行して内部版・公開版へ反映する。

調査は原則として1地点3検索、公式ページ5件、10分を上限とし、見つからない場合は
推測で埋めず`unresolved`とする。

調査キュー、結果の保存規約、命名規則、保持方針は
`dataset/research/pokefuta-location/README.md`に定める。

## 未決事項

- `near_station`と`far_station`の距離閾値
- 既存タグのうち表示用・算出用・内部用を物理的に分離するか
- 既存の出典なし`building`をどの範囲まで再監査するか
