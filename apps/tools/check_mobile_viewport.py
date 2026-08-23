#!/usr/bin/env python3
"""スマホ幅で横にはみ出していないかを本番（または任意のベースURL）で検証する。

なぜ「横はみ出し」だけを見るのか:

図鑑のスマホ表示崩れは、ほぼ必ずこの連鎖で起きる。

  1. ヘッダーやグリッドが数px 横にはみ出す
  2. `width=device-width` なのでブラウザはレイアウトビューポートを実測幅まで広げ、
     ページ全体を縮小表示（shrink-to-fit）する
  3. sticky なヘッダーと fixed な下タブは「レイアウトビューポート」基準で置かれるため、
     縮小された「視覚ビューポート」とズレる
  4. 結果、下タブが画面下端に貼り付かず本文に重なり、ヘッダーの右端が画面外へ切れる

つまり「パンくずがヘッダーとフッターにかぶる」の根っこは横はみ出しであり、
`scrollWidth == clientWidth` の1本で回帰を捕まえられる。

`innerWidth` まで突き合わせるのが要点。`overflow-x: clip` は scrollWidth を
隠せてしまうが、縮小表示そのものは止まらない。

使い方:
    python3 tools/check_mobile_viewport.py
    python3 tools/check_mobile_viewport.py --base-url http://localhost:8899
    python3 tools/check_mobile_viewport.py --path / --path /summary/ --width 390
"""

from __future__ import annotations

import argparse
import sys

# 実機で多い幅。360 は Android の最頻値、375/390/393 は iPhone、430 は Pro Max。
# 320 は iPhone SE(第1世代)級で、ここだけはブランド名の省略を許容する。
DEFAULT_WIDTHS = (320, 360, 375, 390, 393, 412, 430)

# ページ種別 × ロケールを1本ずつ。英語は認証ラベルが最長で最初に破綻するので必ず含める。
DEFAULT_PATHS = (
    "/",
    "/map.html",
    "/summary/",
    "/prefectures/aichi/",
    "/prefectures/hokkaido/",
    "/manholes/290/",
    "/pokemon/",
    "/pokemon/pikachu/",
    "/character_manholes.html",
    "/design_manhole.html",
    "/nearby.html",
    "/login.html",
    "/en/",
    "/en/summary/",
    "/en/pokemon/",
    "/ko/summary/",
    "/zh-TW/summary/",
    "/zh-CN/summary/",
)

IPHONE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

# はみ出しの発生源を絞り込むスクリプト。親がはみ出していない要素だけを挙げる。
PROBE = """() => {
  const de = document.documentElement;
  const vw = de.clientWidth;
  const culprits = [];
  document.querySelectorAll('body *').forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0 || r.right <= vw + 1) return;
    const p = el.parentElement;
    if (p && p.getBoundingClientRect().right > vw + 1) return;
    const cls = typeof el.className === 'string' && el.className
      ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.')
      : '';
    culprits.push({
      sel: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + cls,
      right: Math.round(r.right),
      text: (el.textContent || '').trim().slice(0, 24),
    });
  });
  const tabs = document.querySelector('.site-tabs');
  return {
    scrollWidth: de.scrollWidth,
    clientWidth: vw,
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    tabsBottom: tabs ? Math.round(tabs.getBoundingClientRect().bottom) : null,
    culprits: culprits.slice(0, 6),
  };
}"""


def check(base_url: str, paths, widths, timeout_ms: int = 45000) -> list[str]:
    from playwright.sync_api import sync_playwright

    failures: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for width in widths:
                context = browser.new_context(
                    viewport={"width": width, "height": 780},
                    device_scale_factor=2,
                    is_mobile=True,
                    has_touch=True,
                    user_agent=IPHONE_UA,
                )
                for path in paths:
                    url = base_url.rstrip("/") + path
                    page = context.new_page()
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                        page.wait_for_timeout(2500)
                        result = page.evaluate(PROBE)
                    finally:
                        page.close()

                    problems = []
                    if result["scrollWidth"] > result["clientWidth"] + 1:
                        problems.append(
                            f"横スクロールが出ている（scrollWidth={result['scrollWidth']} > "
                            f"clientWidth={result['clientWidth']}）"
                        )
                    if result["innerWidth"] != width:
                        problems.append(
                            f"ページが縮小表示されている（innerWidth={result['innerWidth']} != {width}）"
                        )
                    if result["tabsBottom"] is not None and abs(result["tabsBottom"] - result["innerHeight"]) > 2:
                        problems.append(
                            f"下タブが画面下端にいない（bottom={result['tabsBottom']} != "
                            f"innerHeight={result['innerHeight']}）"
                        )
                    if problems:
                        detail = "; ".join(problems)
                        origins = ", ".join(
                            f"{c['sel']}(right={c['right']})" for c in result["culprits"]
                        ) or "（発生源を特定できず）"
                        failures.append(f"[{width}px] {path}: {detail} / はみ出し元: {origins}")
                    else:
                        print(f"[OK] {width}px {path}")
                context.close()
        finally:
            browser.close()
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="https://data.pokefuta.com")
    parser.add_argument("--path", action="append", dest="paths")
    parser.add_argument("--width", action="append", type=int, dest="widths")
    args = parser.parse_args()

    paths = tuple(args.paths) if args.paths else DEFAULT_PATHS
    widths = tuple(args.widths) if args.widths else DEFAULT_WIDTHS

    failures = check(args.base_url, paths, widths)
    if failures:
        print("\n=== スマホ幅ではみ出しがある ===", file=sys.stderr)
        for line in failures:
            print("  " + line, file=sys.stderr)
        print(
            "\nはみ出すとページ全体が縮小表示され、ヘッダーと下タブが本文に重なる。"
            "\nグリッドは repeat(N, minmax(0, 1fr))、ヘッダーの要素は縮められるように直すこと。",
            file=sys.stderr,
        )
        return 1
    print(f"\nすべて通過（{len(widths)} 幅 × {len(paths)} ページ）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
