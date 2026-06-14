# Semantic Manhole Metadata Editor

ポケふたの semantic metadata を安全に編集するための内部ツールです。
JSON を直接編集するのではなく、タスク単位の UI を通じて操作します。

## 起動

```bash
cd tools/manhole-semantic-editor
npm install
npm run dev
```

固定URL: **http://localhost:5177**

ポートが使用中の場合はエラーで終了します（他のポートへのフォールバックはありません）。

## 編集可能ファイル

```
dataset/manhole_titles.json
```

## 編集禁止ファイル

```
docs/pokefuta.ndjson
docs/*.ndjson
```

クローラーが管轄する source of truth のため、このツールは読み取りのみ行います。

## タスク一覧

| # | タスク | 説明 |
|---|--------|------|
| 1 | 自治体URLを追加する | `city_links` に自治体公式案内ページを登録 |
| 2 | 公式URLを確認する | `manholes.<id>.official_url` を設定 |
| 3 | 海・湖・離島タグを付ける | `seaside` / `lakeside` / `remote_island` タグ |
| 4 | 駅近・駅構内タグを付ける | `in_station` / `near_station` など（実装予定） |
| 5 | 観光地タグを付ける | `tourism` / `park` / `museum` など |
| 6 | titleを確認する | `confidence` / `verified_at` を更新 |
| 7 | Admin: 特定マンホール編集 | ID指定で直接編集 |
| 8 | Admin: 一括編集 | 条件フィルタで複数件を一括変更（要確認テキスト入力） |
| 9 | 近くのマンホールを探す | Manhole Map投稿をポケふたからの距離順に閲覧 |

## Manhole Map データ

「近くのマンホールを探す」は、事前に生成した読み取り専用JSON-LDを使います。

```bash
python3 apps/tools/import_manholemap.py
```

生成先の `dataset/manholemap.json` と都道府県別キャッシュはgitignore対象です。

## PR を作成する

セッション中の変更は `workspace/changes.ndjson` に記録されます。

サイドバーの「PR を作成する」ボタンを押すか：

```bash
npm run create-pr
```

PR作成前に以下を自動検証します：

- `docs/*.ndjson` が変更されていないこと
- `dataset/manhole_titles.json` が変更されていること
- `workspace/changes.ndjson` にパッチが記録されていること

## Semantic Patch

操作は JSON 差分ではなく semantic operation として記録されます：

```json
{
  "id": "1716345678901-1",
  "createdAt": "2026-05-20T12:00:00.000Z",
  "taskType": "assign_location_tags",
  "operation": "add_tags",
  "target": "manholes",
  "manholeIds": [101, 102, 103],
  "payload": { "tags": ["seaside"] }
}
```

## JSON 出力の安定性

`dataset/manhole_titles.json` への書き込み時：

- `manholes` キーを数値ID昇順でソート
- 各エントリのフィールド順を固定（`building → address_raw → ... → official_url`）
- 2スペースインデント、末尾改行

## アーキテクチャ

```
docs/pokefuta.ndjson  ←── read-only (Vite plugin で提供)
          ↓
    React UI (localhost:5177)
          ↓ semantic patch
dataset/manhole_titles.json  ←── 書き込み対象
```

ファイルI/Oは Vite カスタムプラグイン (`vite.config.ts`) が `/__editor/` エンドポイントとして提供します。
外部バックエンドサーバーは不要です。
