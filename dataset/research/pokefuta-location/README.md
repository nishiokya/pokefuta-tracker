# ポケふた設置場所調査データ

## 役割

`building`、`place_detail`、`landmark`、`tags`の採用前調査と監査証跡を保存する。
採用済みメタデータの正本は`dataset/manhole_titles.json`であり、このディレクトリの
データを公開NDJSONへ直接反映しない。

## ディレクトリ

```text
queues/   調査対象、割当、選定理由
results/  調査結果。pokefuta-location-research.schema.json準拠
```

## 命名規則

- キュー: `YYYY-MM-DD-<batch>.ndjson`
- 結果: `YYYY-MM-DD-<batch>-<assignment>.ndjson`
- `<batch>`と`<assignment>`は小文字英数字とハイフンのみ
- 同じ名前のファイルを別目的に再利用しない

例:

```text
queues/2026-07-25-pilot-01.ndjson
results/2026-07-25-pilot-01-pilot-a.ndjson
results/2026-07-25-pilot-01-pilot-b.ndjson
```

## キュー形式

キューは1行1地点とし、次のフィールドを持つ。

| フィールド | 説明 |
|---|---|
| `schema_version` | キュー形式のバージョン。初版は`1` |
| `id` | ポケふたID |
| `prefecture`, `city`, `address` | 調査開始時点の所在地 |
| `lat`, `lng` | 調査開始時点の公式座標 |
| `tags` | 調査開始時点の既存タグ |
| `detail_url`, `prefecture_site_url` | 公式サイトの調査入口 |
| `stratum` | 選定層 |
| `assignment` | 担当名 |
| `selection_reason` | パイロットへ含めた理由 |

キューは調査開始時点のスナップショットとし、調査で誤りが判明しても書き換えない。
修正候補は結果NDJSONの`candidate`と`issues`へ記録する。

## 結果形式

結果は`schemas/pokefuta-location-research.schema.json`に従い、次のコマンドで検証する。

```bash
python3 apps/tools/validate_location_research.py \
  dataset/research/pokefuta-location/results/<file>.ndjson
```

1担当につき1ファイルとする。調査中は追記できるが、レビュー開始後は既存行を
書き換えず、修正コミットで履歴を残す。同じ結果ファイル内でIDを重複させない。

## 保持方針

- キューと結果は、採用・保留・未解決を問わずGitで保持する。
- 外部ページの本文や地図画像は保存せず、URL、短い根拠要約、確認日を保存する。
- 個人情報、APIキー、有料地図サービスからの転載データを保存しない。
- 再調査は新しいbatchとして作成し、過去結果を上書きしない。
