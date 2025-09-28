#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pokefuta scraper with ID scan streaming, per-record save, and SIGINT-safe shutdown.

Examples:
  # Default usage - scans IDs 1-500 and outputs to NDJSON
  python scrape_pokefuta.py

  # Custom ID range
  python scrape_pokefuta.py --scan-min 1 --scan-max 1200

  # JSON array output
  python scrape_pokefuta.py --write-mode array --out pokefuta.json
"""
import argparse, json, logging, os, re, signal, tempfile, time
from dataclasses import dataclass, asdict
from typing import Dict, Generator, Iterable, List, Optional
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

DEFAULT_BASE = "https://local.pokemon.jp/manhole/"
HEADERS = {"User-Agent": "pokefuta-tracker-scraper (+https://github.com/yourname/pokefuta-tracker)"}

# Language-specific headers
HEADERS_EN = {
    "User-Agent": "pokefuta-tracker-scraper (+https://github.com/yourname/pokefuta-tracker)",
    "Accept-Language": "en-US,en;q=0.9"
}

HEADERS_ZH = {
    "User-Agent": "pokefuta-tracker-scraper (+https://github.com/yourname/pokefuta-tracker)",
    "Accept-Language": "zh-CN,zh;q=0.9"
}
REQ_TIMEOUT = 20
SLEEP_SEC = 0.6
RETRY = 3

# Removed traditional crawling patterns - only ID scan is supported

# --- model
@dataclass
class Pokefuta:
    id: str
    title: str
    title_en: str
    title_zh: str
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

def backup_existing_file(path: str, logger: logging.Logger):
    """Create backup of existing file with timestamp."""
    if os.path.exists(path):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = f"{path}.backup_{timestamp}"
        try:
            os.rename(path, backup_path)
            logger.info("Backed up existing file: %s -> %s", path, backup_path)
        except OSError as e:
            logger.warning("Failed to backup existing file %s: %s", path, e)

def write_ndjson(path: str, rec: Dict):
    """Write one JSON object per line (creates new file or overwrites)."""
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False))
        f.write("\n")

# --- dataset loading
def find_last_id_from_file(file_path: str, logger: logging.Logger) -> int:
    """Find the highest ID from existing NDJSON file."""
    if not os.path.exists(file_path):
        logger.info("No existing file found at %s, starting from ID 1", file_path)
        return 0

    max_id = 0
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        current_id = int(data.get('id', 0))
                        max_id = max(max_id, current_id)
                    except (json.JSONDecodeError, ValueError, KeyError):
                        continue
        logger.info("Found highest existing ID: %d in %s", max_id, file_path)
        return max_id
    except Exception as e:
        logger.warning("Error reading existing file %s: %s", file_path, e)
        return 0

def load_city_links(dataset_dir: str) -> Dict[tuple, str]:
    """Load city links from city_link.tsv. Returns {(prefecture, city): url}"""
    city_links = {}
    city_link_path = os.path.join(dataset_dir, "city_link.tsv")
    if os.path.exists(city_link_path):
        with open(city_link_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 3:
                    pref, city, url = parts[0], parts[1], parts[2]
                    # Remove special markers like （県全体案内）
                    clean_city = re.sub(r'[（(].*[）)]', '', city).strip()
                    if clean_city:  # Only add if city name is not empty after cleaning
                        city_links[(pref, clean_city)] = url
    return city_links

def load_titles_addresses(dataset_dir: str) -> tuple[Dict[str, str], Dict[str, str]]:
    """Load titles and addresses from title.tsv. Returns (titles_dict, addresses_dict)"""
    titles = {}
    addresses = {}
    title_path = os.path.join(dataset_dir, "title.tsv")
    if os.path.exists(title_path):
        with open(title_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 3:
                    id_str, title, address = parts[0], parts[1], parts[2]
                    if title.strip():  # Add title if not empty
                        titles[id_str] = title.strip()
                    if address.strip():  # Add address if not empty
                        addresses[id_str] = address.strip()
    return titles, addresses

# --- http
def fetch(url: str, logger: logging.Logger, headers: Dict = None) -> requests.Response:
    if headers is None:
        headers = HEADERS
    last = None
    for i in range(RETRY):
        try:
            r = requests.get(url, headers=headers, timeout=REQ_TIMEOUT)
            if r.status_code == 404:
                logger.debug("GET %s -> 404", url); return r
            r.raise_for_status()
            logger.debug("GET %s -> %d", url, r.status_code); return r
        except Exception as e:
            last = e; logger.warning("GET failed (%s) retry=%d err=%s", url, i+1, e)
            time.sleep(1.5*(i+1))
    raise RuntimeError(f"Failed to fetch {url}: {last}")

# --- parse
def parse_detail_html(detail_url: str, html: str, city_links: Dict[tuple, str], titles: Dict[str, str], addresses: Dict[str, str]) -> Optional[Pokefuta]:
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

    # title extraction (Japanese only - multilingual handled separately)
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

    # pokemons and prefecture site detection (Japanese only)
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

        # Extract Pokemon names (Japanese)
        if t and ("図鑑" in t or "ポケモン" in t or "Pokédex" in t or "ずかん" in t):
            # Extract and normalize Pokemon name
            name = re.sub(r'(図鑑|ポケモン|Pokédex|ずかん|へ|の)', '', t).strip()
            if name and len(name) > 1:
                pokemons.append(name)

    # Also look for Pokemon names in text content (Japanese)
    full_text = soup.get_text()
    pokemon_patterns_ja = [
        r'ポケモン[：:]\s*([^\s、。]+)',
        r'デザイン[：:]\s*([^\s、。]+)',
        r'モチーフ[：:]\s*([^\s、。]+)'
    ]
    for pattern in pokemon_patterns_ja:
        matches = re.findall(pattern, full_text)
        for match in matches:
            clean_name = re.sub(r'[^\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', match).strip()
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
            if re.search(r"/manhole/([a-z0-9_-]+)\.html$", href) and txt:
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

    # Get title from dataset (prioritize dataset title over scraped title)
    dataset_title = titles.get(pid, "")
    final_title = dataset_title if dataset_title else title

    # Get address from dataset
    address = addresses.get(pid, "")

    # Get city URL from dataset
    city_url = ""
    if prefecture and city:
        city_url = city_links.get((prefecture, city), "")

    return Pokefuta(pid, final_title, "", "", prefecture or "", city, address, city_url, lat, lng, pokemons, [], [], detail_url, prefecture_site_url)

def extract_from_detail(detail_url: str, city_links: Dict[tuple, str], titles: Dict[str, str], addresses: Dict[str, str], logger: logging.Logger) -> Optional[Pokefuta]:
    # First, get Japanese content
    r_ja = fetch(detail_url, logger, HEADERS)
    if r_ja.status_code == 404:
        return None

    # Parse Japanese content first
    pokefuta_ja = parse_detail_html(detail_url, r_ja.text, city_links, titles, addresses)
    if not pokefuta_ja:
        return None

    # If Japanese data exists, also try to get English and Chinese versions
    title_en = ""
    title_zh = ""
    pokemons_en = []
    pokemons_zh = []

    try:
        # Try English version
        r_en = fetch(detail_url, logger, HEADERS_EN)
        if r_en.status_code == 200:
            soup_en = BeautifulSoup(r_en.text, "html.parser")
            # Extract English title
            h_en = soup_en.find(["h1","h2"])
            if h_en and h_en.get_text(strip=True):
                title_en = h_en.get_text(strip=True)

            # Extract English Pokemon names
            for a in soup_en.select("a[href]"):
                t = a.get_text(strip=True)
                if t and ("Pokédex" in t or "Pokemon" in t):
                    name = re.sub(r'(Pokédex|Pokemon)', '', t).strip()
                    if name and len(name) > 1 and name not in pokemons_en:
                        pokemons_en.append(name)

        time.sleep(SLEEP_SEC)  # Rate limiting between requests

        # Try Chinese version
        r_zh = fetch(detail_url, logger, HEADERS_ZH)
        if r_zh.status_code == 200:
            soup_zh = BeautifulSoup(r_zh.text, "html.parser")
            # Extract Chinese title
            h_zh = soup_zh.find(["h1","h2"])
            if h_zh and h_zh.get_text(strip=True):
                title_zh = h_zh.get_text(strip=True)

            # Extract Chinese Pokemon names
            for a in soup_zh.select("a[href]"):
                t = a.get_text(strip=True)
                if t and ("图鉴" in t or "寶可夢" in t or "精灵" in t):
                    name = re.sub(r'(图鉴|寶可夢|精灵)', '', t).strip()
                    if name and len(name) > 1 and name not in pokemons_zh:
                        pokemons_zh.append(name)

    except Exception as e:
        logger.warning(f"Failed to fetch multilingual data for {detail_url}: {e}")

    # Update the pokefuta object with multilingual data
    return Pokefuta(
        pokefuta_ja.id,
        pokefuta_ja.title,
        title_en,
        title_zh,
        pokefuta_ja.prefecture,
        pokefuta_ja.city,
        pokefuta_ja.address,
        pokefuta_ja.city_url,
        pokefuta_ja.lat,
        pokefuta_ja.lng,
        pokefuta_ja.pokemons,
        pokemons_en,
        pokemons_zh,
        pokefuta_ja.detail_url,
        pokefuta_ja.prefecture_site_url
    )

# --- ID scan streaming (only supported method)

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
    _ = signum, frame  # Ignore unused parameters
    _running = False
    # 2度目の Ctrl-C で即時終了
    signal.signal(signal.SIGINT, signal.SIG_DFL)

def main():
    global SLEEP_SEC
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=DEFAULT_BASE, help="Top page (EN or JA).")
    parser.add_argument("--out", default="pokefuta.ndjson", help="Output path.")
    parser.add_argument("--dataset-dir", default="dataset", help="Path to dataset directory with TSV files.")
    parser.add_argument("--sleep", type=float, default=SLEEP_SEC, help="Sleep seconds.")
    parser.add_argument("--log-level", default="INFO", help="DEBUG/INFO/WARN/ERROR")
    parser.add_argument("--write-mode", choices=["array","ndjson"], default="ndjson", help="Save as array JSON or NDJSON.")

    # ID scan range
    parser.add_argument("--scan-min", type=int, help="Minimum ID to scan (default: auto-detect from existing file)")
    parser.add_argument("--scan-max", type=int, default=500, help="Maximum ID to scan")
    parser.add_argument("--full-crawl", action="store_true", help="Crawl all IDs from 1 (ignores existing file)")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N successes (testing).")
    args = parser.parse_args()

    logger = setup_logger(args.log_level)
    SLEEP_SEC = max(0.2, args.sleep)
    signal.signal(signal.SIGINT, _sigint_handler)

    # Determine scan range
    if args.full_crawl:
        scan_min = 1
        logger.info("Full crawl mode: starting from ID 1")
    elif args.scan_min is not None:
        scan_min = args.scan_min
        logger.info("Manual scan range: starting from ID %d", scan_min)
    else:
        # Auto-detect from existing file (incremental mode)
        last_id = find_last_id_from_file(args.out, logger)
        scan_min = last_id + 1
        logger.info("Incremental mode: starting from ID %d (last found: %d)", scan_min, last_id)

    # Backup existing output file (only for full crawl or array mode)
    if args.full_crawl or args.write_mode == "array":
        backup_existing_file(args.out, logger)

    # Load datasets
    logger.info("Loading datasets from %s", args.dataset_dir)
    city_links = load_city_links(args.dataset_dir)
    titles, addresses = load_titles_addresses(args.dataset_dir)
    logger.info("Loaded %d city links, %d titles and %d addresses", len(city_links), len(titles), len(addresses))

    # ID scan streaming (only method)
    def detail_url_stream() -> Iterable[str]:
        yield from stream_scan_ids(args.base, scan_min, args.scan_max, logger)

    # 逐次保存
    out_array: List[Dict] = []
    successes = 0
    processed = 0

    try:
        for durl in detail_url_stream():
            if not _running:
                logger.warning("SIGINT received. Flushing and exiting...")
                break
            rec = extract_from_detail(durl, city_links, titles, addresses, logger)
            processed += 1
            if rec:
                successes += 1
                obj = asdict(rec)
                if args.write_mode == "ndjson":
                    write_ndjson(args.out, obj)          # ★ 1件ごと即追記
                    logger.info("OK #%d id=%s -> %s (NDJSON written)", successes, rec.id, args.out)
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
