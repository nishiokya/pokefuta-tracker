#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scrape Poké Lids (pokefuta) into JSON with verbose logging and incremental writes.

Usage examples:
  # 巡回モード（英語トップ）
  python scrape_pokefuta.py --out pokefuta.v1.json

  # 巡回モード（日本語トップ）
  python scrape_pokefuta.py --base https://local.pokemon.jp/manhole/ --out pokefuta.ja.v1.json

  # IDスキャン（1..1200）
  python scrape_pokefuta.py --scan-min 1 --scan-max 1200 --out pokefuta.scan.v1.json

  # 自動スキャン（連続ミス100で停止）
  python scrape_pokefuta.py --auto-scan --start-id 1 --miss-threshold 100 --out pokefuta.auto.v1.json
"""

import argparse
import json
import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

DEFAULT_BASE = "https://local.pokemon.jp/en/manhole/"
HEADERS = {"User-Agent": "pokefuta-tracker-scraper (+https://github.com/yourname/pokefuta-tracker)"}
REQ_TIMEOUT = 20
SLEEP_SEC = 0.6
RETRY = 3

DETAIL_HREF_PATTERNS = ("/manhole/desc/",)
PREF_PAGE_PAT = re.compile(r"/manhole/([a-z0-9_-]+)\.html$")


@dataclass
class Pokefuta:
    id: str
    title: str
    prefecture: str
    lat: float
    lng: float
    pokemons: List[str]
    detail_url: str
    source_last_checked: str


def setup_logger(level: str = "INFO") -> logging.Logger:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("pokefuta-scraper")


def atomic_write_json(path: str, payload: List[Dict]):
    """Write JSON atomically (avoid partial file)."""
    dirname = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(dirname, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=dirname, encoding="utf-8") as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = tmp.name
    os.replace(tmp_path, path)


def fetch(url: str, logger: logging.Logger) -> requests.Response:
    last = None
    for i in range(RETRY):
        try:
            r = requests.get(url, headers=HEADERS, timeout=REQ_TIMEOUT)
            if r.status_code == 404:
                logger.debug("GET %s -> 404", url)
                return r
            r.raise_for_status()
            logger.debug("GET %s -> %d", url, r.status_code)
            return r
        except Exception as e:
            last = e
            logger.warning("GET failed (%s) retry=%d err=%s", url, i + 1, e)
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last}")


def parse_detail_html(detail_url: str, html: str, now_iso: str, logger: logging.Logger) -> Optional[Pokefuta]:
    soup = BeautifulSoup(html, "html.parser")

    # Google Map (?q=lat,lng)
    lat = lng = None
    for a in soup.select('a[href*="maps.google"]'):
        q = parse_qs(urlparse(a["href"]).query).get("q", [])
        if not q:
            continue
        m = re.match(r"\s*([+-]?\d+(\.\d+)?),\s*([+-]?\d+(\.\d+)?)", q[0])
        if m:
            lat, lng = float(m.group(1)), float(m.group(3))
            break
    if lat is None or lng is None:
        logger.debug("No coords in %s", detail_url)
        return None

    # title
    title = ""
    h = soup.find(["h1", "h2"])
    if h and h.get_text(strip=True):
        title = h.get_text(strip=True)

    # pokemons
    pokemons: List[str] = []
    for a in soup.select("a[href]"):
        txt = a.get_text(strip=True)
        if not txt:
            continue
        if "Pokédex" in txt or "図鑑" in txt:
            name = txt.replace("Pokédex", "").strip()
            if name:
                pokemons.append(name)

    # prefecture (heuristic)
    prefecture = ""
    for a in reversed(soup.select("a[href]")):
        href = a.get("href", "")
        txt = a.get_text(strip=True)
        if PREF_PAGE_PAT.search(href) and txt:
            prefecture = txt
            break

    m = re.search(r"/desc/(\d+)/?", detail_url)
    pid = m.group(1) if m else ""
    return Pokefuta(
        id=pid,
        title=title,
        prefecture=prefecture or "",
        lat=lat,
        lng=lng,
        pokemons=pokemons,
        detail_url=detail_url,
        source_last_checked=now_iso,
    )


def extract_from_detail(detail_url: str, now_iso: str, logger: logging.Logger) -> Optional[Pokefuta]:
    r = fetch(detail_url, logger)
    if r.status_code == 404:
        return None
    return parse_detail_html(detail_url, r.text, now_iso, logger)


def get_prefecture_pages(base_url: str, logger: logging.Logger) -> List[str]:
    seen: Set[str] = set()
    queue: List[str] = [base_url]
    result: List[str] = []
    logger.info("Collecting prefecture pages from %s", base_url)

    while queue:
        url = queue.pop(0)
        r = fetch(url, logger)
        if r.status_code == 404:
            continue
        soup = BeautifulSoup(r.text, "html.parser")

        # collect prefecture pages
        for a in soup.select("a[href]"):
            href = a.get("href")
            if not href:
                continue
            absu = urljoin(url, href)
            if any(p in absu for p in DETAIL_HREF_PATTERNS):
                continue
            if PREF_PAGE_PAT.search(urlparse(absu).path) and absu not in seen:
                seen.add(absu)
                result.append(absu)

        # discover region pages
        for a in soup.select("a[href]"):
            href = a.get("href")
            if not href:
                continue
            absu = urljoin(url, href)
            p = urlparse(absu).path
            if (p.startswith("/en/manhole/") or p.startswith("/manhole/")) and p.endswith(".html"):
                if absu not in seen:
                    seen.add(absu)
                    queue.append(absu)

        time.sleep(SLEEP_SEC)

    # uniq preserve order
    uniq, s = [], set()
    for u in result:
        if u not in s:
            uniq.append(u)
            s.add(u)
    logger.info("Prefecture pages found: %d", len(uniq))
    return uniq


def extract_detail_links(pref_url: str, logger: logging.Logger) -> List[str]:
    r = fetch(pref_url, logger)
    if r.status_code == 404:
        return []
    soup = BeautifulSoup(r.text, "html.parser")

    links: List[str] = []
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if any(p in href for p in DETAIL_HREF_PATTERNS):
            u = urljoin(pref_url, href)
            # normalize to modal for consistent HTML
            if "is_modal=1" not in u:
                u = (u + ("&" if "?" in u else "?") + "is_modal=1")
            links.append(u)

    # uniq
    uniq, s = [], set()
    for u in links:
        if u not in s:
            uniq.append(u)
            s.add(u)

    logger.info("  %s -> %d detail links", pref_url, len(uniq))
    time.sleep(SLEEP_SEC)
    return uniq


def scan_ids(base_top: str, id_min: int, id_max: int, logger: logging.Logger) -> List[str]:
    """Generate /desc/{id}/?is_modal=1 urls that exist (status != 404)."""
    base_root = base_top.rstrip("/")
    if not base_root.endswith("/manhole"):
        base_root = re.sub(r"/manhole/.*$", "/manhole", base_root)
        if not base_root.endswith("/manhole"):
            base_root += "/manhole"

    urls: List[str] = []
    logger.info("Scanning ids from %d to %d", id_min, id_max)
    for i in range(id_min, id_max + 1):
        u = f"{base_root}/desc/{i}/?is_modal=1"
        r = fetch(u, logger)
        if r.status_code != 404 and ("maps.google" in r.text or "/manhole/" in r.text):
            urls.append(u)
            logger.debug("  id=%d exists", i)
        else:
            logger.debug("  id=%d missing", i)
        time.sleep(SLEEP_SEC)

    logger.info("ID scan found %d candidates", len(urls))
    return urls


def auto_scan(base_top: str, start_id: int, miss_threshold: int, logger: logging.Logger) -> List[str]:
    """Expand ids upward until miss_threshold consecutive 404/invalid pages appear."""
    base_root = base_top.rstrip("/")
    if not base_root.endswith("/manhole"):
        base_root = re.sub(r"/manhole/.*$", "/manhole", base_root)
        if not base_root.endswith("/manhole"):
            base_root += "/manhole"

    urls: List[str] = []
    misses = 0
    cur = start_id
    logger.info("Auto scan start at id=%d (stop after %d consecutive misses)", start_id, miss_threshold)

    while True:
        u = f"{base_root}/desc/{cur}/?is_modal=1"
        r = fetch(u, logger)
        if r.status_code != 404 and ("maps.google" in r.text or "/manhole/" in r.text):
            urls.append(u)
            misses = 0
            logger.debug("  id=%d exists", cur)
        else:
            misses += 1
            logger.debug("  id=%d missing (misses=%d)", cur, misses)
            if misses >= miss_threshold:
                break
        cur += 1
        time.sleep(SLEEP_SEC)

    logger.info("Auto scan found %d candidates (last tried id=%d)", len(urls), cur - 1)
    return urls


def main():
    global SLEEP_SEC  # ← 先頭に置く（SyntaxError回避）

    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=DEFAULT_BASE, help="Top page for manhole (EN or JA).")
    parser.add_argument("--out", default="pokefuta.v1.json", help="Output JSON (array).")
    parser.add_argument("--limit", type=int, default=0, help="Limit detail pages (testing).")
    parser.add_argument("--sleep", type=float, default=SLEEP_SEC, help="Sleep seconds between requests.")
    parser.add_argument("--log-level", default="INFO", help="DEBUG/INFO/WARN/ERROR")

    # IDスキャン系
    parser.add_argument("--scan-min", type=int, help="Scan ids from this value (inclusive).")
    parser.add_argument("--scan-max", type=int, help="Scan ids up to this value (inclusive).")
    parser.add_argument("--auto-scan", action="store_true", help="Auto expand ids upward until misses.")
    parser.add_argument("--start-id", type=int, default=1, help="Auto-scan start id.")
    parser.add_argument("--miss-threshold", type=int, default=100, help="Consecutive misses to stop auto-scan.")

    args = parser.parse_args()
    logger = setup_logger(args.log_level)

    # sleep設定
    SLEEP_SEC = max(0.2, args.sleep)

    # 収集対象URLの決定
    t0 = time.perf_counter()
    if args.scan_min and args.scan_max:
        detail_urls = scan_ids(args.base, args.scan_min, args.scan_max, logger)
    elif args.auto_scan:
        detail_urls = auto_scan(args.base, args.start_id, args.miss_threshold, logger)
    else:
        base = args.base if args.base.endswith("/") else args.base + "/"
        pref_pages = get_prefecture_pages(base, logger)
        detail_urls: List[str] = []
        for idx, p in enumerate(pref_pages, 1):
            logger.info("Pref page %d/%d", idx, len(pref_pages))
            detail_urls.extend(extract_detail_links(p, logger))

    # uniq + limit
    uniq, seen = [], set()
    for u in detail_urls:
        if u not in seen:
            uniq.append(u)
            seen.add(u)
    if args.limit > 0:
        uniq = uniq[: args.limit]

    logger.info("Detail pages to parse: %d", len(uniq))

    # 逐次保存：1件処理するたびに --out をアトミック上書き
    out: List[Dict] = []
    processed = 0
    successes = 0
    for i, durl in enumerate(uniq, 1):
        try:
            pf = extract_from_detail(durl, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), logger)
            processed += 1
            if pf:
                rec = asdict(pf)
                out.append(rec)
                successes += 1
                logger.info("Parsed %d/%d OK id=%s title='%s' (%.6f, %.6f)",
                            i, len(uniq), pf.id, (pf.title or "")[:40], pf.lat, pf.lng)
                # ここで都度保存
                atomic_write_json(args.out, out)
                logger.debug("Wrote %d records -> %s", len(out), args.out)
            else:
                logger.warning("No coords / invalid page: %s", durl)
        except Exception as e:
            logger.warning("Error parsing %s: %s", durl, e)
        time.sleep(SLEEP_SEC)
        if i % 10 == 0:
            logger.info("Progress: %d/%d processed, %d saved", i, len(uniq), len(out))

    elapsed = time.perf_counter() - t0
    # 最終保存（冪等）
    atomic_write_json(args.out, out)
    logger.info("DONE: %d processed, %d saved -> %s (%.2fs)", processed, successes, args.out, elapsed)


if __name__ == "__main__":
    main()
