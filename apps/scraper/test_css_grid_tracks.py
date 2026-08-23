"""グリッドのトラックが min-content で突っ張らないことを検査する。

`repeat(N, 1fr)` は `repeat(N, minmax(auto, 1fr))` と同義で、トラックが
min-content 未満に縮まない。子に `white-space: nowrap` があると（投稿者名・
地名・日付など）min-content ＝ その1行の実幅になり、グリッドがビューポートを
突き破る。

横にはみ出すとモバイルブラウザはページ全体を縮小表示し、sticky ヘッダーと
fixed 下タブが視覚ビューポートからズレて本文に重なる。実際 `/summary/` の
最新追加写真グリッドが `repeat(2, 1fr)` だったせいで、文書幅が 433px に固定され、
どのスマホでも下タブが画面下端から外れていた。

実測での回帰検知は tools/check_mobile_viewport.py（ヘッドレス）が担当する。
ここは書き戻しを止めるための、依存なしの静的な歯止め。

同じ罠は `grid-template-columns: 1fr 1fr` のような直書きにもある。新しく
グリッドを足すときは常に `minmax(0, 1fr)` を使うこと。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 生成物にそのまま焼き込まれる CSS を持つファイル
SCANNED = (
    "apps/scraper/generate_summary_pages.py",
    "apps/scraper/generate_prefecture_pages.py",
    "apps/scraper/generate_manhole_pages.py",
    "apps/scraper/generate_pokemon_pages.py",
    "apps/scraper/generate_pokemon_index_page.py",
    "apps/scraper/generate_character_manhole_page.py",
    "apps/web/assets/top-page.css",
    "apps/web/assets/site-header.css",
    "apps/web/assets/pokefuta-map.css",
    "apps/web/index.html",
    "apps/web/index.template.html",
    "apps/web/map.html",
    "apps/web/map.template.html",
    "apps/web/design_manhole.html",
    "apps/web/nearby_manholes.html",
)

BARE_FR_TRACK_RE = re.compile(r"repeat\(\s*\d+\s*,\s*1fr\s*\)")


class GridTrackTest(unittest.TestCase):
    def test_no_bare_fr_repeat_tracks(self):
        offenders = []
        for rel in SCANNED:
            path = ROOT / rel
            if not path.exists():
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if BARE_FR_TRACK_RE.search(line):
                    offenders.append(f"{rel}:{lineno} {line.strip()[:90]}")
        self.assertEqual(
            offenders,
            [],
            "repeat(N, 1fr) は minmax(0, 1fr) にすること（min-content で突っ張って横にはみ出す）:\n  "
            + "\n  ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
