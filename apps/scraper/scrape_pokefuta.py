#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pokefuta scraper with streaming scan, per-record save, and SIGINT-safe shutdown.

Examples:
  # IDスキャンをストリーム処理（推奨）
  python scrape_pokefuta.py --scan-min 1 --scan-max 1200 --out pokefuta.scan.v1.json

  # 中断にさらに強い NDJSON 出力
  python scrape_pokefuta.py --scan-min 1 --scan-max 1200 --out pokefuta.ndjson --write-mode ndjson

  # 従来の巡回（prefページ→詳細）も同様に逐次保存
  python scrape_pokefuta.py --out pokefuta.v1.json
"""
import argparse, json, logging, os, re, signal, sys, tempfile, time
from dataclasses import dataclass, asdict
from typing import Dict, Generator, Iterable, List, Optional, Set
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

DEFAULT_BASE = "https://local.pokemon.jp/manhole/"
HEADERS = {"User-Agent": "pokefuta-tracker-scraper (+https://github.com/yourname/pokefuta-tracker)"}
REQ_TIMEOUT = 20
SLEEP_SEC = 0.6
RETRY = 3

DETAIL_HREF_PATTERNS = ("/manhole/desc/",)
PREF_PAGE_PAT = re.compile(r"/manhole/([a-z0-9_-]+)\.html$")

# --- model
@dataclass
class Pokefuta:
    id: str
    title: str
    prefecture: str
    city: str
    lat: float
    lng: float
    pokemons: List[str]
    detail_url: str
    prefecture_site_url: str
    source_last_checked: str

# --- logging
def setup_logger(level: str = "INFO") -> logging.Logger:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=lvl, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    return logging.getLogger("pokefuta-scraper")

# --- io helpers
def atomic_write_json_array(path: str, payload: List[Dict]):
    """Write JSON array atomically."""
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=d, encoding="utf-8") as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp.flush(); os.fsync(tmp.fileno())
        tmp_path = tmp.name
    os.replace(tmp_path, path)

def append_ndjson(path: str, rec: Dict):
    """Append one JSON object per line."""
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False))
        f.write("\n")

# --- http
def fetch(url: str, logger: logging.Logger) -> requests.Response:
    last = None
    for i in range(RETRY):
        try:
            r = requests.get(url, headers=HEADERS, timeout=REQ_TIMEOUT)
            if r.status_code == 404:
                logger.debug("GET %s -> 404", url); return r
            r.raise_for_status()
            logger.debug("GET %s -> %d", url, r.status_code); return r
        except Exception as e:
            last = e; logger.warning("GET failed (%s) retry=%d err=%s", url, i+1, e)
            time.sleep(1.5*(i+1))
    raise RuntimeError(f"Failed to fetch {url}: {last}")

# --- parse
def parse_detail_html(detail_url: str, html: str, now_iso: str, logger: logging.Logger) -> Optional[Pokefuta]:
    soup = BeautifulSoup(html, "html.parser")
    # coords
    lat = lng = None
    for a in soup.select('a[href*="maps.google"]'):
        qv = parse_qs(urlparse(a["href"]).query).get("q", [])
        if not qv: continue
        m = re.match(r"\s*([+-]?\d+(\.\d+)?),\s*([+-]?\d+(\.\d+)?)", qv[0])
        if m:
            lat, lng = float(m.group(1)), float(m.group(3)); break
    if lat is None or lng is None:
        return None

    # title (Japanese site extraction)
    title = ""
    # Try h1, h2 first
    h = soup.find(["h1","h2"])
    if h and h.get_text(strip=True):
        title = h.get_text(strip=True)
    # If no title found, try specific class patterns
    if not title:
        title_elem = soup.find(class_=re.compile(r'title|heading', re.I))
        if title_elem:
            title = title_elem.get_text(strip=True)

    # pokemons and prefecture site detection
    pokemons: List[str] = []
    prefecture_site_url = ""

    # Look for Pokemon names and prefecture site links
    for a in soup.select("a[href]"):
        t = a.get_text(strip=True)
        href = a.get("href", "")

        # Check for prefecture site links
        if re.search(r'(ローカルActs.*ページ|.*県ページ|都道府県.*ページ)', t):
            if href:
                prefecture_site_url = urljoin(detail_url, href)
            continue  # Don't add to pokemon list

        # Extract Pokemon names
        if t and ("図鑑" in t or "ポケモン" in t or "Pokédex" in t or "ずかん" in t):
            # Extract and normalize Pokemon name
            name = re.sub(r'(図鑑|ポケモン|Pokédex|ずかん|へ|の)', '', t).strip()
            if name and len(name) > 1:
                pokemons.append(name)

    # Also look for Pokemon names in text content
    pokemon_patterns = [
        r'ポケモン[：:]\s*([^\s、。]+)',
        r'デザイン[：:]\s*([^\s、。]+)',
        r'モチーフ[：:]\s*([^\s、。]+)'
    ]
    for pattern in pokemon_patterns:
        matches = re.findall(pattern, soup.get_text())
        for match in matches:
            clean_name = re.sub(r'[^\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', match).strip()
            # Remove common suffixes
            clean_name = re.sub(r'(ずかん|図鑑|へ)$', '', clean_name).strip()
            if clean_name and clean_name not in pokemons:
                pokemons.append(clean_name)

    # prefecture and city extraction from title
    prefecture = ""
    city = ""
    # Extract from title (e.g., "鹿児島県/指宿市" -> "鹿児島県", "指宿市")
    if title and '/' in title:
        parts = title.split('/')
        if len(parts) >= 2:
            prefecture_part = parts[0].strip()
            city_part = parts[1].strip()

            # Check if it looks like a prefecture name
            if re.match(r'.*[都道府県]$', prefecture_part):
                prefecture = prefecture_part

            # Extract city name (市町村)
            if city_part:
                city = city_part

    # If no prefecture found from title, try breadcrumb or navigation patterns
    if not prefecture:
        for a in reversed(soup.select("a[href]")):
            href = a.get("href",""); txt = a.get_text(strip=True)
            if PREF_PAGE_PAT.search(href) and txt:
                # Clean up prefecture name from navigation
                cleaned_pref = re.sub(r'(トップへ|へ戻る|に戻る)$', '', txt).strip()
                if re.match(r'.*[都道府県]$', cleaned_pref):
                    prefecture = cleaned_pref
                    break

    # If still no prefecture found, try to extract from URL or page content
    if not prefecture:
        # Extract from URL path
        url_parts = detail_url.split('/')
        for part in url_parts:
            if re.match(r'^[a-z]+$', part) and len(part) > 2:
                # Try to map URL part to prefecture name
                prefecture_map = {
                    'kagoshima': '鹿児島県',
                    'aomori': '青森県',
                    'iwate': '岩手県',
                    'miyagi': '宮城県',
                    'fukushima': '福島県',
                    'tokyo': '東京都',
                    'osaka': '大阪府',
                    'kyoto': '京都府',
                    'hyogo': '兵庫県',
                    'nara': '奈良県',
                    'wakayama': '和歌山県',
                    'shiga': '滋賀県',
                    'mie': '三重県',
                    'aichi': '愛知県',
                    'shizuoka': '静岡県',
                    'yamanashi': '山梨県',
                    'nagano': '長野県',
                    'gifu': '岐阜県',
                    'fukui': '福井県',
                    'ishikawa': '石川県',
                    'toyama': '富山県',
                    'niigata': '新潟県',
                    'gunma': '群馬県',
                    'tochigi': '栃木県',
                    'ibaraki': '茨城県',
                    'chiba': '千葉県',
                    'saitama': '埼玉県',
                    'kanagawa': '神奈川県',
                    'hokkaido': '北海道',
                    'okinawa': '沖縄県',
                }
                if part in prefecture_map:
                    prefecture = prefecture_map[part]
                    break

    # id
    m = re.search(r"/desc/(\d+)/?", detail_url)
    pid = m.group(1) if m else ""
    return Pokefuta(pid, title, prefecture or "", city, lat, lng, pokemons, detail_url, prefecture_site_url, now_iso)

def extract_from_detail(detail_url: str, now_iso: str, logger: logging.Logger) -> Optional[Pokefuta]:
    r = fetch(detail_url, logger)
    if r.status_code == 404: return None
    return parse_detail_html(detail_url, r.text, now_iso, logger)

# --- url streams (yield で逐次処理)
def stream_prefecture_pages(base_url: str, logger: logging.Logger) -> Generator[str, None, None]:
    """BFSで都道府県ページのURLを逐次yield。"""
    seen: Set[str] = set(); queue: List[str] = [base_url]
    logger.info("Collecting prefecture pages from %s", base_url)
    while queue:
        url = queue.pop(0)
        r = fetch(url, logger)
        if r.status_code == 404: continue
        soup = BeautifulSoup(r.text, "html.parser")
        # prefecture
        for a in soup.select("a[href]"):
            href = a.get("href"); 
            if not href: continue
            absu = urljoin(url, href)
            if any(p in absu for p in DETAIL_HREF_PATTERNS): continue
            if PREF_PAGE_PAT.search(urlparse(absu).path) and absu not in seen:
                seen.add(absu); logger.debug("pref: %s", absu); yield absu
        # region discovery
        for a in soup.select("a[href]"):
            href = a.get("href"); 
            if not href: continue
            absu = urljoin(url, href); p = urlparse(absu).path
            if p.startswith("/manhole/") and p.endswith(".html"):
                if absu not in seen:
                    seen.add(absu); queue.append(absu)
        time.sleep(SLEEP_SEC)

def stream_detail_links_from_pref(pref_url: str, logger: logging.Logger) -> Generator[str, None, None]:
    """都道府県ページから詳細URLを逐次yield。"""
    r = fetch(pref_url, logger)
    if r.status_code == 404: return
    soup = BeautifulSoup(r.text, "html.parser")
    seen: Set[str] = set()
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if any(p in href for p in DETAIL_HREF_PATTERNS):
            u = urljoin(pref_url, href)
            if "is_modal=1" not in u:
                u = u + ("&" if "?" in u else "?") + "is_modal=1"
            if u not in seen:
                seen.add(u); logger.debug("detail: %s", u); yield u
    time.sleep(SLEEP_SEC)

def stream_scan_ids(base_top: str, id_min: int, id_max: int, logger: logging.Logger) -> Generator[str, None, None]:
    """IDレンジを逐次yield（存在するものだけ）。"""
    base_root = base_top.rstrip("/")
    if not base_root.endswith("/manhole"):
        base_root = re.sub(r"/manhole/.*$", "/manhole", base_root)
        if not base_root.endswith("/manhole"): base_root += "/manhole"
    logger.info("Streaming scan ids from %d to %d", id_min, id_max)
    for i in range(id_min, id_max+1):
        u = f"{base_root}/desc/{i}/?is_modal=1"
        r = fetch(u, logger)
        if r.status_code != 404 and ("maps.google" in r.text or "/manhole/" in r.text):
            logger.debug("  id=%d exists -> %s", i, u); yield u
        else:
            logger.debug("  id=%d missing", i)
        time.sleep(SLEEP_SEC)

# --- main
SLEEP_SEC = 0.6
_running = True
def _sigint_handler(signum, frame):
    global _running
    _running = False
    # 2度目の Ctrl-C で即時終了
    signal.signal(signal.SIGINT, signal.SIG_DFL)

def main():
    global SLEEP_SEC
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=DEFAULT_BASE, help="Top page (EN or JA).")
    parser.add_argument("--out", default="pokefuta.v1.json", help="Output path.")
    parser.add_argument("--sleep", type=float, default=SLEEP_SEC, help="Sleep seconds.")
    parser.add_argument("--log-level", default="INFO", help="DEBUG/INFO/WARN/ERROR")
    parser.add_argument("--write-mode", choices=["array","ndjson"], default="array", help="Save as array JSON or NDJSON.")

    # scan / crawl
    parser.add_argument("--scan-min", type=int)
    parser.add_argument("--scan-max", type=int)
    parser.add_argument("--auto-scan", action="store_true")  # （簡略化のため省略実装可）
    parser.add_argument("--start-id", type=int, default=1)
    parser.add_argument("--miss-threshold", type=int, default=100)
    parser.add_argument("--limit", type=int, default=0, help="Stop after N successes (testing).")
    args = parser.parse_args()

    logger = setup_logger(args.log_level)
    SLEEP_SEC = max(0.2, args.sleep)
    signal.signal(signal.SIGINT, _sigint_handler)

    # URLを逐次ストリーム
    def detail_url_stream() -> Iterable[str]:
        if args.scan_min is not None and args.scan_max is not None:
            yield from stream_scan_ids(args.base, args.scan_min, args.scan_max, logger)
        else:
            base = args.base if args.base.endswith("/") else args.base + "/"
            for pref in stream_prefecture_pages(base, logger):
                for u in stream_detail_links_from_pref(pref, logger):
                    yield u

    # 逐次保存
    out_array: List[Dict] = []
    successes = 0
    processed = 0

    try:
        for durl in detail_url_stream():
            if not _running:
                logger.warning("SIGINT received. Flushing and exiting...")
                break
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            rec = extract_from_detail(durl, now_iso, logger)
            processed += 1
            if rec:
                successes += 1
                obj = asdict(rec)
                if args.write_mode == "ndjson":
                    append_ndjson(args.out, obj)          # ★ 1件ごと即追記
                    logger.info("OK #%d id=%s -> %s (NDJSON appended)", successes, rec.id, args.out)
                else:
                    out_array.append(obj)
                    atomic_write_json_array(args.out, out_array)  # ★ 1件ごと即アトミック上書き
                    logger.info("OK #%d id=%s -> %s (array size=%d)", successes, rec.id, args.out, len(out_array))
            else:
                logger.debug("skip (no coords): %s", durl)

            if args.limit and successes >= args.limit:
                logger.info("Limit %d reached. Stopping.", args.limit)
                break
    finally:
        # 最終フラッシュ（arrayモードのみ必要）
        if args.write_mode == "array":
            atomic_write_json_array(args.out, out_array)
            logger.info("Final flush: %d records -> %s", len(out_array), args.out)

    logger.info("DONE: processed=%d, saved=%d, mode=%s, out=%s",
                processed, successes, args.write_mode, args.out)

if __name__ == "__main__":
    main()
