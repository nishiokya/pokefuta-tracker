Sync the latest manhole photos manually.

NOTE: 通常は `.github/workflows/import-manhole-photos.yml` が日次（JST 07:00）で export〜画像DL〜commit まで自動実行する。このスキルは即時反映したいときや Action が失敗したときの手動フォールバック。

Run these two steps in order:

1. Copy `../pokefuta/public/data/latest-manhole-photos.json` to both `apps/web/latest-manhole-photos.json` and `docs/latest-manhole-photos.json`
2. Run `python3 apps/tools/import_latest_manhole_photos.py --presign-r2` from the project root

Prerequisite: `pokefuta` リポジトリが `../pokefuta/` に存在すること（`latest-manhole-photos.json` のコピー元）。

Prerequisite: `.env.local` must contain the following variables:
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_ENDPOINT` (or `R2_PUBLIC_URL`)
- `R2_BUCKET` (optional)

Then report the summary line (imported / skipped / failed / gallery_imported / gallery_kept / gallery_removed counts) and confirm the file count in `dataset/manhole/image/`.

Notes:
- 代表写真は `{id}_latest.jpeg`、ギャラリー写真（photos JSON の `gallery` 配列、代表を除く）は `{id}_{photo_id先頭8桁}.jpeg` に保存される
- 既存のギャラリーファイルは再ダウンロードされない（冪等）。エクスポートから外れた photo_id のファイルは自動削除される
- 詳細仕様: `docs/MANHOLE_DETAIL_SPEC.md`
