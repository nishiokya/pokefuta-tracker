Sync the latest manhole photos. Run these two steps in order:

1. Copy `apps/web/latest-manhole-photos.json` to `docs/latest-manhole-photos.json`
2. Run `python3 apps/tools/import_latest_manhole_photos.py --presign-r2` from the project root

Then report the summary line (imported / skipped / failed counts) and confirm the file count in `dataset/manhole/image/`.
