Sync the latest manhole photos. Run these two steps in order:

1. Copy `../pokefuta/public/data/latest-manhole-photos.json` to both `apps/web/latest-manhole-photos.json` and `docs/latest-manhole-photos.json`
2. Run `python3 apps/tools/import_latest_manhole_photos.py --presign-r2` from the project root

Prerequisite: `.env.local` must contain the following variables:
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_ENDPOINT` (or `R2_PUBLIC_URL`)
- `R2_BUCKET` (optional)

Then report the summary line (imported / skipped / failed counts) and confirm the file count in `dataset/manhole/image/`.
