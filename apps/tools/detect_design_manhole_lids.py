#!/usr/bin/env python3
"""Detect lid bounds in public design photos using the existing manhole-score model.

Run on K11 with manhole-score's venv; no database credentials or image copies in Git.
Review the resulting crops visually before committing the metadata.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--submissions', type=Path, required=True)
    parser.add_argument('--detector-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.detector_root / 'scripts'))
    from lid_detector import LidDetector, load_image
    detector = LidDetector()
    output = json.loads(args.output.read_text()) if args.output.exists() else {}
    rows = [json.loads(line) for line in args.submissions.read_text().splitlines() if line.strip()]
    with tempfile.TemporaryDirectory() as tmp:
        for row in rows:
            sid = row.get('source_id')
            if row.get('status') != 'active' or not str(row.get('canonical_ref', '')).startswith('gundam:') or not sid or sid in output:
                continue
            # Fetch only the public endpoint; hidden/deleted photos return 404.
            url = f'https://pokefuta.com/api/design-manholes/{sid}/photo?size=small'
            path = Path(tmp) / 'photo'
            with urlopen(url, timeout=30) as response:
                path.write_bytes(response.read())
            box, score = detector.predict(path)
            if box and score >= .8:
                width, height = load_image(path).size
                output[sid] = {'box': box, 'width': width, 'height': height}
            print(f'{sid}: {"detected" if sid in output else "needs review"}', flush=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
