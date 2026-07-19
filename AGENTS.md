manhole_titles.jsonは手動で更新している
dataset/prefecture_events.json は手動更新（都道府県ページに出す開催中スタンプラリー等のリンク。end_date 過ぎは日次再生成で自動非表示）
pokefuta.ndjsonはapps/scraperで更新している
latest-manhole-photos.json と docs/api/*.json は import-manhole-photos.yml が Supabase から日次一括生成（画像DL込み。pokefuta.com アプリの /api/manholes・/api/site-stats は docs/api を読む。手動で回すときだけ `/import-photos` スキル）

## ディレクトリ構成

- `apps/scraper/` — GitHub Actions から自動実行されるスクリプト群（update-pokefuta.yml / pages-deploy.yml / import-manhole-photos.yml）
  - `address_parser.py` / `manhole_titles.py` は上記スクリプトの内部ライブラリ
- `apps/tools/` — 手動実行ツール・初期化アーカイブ（例外: import_latest_manhole_photos.py は import-manhole-photos.yml からも呼ばれる）
- `apps/web/` — フロントエンド

## バッチワークフロー規約

`.github/workflows/` を新規作成・変更するときは以下に従うこと。過去に**規約が無いまま各ワークフローが別々に育ち、timeout 未設定・依存の二重管理・クロスリポジトリ依存といった事故要因が溜まった**ため明文化した。

### どの家系で作るかを最初に決める

| 家系 | 挙動 | 使いどころ | 例 |
|---|---|---|---|
| **A: 自動マージ** | ブランチ→PR作成→**即 squash マージ**→`gh workflow run pages-deploy.yml` で明示起動 | 毎日確実に本番へ出す必要があるデータ。人のレビューを待たない | `import-manhole-photos.yml` |
| **B: レビュー待ち** | `peter-evans/create-pull-request@v8` で PR を作って放置 | 中身を人が見てからマージしたいデータセット更新 | `update-pokefuta.yml` / `update-design-manholes.yml` |
| **C: 読み取り専用** | 何も書かない。異常時に失敗させるだけ | 監視・検証 | `check-site-stats.yml` / `production-url-check.yml` |

家系AとBが形式的にPRを作るのは `main` が「PR必須」ルールのため。**家系Aは人の目を通らない**ので、壊れた出力がそのまま本番に出ることを踏まえて作ること。ワークフロー冒頭のコメントにどの家系かを明記する。

### 必ず守ること

- **`timeout-minutes` を必ず書く。** 既定値は6時間で、ハングすると runner をその間占有する
- **Python は `actions/setup-python@v6` + `python-version: '3.11'` で固定する。** ランナー既定の python に依存しない
- **依存は `requirements.txt` に集約する。** ワークフロー内で `pip install <パッケージ名>` を直接書かない（バージョン非固定で上流の破壊的変更をそのまま踏むため）
- **定期実行するワークフローには `concurrency` を付ける。** 手動実行と定時実行の衝突を防ぐ
- **外部リポジトリを `actions/checkout` するときは `ref:` をタグかコミットSHAに固定する。** 以前 `nishiokya/pokefuta` を HEAD で引いてスクリプトを実行しており、相手側の変更で日次ジョブが黙って壊れる状態だった（現在は tracker 側へ移管して解消済み）
- **同じ Supabase テーブルを複数のワークフローから引かない。** 取得は1ジョブに集約する。かつては写真取込とスナップショット生成が同じ `photo` / `visit` を別々に引いていた
- **cron を変更するときは前後のワークフローとの順序を確認する。** `import-manhole-photos.yml`（05:30 JST）→ Pages デプロイ → `check-site-stats.yml`（08:00 JST）は**この順序に依存**しており、崩すと検証が生成を追い越して毎日誤検知する

### テストについて

テストファイルは20個以上あるが **CI で走っているのはごく一部**。ワークフローからスクリプトを呼ぶなら、対応するテストを実行するステップも同じワークフローに入れること。
