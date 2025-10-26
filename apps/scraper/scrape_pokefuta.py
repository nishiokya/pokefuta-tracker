#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pokefuta initial dataset scraper (手動初期化専用).

このスクリプトは「初期データをまとめて生成する」ためだけに使います。
以降の継続的な差分監視・削除/新規検出は `update_pokefuta.py` を使用してください。

主な仕様 (最小実装):
  * ID レンジを 1..N で総当たりし、存在する detail ページを抽出
  * 緯度 / 経度 / タイトル / ポケモン(簡易) を取得
  * 404 はスキップ
  * 日本語ページのみ必須。英語/中国語は任意取得 (失敗しても継続)
  * 出力: NDJSON (デフォルト) または JSON array
  * Ctrl-C (SIGINT) で安全に途中終了 (取得済み分は保存)

使い方例:
  # 1..500 を走査し NDJSON 出力
  python apps/scraper/scrape_pokefuta.py --scan-max 500 --out pokefuta.ndjson

  # JSON 配列で保存
  python apps/scraper/scrape_pokefuta.py --scan-max 800 --write-mode array --out pokefuta.json

注意:
  * 生成後の差分追跡は `update_pokefuta.py` に任せてください。
  * 初期フェーズ終了後、このスクリプトを CI / 定期実行に組み込まないでください。
"""
from __future__ import annotations
import argparse, json, logging, os, re, signal, sys, tempfile, time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

DEFAULT_BASE = "https://local.pokemon.jp/manhole/"
HEADERS = {"User-Agent": "pokefuta-initial-scraper (+https://github.com/nishiokya/pokefuta-tracker)"}
HEADERS_EN = {**HEADERS, "Accept-Language": "en-US,en;q=0.9"}
HEADERS_ZH = {**HEADERS, "Accept-Language": "zh-CN,zh;q=0.9"}

REQ_TIMEOUT = 15
RETRY = 3
DEFAULT_SLEEP = 0.5

@dataclass
class Pokefuta:
    id: str
    title: str
    prefecture: str
    city: str
    address: str
    city_url: str
    lat: float
    lng: float
    pokemons: List[str]
    pokemons_en: List[str]
    pokemons_zh: List[str]
    detail_url: str
    prefecture_site_url: str


def setup_logger(level: str = "INFO") -> logging.Logger:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=lvl, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    return logging.getLogger("pokefuta-init")


def fetch(url: str, logger: logging.Logger, headers: Dict[str, str]) -> Optional[str]:
    last_err = None
    for i in range(RETRY):
        try:
            r = requests.get(url, headers=headers, timeout=REQ_TIMEOUT)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_err = e
            logger.warning("fetch failed (%s) retry=%d err=%s", url, i + 1, e)
            time.sleep(0.8 * (i + 1))
    logger.error("giving up %s: %s", url, last_err)
    return None


def parse_detail(detail_url: str, html: str, logger: logging.Logger) -> Optional[Dict]:
    soup = BeautifulSoup(html, "html.parser")

    # 緯度経度 (Google Maps へのリンクから抽出)
    lat = lng = None
    for a in soup.select('a[href*="maps.google"]'):
        href = a.get("href", "")
        # q=lat,lng を拾う
        m = re.search(r"q=([+-]?\d+(?:\.\d+)?),([+-]?\d+(?:\.\d+)?)", href)
        if m:
            try:
                lat = float(m.group(1)); lng = float(m.group(2))
                break
            except Exception:
                continue
    if lat is None or lng is None:
        return None

    # タイトル (h1/h2 優先)
    title = ""
    h = soup.find(["h1", "h2"])
    if h and h.get_text(strip=True):
        title = h.get_text(strip=True)
    if not title:
        t2 = soup.find(class_=re.compile(r"title|heading", re.I))
        if t2:
            title = t2.get_text(strip=True)

    # ポケモン名 (簡易: アンカーテキストなどに「ポケモン」「図鑑」含むものから抽出)
    pokemons: List[str] = []
    for a in soup.select("a[href]"):
        txt = a.get_text(strip=True)
        if not txt:
            continue
        if any(k in txt for k in ["ポケモン", "図鑑", "Pokédex", "Pokemon", "Pokémon"]):
            cleaned = re.sub(r"(ポケモン|図鑑|Pokédex|Pokémon|Pokemon)", "", txt).strip()
            if cleaned and len(cleaned) <= 20:
                pokemons.append(cleaned)
    # 重複排除
    pokemons = sorted({p for p in pokemons if p})

    # ID
    m = re.search(r"/desc/(\d+)/?", detail_url)
    pid = m.group(1) if m else ""

    # 県/市 (タイトルが「鹿児島県/指宿市 …」形式なら分割)
    prefecture = city = ""
    if "/" in title:
        part = title.split()[0]  # 最初の語群
        if "/" in part:
            pf, ct = part.split("/", 1)
            if pf.endswith("県") or pf.endswith("府") or pf.endswith("道") or pf.endswith("都"):
                prefecture = pf
                city = ct.rstrip("市町村区") if ct else ""

    # 住所の取得 (テキストから住所らしき文字列を抽出)
    address = ""
    # 住所パターンを探す（都道府県名 + 市区町村 + 丁目・番地など）
    text_content = soup.get_text()
    address_patterns = [
        r'([^。\n]*(?:県|府|道|都)[^。\n]*(?:市|区|町|村)[^。\n]*(?:\d+[-−‐]\d+[-−‐]\d+|\d+丁目|\d+番地)[^。\n]*)',
        r'([^。\n]*(?:市|区|町|村)[^。\n]*(?:\d+[-−‐]\d+[-−‐]\d+|\d+丁目|\d+番地)[^。\n]*)',
    ]
    for pattern in address_patterns:
        matches = re.findall(pattern, text_content)
        if matches:
            # 最も長い住所らしきものを選択
            address = max(matches, key=len).strip()
            break

    # Use second precision UTC format compatible with JS Date parsing
    now_iso = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    return {
        "id": pid,
        "title": title,
        "prefecture": prefecture,
        "city": city,
        "address": address,
        "city_url": "",
        "lat": lat,
        "lng": lng,
        "pokemons": pokemons,
        "pokemons_en": [],
        "pokemons_zh": [],
        "detail_url": detail_url,
        "prefecture_site_url": "",
        # extended schema (for consistency with incremental updater)
    "first_seen": now_iso,
    "added_at": now_iso,  # alias for first_seen used by web UI
    "last_updated": now_iso,  # unified update timestamp
    "status": "active"
    }


def enrich_multilingual(detail_url: str, rec: Dict, logger: logging.Logger):
    # English
    html_en = fetch(detail_url, logger, HEADERS_EN)
    if html_en:
        soup_en = BeautifulSoup(html_en, "html.parser")
        # simple pokemon extraction
        p_en = []
        for a in soup_en.select("a[href]"):
            t = a.get_text(strip=True)
            if not t:
                continue
            if any(k in t for k in ["Pokémon", "Pokemon", "Pokédex"]):
                nm = re.sub(r"(Pokémon|Pokemon|Pokédex)", "", t).strip()
                if nm:
                    p_en.append(nm)
        rec["pokemons_en"] = sorted({x for x in p_en if x})
    # Chinese
    html_zh = fetch(detail_url, logger, HEADERS_ZH)
    if html_zh:
        soup_zh = BeautifulSoup(html_zh, "html.parser")
        p_zh = []
        for a in soup_zh.select("a[href]"):
            t = a.get_text(strip=True)
            if not t:
                continue
            if any(k in t for k in ["宝可梦", "圖鑑", "图鉴"]):
                nm = re.sub(r"(宝可梦|圖鑑|图鉴)", "", t).strip()
                if nm:
                    p_zh.append(nm)
        rec["pokemons_zh"] = sorted({x for x in p_zh if x})


def atomic_write_array(path: str, rows: List[Dict]):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=d, encoding="utf-8") as tmp:
        json.dump(rows, tmp, ensure_ascii=False, indent=2)
        tmp.flush(); os.fsync(tmp.fileno())
        p = tmp.name
    os.replace(p, path)


def atomic_write_ndjson(path: str, rows: List[Dict]):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=d, encoding="utf-8") as tmp:
        for r in rows:
            tmp.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.flush(); os.fsync(tmp.fileno())
        p = tmp.name
    os.replace(p, path)


def load_existing(path: str, mode: str) -> List[Dict]:
    """Load existing output file (ndjson or array). Return list of dicts or [].

    Any malformed lines are skipped to be resilient against manual edits.
    """
    if not os.path.exists(path):
        return []
    records: List[Dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            if mode == "array":
                try:
                    arr = json.load(f)
                    if isinstance(arr, list):
                        for x in arr:
                            if isinstance(x, dict):
                                records.append(x)
                except Exception:
                    return []
            else:  # ndjson
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict):
                            records.append(obj)
                    except Exception:
                        continue
    except Exception:
        return []
    return records


CORE_COMPARE_FIELDS = [
    "title", "prefecture", "city", "address", "city_url",
    "lat", "lng", "pokemons", "pokemons_en", "pokemons_zh", "detail_url", "prefecture_site_url", "status"
]


def _record_changed(new: Dict, old: Dict) -> bool:
    for k in CORE_COMPARE_FIELDS:
        if new.get(k) != old.get(k):
            return True
    return False


def merge_with_existing(existing: List[Dict], freshly_scraped: List[Dict], now_iso: str) -> Tuple[List[Dict], bool]:
    """Merge new scrape results with existing records preserving timestamps.

    Rules:
      * If id exists and core fields unchanged -> keep entire old record (no diff)
      * If id exists and changed -> keep old first_seen/added_at, update last_updated=now_iso
      * New id -> insert with its timestamps (first_seen/added_at/last_updated already set) -> diff
      * Removed ids (present before, missing now) are retained unchanged (initial scraper doesn't handle deletions)
    Returns (merged_records, changed_flag).
    """
    old_by_id = {r.get("id"): r for r in existing if r.get("id")}
    new_by_id = {r.get("id"): r for r in freshly_scraped if r.get("id")}

    changed = False
    merged: List[Dict] = []

    # Preserve existing ordering primarily
    for old in existing:
        oid = old.get("id")
        if not oid:
            continue
        if oid in new_by_id:
            new_rec = new_by_id[oid]
            if _record_changed(new_rec, old):
                # update timestamps but keep original first_seen/added_at
                new_rec["first_seen"] = old.get("first_seen", new_rec.get("first_seen"))
                new_rec["added_at"] = old.get("added_at", new_rec.get("added_at"))
                new_rec["last_updated"] = now_iso
                merged.append(new_rec)
                changed = True
            else:
                merged.append(old)  # identical -> keep as-is
            del new_by_id[oid]
        else:
            # Old record not re-scraped (outside scan range or deleted) -> keep
            merged.append(old)

    # Append truly new records (remaining in new_by_id)
    for rec in freshly_scraped:
        rid = rec.get("id")
        if rid in new_by_id:  # still not merged
            merged.append(rec)
            changed = True
    return merged, changed


_running = True
def _sigint_handler(signum, frame):  # noqa: D401
    global _running
    _running = False
    signal.signal(signal.SIGINT, signal.SIG_DFL)


def scan_range(base: str, start: int, end: int) -> List[str]:
    base_root = base.rstrip('/')
    if not base_root.endswith('/manhole'):
        base_root = re.sub(r'/manhole/.*$', '/manhole', base_root)
        if not base_root.endswith('/manhole'):
            base_root += '/manhole'
    return [f"{base_root}/desc/{i}/?is_modal=1" for i in range(start, end + 1)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default=DEFAULT_BASE, help='Base manhole top URL')
    parser.add_argument('--scan-min', type=int, default=1, help='Start ID (inclusive)')
    parser.add_argument('--scan-max', type=int, default=500, help='End ID (inclusive)')
    parser.add_argument('--out', default='pokefuta.ndjson', help='Output file path')
    parser.add_argument('--write-mode', choices=['ndjson', 'array'], default='ndjson', help='Output format')
    parser.add_argument('--sleep', type=float, default=DEFAULT_SLEEP, help='Sleep seconds between requests')
    parser.add_argument('--log-level', default='INFO', help='Log level')
    parser.add_argument('--no-ml', dest='no_ml', action='store_true', help='Skip English/Chinese enrichment for speed')
    parser.add_argument('--limit', type=int, default=0, help='Stop after N successful records (testing)')
    args = parser.parse_args()

    logger = setup_logger(args.log_level)
    signal.signal(signal.SIGINT, _sigint_handler)
    sleep_sec = max(0.1, args.sleep)

    if args.scan_min < 1 or args.scan_max < args.scan_min:
        logger.error('Invalid scan range: %d..%d', args.scan_min, args.scan_max)
        sys.exit(1)

    detail_urls = scan_range(args.base, args.scan_min, args.scan_max)
    logger.info('Scanning IDs %d..%d total=%d', args.scan_min, args.scan_max, len(detail_urls))

    results: List[Dict] = []
    processed = 0
    successes = 0
    start_ts = time.time()

    for url in detail_urls:
        if not _running:
            logger.warning('Interrupted by user, stopping early...')
            break
        processed += 1
        html = fetch(url, logger, HEADERS)
        if html is None:  # 404 or failure
            time.sleep(sleep_sec)
            continue
        rec = parse_detail(url, html, logger)
        if not rec:  # parse failure
            time.sleep(sleep_sec)
            continue
        if not args.no_ml:
            try:
                enrich_multilingual(url, rec, logger)
            except Exception as e:  # noqa: BLE001
                logger.debug('multilingual enrich failed id=%s err=%s', rec.get('id'), e)
        results.append(rec)
        successes += 1
        if args.limit and successes >= args.limit:
            logger.info('Limit %d reached, stopping early', args.limit)
            break
        time.sleep(sleep_sec)

    # 保存
    existing = load_existing(args.out, args.write_mode)
    merged, changed_flag = merge_with_existing(existing, results, datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'))

    if not changed_flag:
        logger.info('No changes detected; skip writing (out=%s)', args.out)
    else:
        if args.write_mode == 'array':
            atomic_write_array(args.out, merged)
        else:
            atomic_write_ndjson(args.out, merged)
        logger.info('Wrote updated dataset records=%d new_or_changed=%d out=%s', len(merged), len(merged) - len(existing), args.out)

    dur = time.time() - start_ts
    logger.info('DONE processed=%d success=%d current_records=%d mode=%s out=%s elapsed=%.1fs changed=%s', processed, successes, len(merged if changed_flag else existing), args.write_mode, args.out, dur, changed_flag)

    # ヘルプ: 次のステップ
    logger.info('次回以降の定期更新は update_pokefuta.py を使用してください。')


if __name__ == '__main__':  # pragma: no cover
    main()
