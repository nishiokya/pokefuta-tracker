manhole_titles.jsonは手動で更新している
dataset/prefecture_events.json は手動更新（都道府県ページに出す開催中スタンプラリー等のリンク。end_date 過ぎは日次再生成で自動非表示）
dataset/features/<slug>.json は手動更新（特集。1本1ファイルで /features/<slug>/ ができる。highlight_until までは /summary/ にも出る。書式は apps/scraper/features.py）
dataset/pokemon_representatives.json は手動更新（ポケモンごとの代表のマンホール。manhole-ai の Tools/pokemon-rep で選び、export_reps.py の出力を入れる。トップの「設置の多いポケモンから探す」、/pokemon/ のカード、ポケモンのページの上の1枚と og:image のように1枚だけ出す所で使い、ポケモンのページの一覧は全部出す）
dataset/trip_areas.json は手動更新（/trip/ のエリア。マンホールIDの組を登録すると、日次の Pages デプロイでページができる。地点が欠けた・設置予定のエリアは出ない）
dataset/visit_durations.json は手動更新（k11 の DB バックアップで `apps/tools/build_visit_durations.py` を実行して PR。集計値だけで人数は載せない。公開の記録で1日で全部回った人が3人以上の組だけ（時間の幅は非公開も含める。`MIN_PUBLIC_PEOPLE`）。県・市・trip のページの所要時間はこれを読む）
pokefuta.ndjsonはapps/scraperで更新している
latest-manhole-photos.json と docs/api/*.json は import-manhole-photos.yml が Supabase から日次一括生成（画像DL込み。pokefuta.com アプリの /api/manholes・/api/site-stats は docs/api を読む。手動で回すときだけ `/import-photos` スキル）

## 公開リポジトリとして守ること

このリポジトリと data.pokefuta.com は公開。2026-10-11 の点検では、全履歴・PR・Issue に秘密は出ていなかった。この状態を保つ。

- **資格情報は GitHub Actions の secrets にだけ置く**（`SUPABASE_SERVICE_ROLE_KEY`・`R2_*`・`REGULAR_BADGE_RULE` など）。ワークフローでは `env:` で渡し、`echo`・`set -x`・`curl -v` でログに出さない。`pull_request_target` は使わない
- **常連バッジの線（`REGULAR_BADGE_RULE`）の数字は、コード・PR・画面に書かない**
- **PR・コミット・データに他ユーザーの名前・行動・auth UID を書かない。** 指すときは公開ID（`photo_id`・`public_user_id`・マンホールID）
- **公開する JSON（`docs/api/*.json`・`docs/latest-manhole-photos.json`）に出してよい利用者の情報は `public_user_id` と表示名まで。** auth の user_id・メール・署名付きURL・写真の位置情報（EXIF）は出さない
- Supabase の anon キー（`apps/web/assets/pokefuta-auth.js`）は公開前提の値。守りは写真館側の RLS とテーブル権限で効かせる

## ディレクトリ構成

- `apps/scraper/` — GitHub Actions から自動実行されるスクリプト群（update-pokefuta.yml / pages-deploy.yml / import-manhole-photos.yml）
  - `address_parser.py` / `manhole_titles.py` は上記スクリプトの内部ライブラリ
- `apps/tools/` — 手動実行ツール・初期化アーカイブ（例外: import_latest_manhole_photos.py は import-manhole-photos.yml から、check_mobile_viewport.py は mobile-viewport-check.yml からも呼ばれる）
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

家系AとBの PR は `github-actions[bot]` が作るので、`pull_request` で起動する検証（`production-url-check.yml` など）は承認待ちのまま走らない（家系Aは即マージされ、ジョブ0個の failure として残る）。**PR に入れる前に必要な検査は、そのワークフローの中で PR 作成より前に実行する。**

### 必ず守ること

- **`timeout-minutes` を必ず書く。** 既定値は6時間で、ハングすると runner をその間占有する
- **Python は `actions/setup-python@v6` + `python-version: '3.11'` で固定する。** ランナー既定の python に依存しない
- **依存は `requirements.txt` に集約する。** ワークフロー内で `pip install <パッケージ名>` を直接書かない（バージョン非固定で上流の破壊的変更をそのまま踏むため）。例外は家系Cの検証専用依存で、`requirements-check.txt` に分けている（playwright を本体に入れると、ブラウザ検査と無関係な日次ジョブ3本が毎回落とすことになる。**バージョンを固定するという規約の意図は分けたファイル側でも守る**）
- **定期実行するワークフローには `concurrency` を付ける。** 手動実行と定時実行の衝突を防ぐ
- **外部リポジトリを `actions/checkout` するときは `ref:` をタグかコミットSHAに固定する。** 以前 `nishiokya/pokefuta` を HEAD で引いてスクリプトを実行しており、相手側の変更で日次ジョブが黙って壊れる状態だった（現在は tracker 側へ移管して解消済み）
- **同じ Supabase テーブルを複数のワークフローから引かない。** 取得は1ジョブに集約する。かつては写真取込とスナップショット生成が同じ `photo` / `visit` を別々に引いていた
- **cron を変更するときは前後のワークフローとの順序を確認する。** `import-manhole-photos.yml`（05:30 JST）→ Pages デプロイ → `check-site-stats.yml`（08:00 JST）→ `mobile-viewport-check.yml`（08:30 JST）は**この順序に依存**しており、崩すと検証が生成を追い越して毎日誤検知する

### テストについて

テストファイルは20個以上あるが **CI で走っているのはごく一部**。ワークフローからスクリプトを呼ぶなら、対応するテストを実行するステップも同じワークフローに入れること。
