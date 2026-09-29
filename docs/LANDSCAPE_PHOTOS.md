# 周辺風景と蓋の写真充足率

写真館に投稿時の「周辺の風景」チェックを追加する対応。保存先は `public.photo.is_landscape`（boolean、既定false）。K11の自動判定や既存写真の再分類は行わない。

## このリポジトリの役割

- `export_latest_manhole_photos.py` は `is_landscape=false` を取得条件に追加する。手動代表指定・最新写真へのフォールバック・ギャラリーでも風景を代表候補に戻さない。
- 風景しかない地点は `latest-manhole-photos.json` の `photos` に含めず、蓋の写真は募集中のままにする。
- `export_app_snapshot.py` の `photo_count` / `with_photos` / `manholes_with_photos` は、公開訪問に属する風景以外の写真で計算する。旧RPCの充足数をそのまま再利用しない。
- 投稿総数は風景も含む。個人の訪問記録・スタンプ判定は写真館側の判断であり、図鑑の写真充足とは別。
- 初期は風景用の図鑑ギャラリーを追加せず、風景の閲覧は写真館の投稿一覧・詳細ページが担当する。

## 反映順序

1. 写真館の `20260929100000_photo_landscape.sql` をDBに適用する。
2. このPRを反映し、日次同期でJSONと掲載写真を生成する。
3. 写真館の投稿UIを公開する。

新列のないDBに対してこのexportを実行すると失敗する。旧スキーマへ黙ってフォールバックすると風景が蓋に混ざるので、DB適用を先に行う。

今回、日次同期の起動・生成済みJSON/画像の書き換え・デプロイは行わない。既存の変更中cloneには触れず、独立したworktreeで実装した。

## テスト

既存の `import-manhole-photos.yml` が実行する以下のテストに、風景だけの地点、風景の手動代表指定、取得時の絞り込み、スナップショットの公開写真充足を追加した。

```sh
python3 -m unittest apps.scraper.test_export_latest_manhole_photos apps.scraper.test_export_app_snapshot apps.scraper.test_display_names
```

82件成功（2026-09-30）。本番データへの接続・生成は未実施。
