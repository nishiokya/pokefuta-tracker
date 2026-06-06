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
   - 金    → `rare_area`
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
   - `prefecture_rank` タイプ: 都道府県マップ＋マンホール写真＋ポケモン統計の
     リッチSVGを自動生成（GeoJSON取得・ndjson参照・ローカル画像埋め込み）
   - その他タイプ: `docs/ogp_template/{type}.svg` のプレースホルダーを置換
9. `docs/social-post-image.jpg` を Read ツールで読み込み、投稿文の下に表示する
