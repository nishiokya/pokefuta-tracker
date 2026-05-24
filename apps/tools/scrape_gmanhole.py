#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gundam manhole initial dataset scraper.

本スクリプトはガンダムマンホール公式サイト (https://www.g-manhole.net/) の
詳細ページ `about/detail.php?id=<N>` を ID 連番総当たりで走査し、メタデータを
NDJSON もしくは JSON 配列で保存します。

取得対象 (暫定最小):
  * id (数値文字列)
  * title (h3 の場所名を優先 / 固定文字列 fallback)
  * prefecture / city (「都/道/府/県/市/町/村/区」パターンから抽出)
  * address (ページ内の住所行)
  * image_urls (マンホール画像 URL 群: ダウンロードはせず URL のみ)
  * franchise = "gundam"
  * characters / series (将来拡張: 現状は空配列/空文字)
  * lat / lng (サイトに未掲載のため null。後で別途ジオコーディング可能)
  * timestamps (first_seen / added_at / last_updated)
  * status (active 固定)

注意:
  * 公式ページの注意書きに従い、画像データの転載は行わず URL のみ記録。
  * 過度な同時アクセスを避けるため sleep を適切に設定してください。
  * 利用規約や robots.txt の変更には随時対応が必要です。

使い方例:
  python apps/scraper/scrape_gmanhole.py --scan-max 80 --out gmanhole.ndjson
  python apps/scraper/scrape_gmanhole.py --scan-min 40 --scan-max 60 --write-mode array --out gmanhole.json
"""
from __future__ import annotations
import argparse, json, logging, os, re, signal, sys, tempfile, time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

DEFAULT_BASE = "https://www.g-manhole.net/about/"
HEADERS = {"User-Agent": "gmanhole-initial-scraper (+https://github.com/nishiokya/pokefuta-tracker)"}
REQ_TIMEOUT = 15
RETRY = 3
DEFAULT_SLEEP = 0.6  # 若干長め (画像が多いため)
GEOCODE_SLEEP_DEFAULT = 1.1  # Nominatim 推奨レートより少し余裕 (gsi はより高速)

# 簡易キャラクター / シリーズ名検出用パターン (ページ内テキスト/alt から抽出)
# 公式表記揺れをある程度許容する正規表現。過剰検出は後で手動クリーニング前提。
CHARACTER_PATTERNS = [
    (r"アムロ", "アムロ"),
    (r"シャア", "シャア"),
    (r"カミーユ", "カミーユ"),
    (r"セイラ", "セイラ"),
    (r"ブライト", "ブライト"),
    (r"リュウ", "リュウ"),
    (r"ガルマ", "ガルマ"),
    (r"ハマーン", "ハマーン"),
    (r"ジュドー", "ジュドー"),
    (r"フリーダム", "フリーダム"),
    (r"ストライク", "ストライク"),
    (r"キラ", "キラ"),
    (r"ラクス", "ラクス"),
    (r"刹那", "刹那"),
    (r"バナージ", "バナージ"),
    (r"リディ", "リディ"),
]
SERIES_PATTERNS = [
    (r"機動戦士ガンダムUC|ガンダムユニコーン", "機動戦士ガンダムUC"),
    (r"機動戦士ガンダムSEED|ガンダムSEED", "機動戦士ガンダムSEED"),
    (r"機動戦士ガンダム00|ガンダム00", "機動戦士ガンダム00"),
    (r"機動戦士ガンダムTHE ORIGIN|ガンダムTHE ORIGIN", "機動戦士ガンダムTHE ORIGIN"),
    (r"機動戦士ガンダム\b", "機動戦士ガンダム"),
]

@dataclass
class GManhole:
    id: str
    title: str
    prefecture: str
    city: str
    address: str
    image_urls: List[str]
    franchise: str
    characters: List[str]
    series: str
    lat: Optional[float]
    lng: Optional[float]
    detail_url: str


def setup_logger(level: str = "INFO") -> logging.Logger:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=lvl, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    return logging.getLogger("gmanhole-init")


def fetch(url: str, logger: logging.Logger) -> Optional[str]:
    last_err = None
    for i in range(RETRY):
        try:
            r = requests.get(url, headers=HEADERS, timeout=REQ_TIMEOUT)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.text
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning("fetch failed (%s) retry=%d err=%s", url, i + 1, e)
            time.sleep(0.8 * (i + 1))
    logger.error("giving up %s: %s", url, last_err)
    return None


_pref_re = re.compile(r"([\w一-龠ぁ-んァ-ヶー]+(?:都|道|府|県))/([\w一-龠ぁ-んァ-ヶー]+(?:市|区|町|村))")
_addr_re = re.compile(r"[一-龠ぁ-んァ-ヶA-Za-z0-9\-ー・\s]+\d")  # 簡易: 数字含む行を住所候補に


def _slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[\s　/]+", "-", s)
    s = re.sub(r"[^a-z0-9\-]+", "", s)
    s = re.sub(r"-+", "-", s).strip('-')
    return s or "unknown"


def parse_detail(detail_url: str, html: str, logger: logging.Logger) -> Optional[Dict]:
    soup = BeautifulSoup(html, "html.parser")

    # ID
    m = re.search(r"id=(\d+)", detail_url)
    pid = m.group(1) if m else ""
    if not pid:
        return None

    # 全テキスト列挙
    texts: List[str] = [t.strip() for t in soup.stripped_strings if t.strip()]

    prefecture = city = ""
    address = ""
    title = ""

    # prefecture/city 抽出
    for t in texts:
        pm = _pref_re.search(t)
        if pm:
            prefecture = pm.group(1)
            city = pm.group(2)
            break

    # 住所候補: prefecture + city を含み数字があり、かつ『マンホール』行ではない
    for t in texts:
        if prefecture and city and prefecture in t and city in t and "マンホール" not in t and _addr_re.search(t):
            address = t
            break

    # タイトル: ページ先頭付近の h3 が場所名 (例: 芸術館通り歩道)
    h3 = soup.find("h3")
    if h3 and h3.get_text(strip=True):
        title = h3.get_text(strip=True)
    if not title:
        # fallback: 最初の住所候補 or 固定文字
        title = address or "ガンダムマンホール"

    # 画像 URL 収集 (id ディレクトリ含むパス)
    image_urls: List[str] = []
    for img in soup.find_all("img"):
        src = img.get("src", "").strip()
        if not src:
            continue
        # 正規化 (相対 URL 対応)
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = "https://www.g-manhole.net" + src
        if f"img{pid}" in src and "img_manhole" in src:
            image_urls.append(src.split("?")[0])  # ver クエリ除去
    image_urls = sorted({u for u in image_urls})

    # キャラクター/シリーズ検出
    joined_text = "\n".join(texts)
    characters: List[str] = []
    for pat, label in CHARACTER_PATTERNS:
        if re.search(pat, joined_text):
            characters.append(label)
    characters = sorted({c for c in characters})

    series = ""
    for pat, label in SERIES_PATTERNS:
        if re.search(pat, joined_text):
            series = label
            break

    # lat/lng は未提供 -> null (後段ジオコーディングで補完)
    lat = None
    lng = None

    slug = _slugify(title or pid)

    now_iso = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    return {
        "id": pid,
        "title": title,
        "prefecture": prefecture,
        "city": city,
        "address": address,
        "image_urls": image_urls,
    "franchise": "gundam",
    "characters": characters,
    "series": series,
    "slug": slug,
    "images_count": len(image_urls),
        "lat": lat,
        "lng": lng,
        "detail_url": detail_url,
        # timestamps & status
        "first_seen": now_iso,
        "added_at": now_iso,
        "last_updated": now_iso,
        "status": "active"
    }


CORE_COMPARE_FIELDS = [
    "title", "prefecture", "city", "address", "image_urls", "images_count", "franchise", "characters", "series", "slug", "lat", "lng", "detail_url", "status"
]


def _record_changed(new: Dict, old: Dict) -> bool:
    for k in CORE_COMPARE_FIELDS:
        if new.get(k) != old.get(k):
            return True
    return False


def merge_with_existing(existing: List[Dict], freshly_scraped: List[Dict], now_iso: str) -> Tuple[List[Dict], bool]:
    old_by_id = {r.get("id"): r for r in existing if r.get("id")}
    new_by_id = {r.get("id"): r for r in freshly_scraped if r.get("id")}
    changed = False
    merged: List[Dict] = []

    for old in existing:
        oid = old.get("id")
        if not oid:
            continue
        if oid in new_by_id:
            new_rec = new_by_id[oid]
            if _record_changed(new_rec, old):
                new_rec["first_seen"] = old.get("first_seen", new_rec.get("first_seen"))
                new_rec["added_at"] = old.get("added_at", new_rec.get("added_at"))
                new_rec["last_updated"] = now_iso
                merged.append(new_rec)
                changed = True
            else:
                merged.append(old)
            del new_by_id[oid]
        else:
            merged.append(old)

    for rec in freshly_scraped:
        rid = rec.get("id")
        if rid in new_by_id:
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
    # detail.php?id=<N>
    return [f"{base_root}/detail.php?id={i}" for i in range(start, end + 1)]


def load_existing(path: str, mode: str) -> List[Dict]:
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default=DEFAULT_BASE, help='Base about URL (一覧ページルート)')
    parser.add_argument('--scan-min', type=int, default=1, help='Start ID (inclusive)')
    parser.add_argument('--scan-max', type=int, default=80, help='End ID (inclusive)')
    parser.add_argument('--out', default='gmanhole.ndjson', help='Output file path')
    parser.add_argument('--write-mode', choices=['ndjson', 'array'], default='ndjson', help='Output format')
    parser.add_argument('--sleep', type=float, default=DEFAULT_SLEEP, help='Sleep seconds between requests')
    parser.add_argument('--log-level', default='INFO', help='Log level')
    parser.add_argument('--limit', type=int, default=0, help='Stop after N successful records (testing)')
    parser.add_argument('--geocode', action='store_true', help='Attempt geocoding addresses to fill lat/lng')
    parser.add_argument('--geocode-provider', choices=['gsi', 'nominatim', 'google'], default='gsi', help='Geocode provider (gsi=国土地理院, nominatim=OSM, google=*API key required)')
    parser.add_argument('--geocode-cache', default='gmanhole_geocode_cache.json', help='Geocode cache file (address->lat/lng)')
    parser.add_argument('--geocode-sleep', type=float, default=GEOCODE_SLEEP_DEFAULT, help='Sleep seconds between geocode requests (provider specific override applies)')
    parser.add_argument('--google-api-key-env', default='GOOGLE_MAPS_API_KEY', help='Environment variable name storing Google Maps Geocoding API key')
    args = parser.parse_args()

    logger = setup_logger(args.log_level)
    signal.signal(signal.SIGINT, _sigint_handler)
    sleep_sec = max(0.15, args.sleep)

    if args.scan_min < 1 or args.scan_max < args.scan_min:
        logger.error('Invalid scan range: %d..%d', args.scan_min, args.scan_max)
        sys.exit(1)

    detail_urls = scan_range(args.base.rstrip('/'), args.scan_min, args.scan_max)
    logger.info('Scanning IDs %d..%d total=%d', args.scan_min, args.scan_max, len(detail_urls))

    results: List[Dict] = []
    processed = 0
    successes = 0
    start_ts = time.time()

    # ジオコーディングキャッシュロード
    geocode_cache: Dict[str, Dict[str, float]] = {}
    if args.geocode and os.path.exists(args.geocode_cache):
        try:
            with open(args.geocode_cache, 'r', encoding='utf-8') as cf:
                data = json.load(cf)
                if isinstance(data, dict):
                    geocode_cache = {k: v for k, v in data.items() if isinstance(v, dict) and 'lat' in v and 'lng' in v}
        except Exception:
            logger.warning('Failed to load geocode cache, starting empty')

    def _normalize_jp_address(addr: str) -> str:
        if not addr:
            return addr
        # 全角数字→半角 / 全角-hyphen様 -> - / 余分な空白除去
        trans = str.maketrans({
            '０':'0','１':'1','２':'2','３':'3','４':'4','５':'5','６':'6','７':'7','８':'8','９':'9',
            '－':'-','―':'-','ー':'-'
        })
        addr = addr.translate(trans)
        # 連続ハイフン縮約
        addr = re.sub(r'-{2,}', '-', addr)
        # 住所行に含まれる末尾の語尾 ("地先" など) はそのまま
        addr = addr.strip()
        return addr

    def geocode_address(address: str, prefecture: str, city: str) -> Optional[Tuple[float, float]]:
        if not address or not prefecture:
            return None
        norm_addr = _normalize_jp_address(address)
        key = f"{prefecture}|{city}|{norm_addr}"
        if key in geocode_cache:
            logger.info('geocode cache hit addr="%s" lat=%.6f lng=%.6f', address, geocode_cache[key]['lat'], geocode_cache[key]['lng'])
            return geocode_cache[key]['lat'], geocode_cache[key]['lng']
        provider = args.geocode_provider
        if provider == 'gsi':
            # 国土地理院 (GSI) AddressSearch API: https://msearch.gsi.go.jp/address-search/AddressSearch?q=<addr>
            q = f"{prefecture}{city}{norm_addr}"  # シンプル連結
            try:
                resp = requests.get(
                    'https://msearch.gsi.go.jp/address-search/AddressSearch',
                    params={'q': q},
                    headers={'User-Agent': HEADERS['User-Agent'] + ' geocode-gsi'},
                    timeout=15
                )
                if resp.status_code == 200:
                    arr = resp.json()
                    if isinstance(arr, list) and arr:
                        # geometry.coordinates -> [lng, lat]
                        coords = arr[0].get('geometry', {}).get('coordinates')
                        if isinstance(coords, list) and len(coords) >= 2:
                            lng = float(coords[0]); lat = float(coords[1])
                            geocode_cache[key] = {'lat': lat, 'lng': lng, 'provider': 'gsi'}
                            logger.info('geocode success (gsi) addr="%s" q="%s" lat=%.6f lng=%.6f', address, q, lat, lng)
                            # GSI は比較的速いが念のため少し sleep (短め)
                            time.sleep(max(min(args.geocode_sleep, 0.6), 0.3))
                            return lat, lng
            except Exception as e:  # noqa: BLE001
                logger.debug('geocode gsi failed addr=%s err=%s', address, e)
            return None
        elif provider == 'nominatim':
            q = f"{prefecture}{city} {norm_addr}, Japan".strip()
            try:
                resp = requests.get(
                    'https://nominatim.openstreetmap.org/search',
                    params={'q': q, 'format': 'json', 'limit': 1},
                    headers={'User-Agent': HEADERS['User-Agent'] + ' geocode'},
                    timeout=20
                )
                if resp.status_code == 200:
                    arr = resp.json()
                    if isinstance(arr, list) and arr:
                        lat = float(arr[0]['lat']); lng = float(arr[0]['lon'])
                        geocode_cache[key] = {'lat': lat, 'lng': lng, 'provider': 'nominatim'}
                        logger.info('geocode success (nominatim) addr="%s" q="%s" lat=%.6f lng=%.6f', address, q, lat, lng)
                        time.sleep(max(args.geocode_sleep, 1.0))  # レート抑制
                        return lat, lng
            except Exception as e:  # noqa: BLE001
                logger.debug('geocode nominatim failed addr=%s err=%s', address, e)
            return None
        elif provider == 'google':
            api_key = os.getenv(args.google_api_key_env, '')
            if not api_key:
                logger.warning('google geocode selected but API key env %s not set', args.google_api_key_env)
                return None
            q = f"{prefecture}{city}{norm_addr}".strip()
            try:
                resp = requests.get(
                    'https://maps.googleapis.com/maps/api/geocode/json',
                    params={'address': q, 'language': 'ja', 'key': api_key},
                    timeout=20
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get('results')
                    if isinstance(results, list) and results:
                        loc = results[0].get('geometry', {}).get('location')
                        if loc and 'lat' in loc and 'lng' in loc:
                            lat = float(loc['lat']); lng = float(loc['lng'])
                            geocode_cache[key] = {'lat': lat, 'lng': lng, 'provider': 'google'}
                            logger.info('geocode success (google) addr="%s" q="%s" lat=%.6f lng=%.6f', address, q, lat, lng)
                            # Google はクォータ課金制: 過度 sleep 不要だが最小 0.2s
                            time.sleep(max(min(args.geocode_sleep, 0.5), 0.2))
                            return lat, lng
            except Exception as e:  # noqa: BLE001
                logger.debug('geocode google failed addr=%s err=%s', address, e)
            return None
        else:
            logger.error('Unknown geocode provider: %s', provider)
            return None

    for url in detail_urls:
        if not _running:
            logger.warning('Interrupted by user, stopping early...')
            break
        processed += 1
        html = fetch(url, logger)
        if html is None:  # 404 or failure
            time.sleep(sleep_sec)
            continue
        rec = parse_detail(url, html, logger)
        if not rec:
            time.sleep(sleep_sec)
            continue
        # ジオコーディング (任意)
        if args.geocode and rec.get('lat') is None:
            loc = geocode_address(rec.get('address', ''), rec.get('prefecture', ''), rec.get('city', ''))
            if loc:
                rec['lat'], rec['lng'] = loc
                rec['geocoded'] = True
            else:
                rec['geocoded'] = False
        results.append(rec)
        successes += 1
        if args.limit and successes >= args.limit:
            logger.info('Limit %d reached, stopping early', args.limit)
            break
        time.sleep(sleep_sec)

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

    # キャッシュ書き戻し
    if args.geocode and geocode_cache:
        try:
            with open(args.geocode_cache, 'w', encoding='utf-8') as cf:
                json.dump(geocode_cache, cf, ensure_ascii=False, indent=2)
        except Exception as e:  # noqa: BLE001
            logger.warning('Failed to persist geocode cache err=%s', e)

    dur = time.time() - start_ts
    logger.info('DONE processed=%d success=%d current_records=%d mode=%s out=%s elapsed=%.1fs changed=%s', processed, successes, len(merged if changed_flag else existing), args.write_mode, args.out, dur, changed_flag)
    logger.info('次回以降の更新差分検出は別途 update スクリプト (未実装) を検討してください。')


if __name__ == '__main__':  # pragma: no cover
    main()
