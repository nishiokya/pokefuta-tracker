今日のX（Twitter）投稿候補を生成して、最適な1件の投稿文を作成・表示する。

```bash
cd "$(git rev-parse --show-toplevel)"
python3 apps/scraper/generate_social_posts.py
```

スクリプト実行後、以下の手順で今日の投稿文を作成すること：

## 手順

1. `docs/social-post-candidates.json` を読み込む（全候補リスト）
2. `docs/social-post-history.json` を読み込む（使用済みID管理）
3. 今日の日付・曜日・月・季節を踏まえて、最も面白い・タイムリーな候補を1件選ぶ
   - `history.used` にある `id` で `used_at` が30日以内のものは選ばない
   - 曜日ローテーションに縛られなくてよい。今日にふさわしいと思う候補を選ぶ
   - 例：夏休み前なら旅行訴求が強い `prefecture_rank` や `rare_area`、最新投稿があれば `latest_photo` など
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
6. `docs/social-post-history.json` の `used` 配列に追記して保存する：
   ```json
   {"id": "候補のid", "used_at": "YYYY-MM-DD"}
   ```
7. 投稿文（body の内容）をそのままユーザーに表示する（コピーしやすいように）
