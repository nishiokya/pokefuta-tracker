今日のX（Twitter）投稿候補を生成して、最適な1件の投稿文を作成・表示する。

```bash
cd "$(git rev-parse --show-toplevel)"
python3 apps/scraper/generate_social_posts.py
```

スクリプト実行後、以下の手順で今日の投稿文を作成すること：

## 手順

1. `docs/social-post-candidates.json` を読み込む（全候補リスト）
2. `docs/social-post-history.json` を読み込む（使用済みID管理）。ファイルが存在しない場合は `{"used": []}` として扱う
3. 今日の曜日に対応するタイプを選ぶ（スケジュール厳守）：
   - 月・日 → `prefecture_rank`
   - 火    → `travel_trivia`
   - 水    → `latest_photo`
   - 木    → `pokemon_rank`
   - 金    → `rare_area` / `michineki` / `remote_island` の3週ローテ
             （`history.used` を見て、この3タイプの中で最も `used_at` が古いもの、または未使用のタイプを優先する）
   - 土    → `no_photo`

   そのタイプの候補の中から、`history.used` にある `id` で `used_at` が30日以内のものを除外した上で最適な1件を選ぶ。
   （同タイプの候補が全て30日除外済みの場合のみ、他タイプから代替してよい）
4. 選んだ候補の `raw_data` をもとに X 投稿文を書く（以下のルールを守ること）：
   - 本文は140文字前後（URLを除いた文章部分）
   - 最初の1行に数字か驚きを入れる
   - Pokemon GO 関連語は使わない
   - 旅行・地域・発見・地域観光の文脈を入れる
   - 「行ったこと・見つけたことに価値がある」という視点を盛り込む
   - ハッシュタグは `#ポケふた #ポケモンマンホール` の2つのみ
   - 本文の最後にURLを追記
   - **`latest_photo` タイプ専用ルール：**
     - encyclopedic tone（「〇〇市にポケふたがある」形式）は禁止
     - リードは「〇〇市のポケふたに新しい写真が届きました」形式のイベント文体
     - `photo_rank == "first_ever"` → 「初めての写真投稿」「はじめての1枚」を冒頭で強調
     - `photo_rank == "long_gap"`  → 「久しぶりの写真投稿」表現を冒頭に盛り込む
     - `display_name` が空でない → 「〇〇さんが撮影した写真」のように撮影者に言及
     - ポケモン名と地域の関連（季節感・風土・地名との語呂）を1文で添える
     - 主役は「写真を届けた行為」——ポケふたの存在説明は不要
5. `docs/social-post-daily.json` を書き込む（上書き）：
   ```json
   {
     "date": "YYYY-MM-DD",
     "id": "候補のid",
     "type": "候補のtype",
     "body": "投稿本文（URLとハッシュタグ含む）",
     "url": "候補のurl",
     "hashtags": ["#ポケふた", "#ポケモンマンホール"],
     "imageType": "候補のimageType",
     "selected_reason": "選んだ理由を一言"
   }
   ```
6. `docs/social-post-history.json` の `used` 配列に追記して保存する（ファイルが存在しない場合は新規作成）：
   ```json
   {"id": "候補のid", "used_at": "YYYY-MM-DD"}
   ```
7. 投稿文（body の内容）をそのままユーザーに表示する（コピーしやすいように）
8. 以下を実行して投稿画像を生成する：
   ```bash
   cd "$(git rev-parse --show-toplevel)"
   python3 apps/scraper/generate_social_ogp.py
   ```
   **テーマ別OGP生成ルール：**
   - `prefecture_rank` / `rare_area` / `no_photo` — GeoJSON ワイヤーフレーム都道府県マップ
     - マンホール数 ≤15: 写真サムネイル（円形・マンホール位置にズーム）
     - マンホール数 >15: カラードット（県全体を俯瞰）
     - GeoJSONは `dataset/prefecture_boundaries/` にキャッシュ（初回のみDL）
   - `travel_trivia` (ibusuki_eevee_9) — 専用テーマ `ibusuki_eevee_complete`
     - イーブイ中央（金枠）＋進化形8種を円形配置
     - バッジ「ALL 9」、タイトル「イーブイ系コンプリート」
     - 指宿半島ワイヤーフレームを背景テクスチャとして使用
   - `latest_photo` — `docs/ogp_template/latest_photo.svg` に写真を base64 埋め込み
   - その他タイプ — `docs/ogp_template/pokefuta_ogp_{theme}.svg` のプレースホルダーを置換
9. `docs/social-post-image.jpg` を Read ツールで読み込み、投稿文の下に表示する
