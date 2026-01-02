#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Incremental Pokefuta updater.

機能:
  * 既存の `pokefuta.ndjson` を読み込み現在のマンホール一覧を再取得
  * 削除されたマンホール (HTTP 404 / ページ構造消失) を検出
  * 新規マンホール (まだファイルに存在しないIDでアクセス可能) を検出
  * 変更差分 (タイトル / 座標 / ポケモンなどスキーマフィールドの変化) を検出
  * 結果を: `pokefuta.ndjson` を更新し、変更サマリを `CHANGELOG.md` に追記
  * GitHub Actions 上で動作し、変更があれば exit 0 で終了 (ワークフロー側が自動コミット + PR)

スキーマ:
  { id, title, prefecture, city, address, city_url, lat, lng, pokemons, pokemons_en, pokemons_zh, detail_url, prefecture_site_url, first_seen, added_at, last_updated, status }
  status: "active" | "deleted" (削除検知後も履歴維持)

使い方:
  python update_pokefuta.py --out pokefuta.ndjson --scan-max 1500

GitHub Actions 用想定引数:
  --out pokefuta.ndjson --scan-max 2000 --log-level INFO

差分定義:
  * 新規: status が付与されていない ID が fetch 成功
  * 削除: 既存 status=active だった ID が 404 または座標抽出失敗
  * 変更: 同一 ID で任意フィールド値が変化 (配列は集合比較)

終了コード:
  0: 正常終了 (差分ある/なし問わず)
  2: 異常終了 (例外)
"""
import argparse, csv, json, logging, os, re, signal, sys, time, tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
import requests

# Constants (unified with scrape_pokefuta.py)
DEFAULT_BASE = "https://local.pokemon.jp/manhole/"
HEADERS = {"User-Agent": "pokefuta-tracker-updater (+https://github.com/nishiokya/pokefuta-tracker)"}
HEADERS_EN = {**HEADERS, "Accept-Language": "en-US,en;q=0.9"}
HEADERS_ZH = {**HEADERS, "Accept-Language": "zh-CN,zh;q=0.9"}

REQ_TIMEOUT = 15
RETRY = 3
DEFAULT_SLEEP = 0.4

CORE_COMPARE_FIELDS = [
    "title", "prefecture", "city", "address", "building", "city_url",
    "address_raw", "address_norm", "place_detail", "landmark", "access",
    "parking", "nearby_spots", "tags", "source_urls", "verified_at",
    "confidence", "lat", "lng", "pokemons", "detail_url",
    "prefecture_site_url", "status"
]

PLACEHOLDER_STRINGS = {s.lower() for s in [
    "", "n/a", "na", "-", "－", "unknown", "不明", "未設定", "わかりません"
]}


def _has_content(value: Any, allow_placeholder: bool = False) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return False
        if not allow_placeholder and cleaned.lower() in PLACEHOLDER_STRINGS:
            return False
        return True
    return True


def _split_pipe_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [part.strip() for part in value.split('|') if part.strip()]

def setup_logger(level: str = "INFO") -> logging.Logger:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=lvl, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    return logging.getLogger("pokefuta-updater")


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


def load_title_metadata(dataset_dir: str) -> Dict[str, Dict[str, Any]]:
    """Load title metadata from CSV / TSV files (if available)."""
    title_data: Dict[str, Dict[str, Any]] = {}
    sources = [
        ("title.csv", ","),
        ("title.tsv", "\t"),
    ]
    for filename, delimiter in sources:
        path = os.path.join(dataset_dir, filename)
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                header_sample = f.readline()
                f.seek(0)
                detected_delimiter = delimiter
                if header_sample:
                    if '\t' in header_sample and ',' not in header_sample:
                        detected_delimiter = '\t'
                    elif ',' in header_sample and '\t' not in header_sample:
                        detected_delimiter = ','
                reader = csv.DictReader(f, delimiter=detected_delimiter)
                for row in reader:
                    if not row:
                        continue
                    rid = (row.get('id') or row.get('\ufeffid') or '').strip()
                    if not rid:
                        continue
                    entry: Dict[str, Any] = {}

                    def _clean(name: str, fallback: Optional[str] = None) -> str:
                        raw = row.get(name)
                        if raw is None and fallback:
                            raw = row.get(fallback)
                        if raw is None:
                            return ""
                        return str(raw).strip()

                    building = _clean('building', '建物')
                    if building:
                        entry['building'] = building

                    address_raw = _clean('address_raw') or _clean('address', '住所')
                    if address_raw:
                        entry['address_raw'] = address_raw

                    address_norm = _clean('address_norm')
                    if address_norm:
                        entry['address_norm'] = address_norm

                    prefecture = _clean('prefecture')
                    if prefecture:
                        entry['prefecture'] = prefecture

                    city = _clean('city')
                    if city:
                        entry['city'] = city

                    place_detail = _clean('place_detail')
                    if place_detail:
                        entry['place_detail'] = place_detail

                    landmark = _clean('landmark')
                    if landmark:
                        entry['landmark'] = landmark

                    access = _clean('access')
                    if access:
                        entry['access'] = access

                    parking = _clean('parking')
                    if parking:
                        entry['parking'] = parking

                    nearby_spots = _split_pipe_list(row.get('nearby_spots'))
                    if nearby_spots:
                        entry['nearby_spots'] = nearby_spots

                    tags = _split_pipe_list(row.get('tags'))
                    if tags:
                        entry['tags'] = tags

                    source_urls = [url for url in _split_pipe_list(row.get('source_urls')) if url]
                    if source_urls:
                        entry['source_urls'] = source_urls

                    verified_at = _clean('verified_at')
                    if verified_at:
                        entry['verified_at'] = verified_at

                    confidence_raw = _clean('confidence')
                    if confidence_raw:
                        try:
                            entry['confidence'] = int(confidence_raw)
                        except ValueError:
                            try:
                                entry['confidence'] = float(confidence_raw)
                            except ValueError:
                                pass

                    if entry:
                        title_data[rid] = entry
        except Exception as e:
            print(f"Warning: Failed to load {path}: {e}")
    return title_data


def apply_title_metadata(record: Dict, title_data: Dict[str, Dict[str, Any]]) -> bool:
    """Merge curated metadata into a record. Returns True when updated."""
    if not title_data or not record:
        return False
    rid = record.get('id')
    if not rid:
        return False
    entry = title_data.get(rid)
    if not entry:
        return False

    updated = False

    def _set_value(key: str, value: Any, *, allow_placeholder: bool = False):
        nonlocal updated
        if not _has_content(value, allow_placeholder=allow_placeholder):
            return
        if record.get(key) == value:
            return
        record[key] = value
        updated = True

    def _set_list(key: str, values: Optional[List[str]]):
        nonlocal updated
        if not values:
            return
        normalized = [v for v in values if _has_content(v, allow_placeholder=True)]
        if not normalized:
            return
        if record.get(key) == normalized:
            return
        record[key] = normalized
        updated = True

    _set_value('building', entry.get('building'))
    _set_value('address_raw', entry.get('address_raw'), allow_placeholder=True)
    _set_value('address_norm', entry.get('address_norm'), allow_placeholder=True)
    _set_value('prefecture', entry.get('prefecture'))
    _set_value('city', entry.get('city'))
    _set_value('place_detail', entry.get('place_detail'), allow_placeholder=True)
    _set_value('landmark', entry.get('landmark'), allow_placeholder=True)
    _set_value('access', entry.get('access'), allow_placeholder=True)
    _set_value('parking', entry.get('parking'), allow_placeholder=True)

    best_address = entry.get('address_norm') or entry.get('address_raw')
    _set_value('address', best_address)

    _set_list('nearby_spots', entry.get('nearby_spots'))
    _set_list('tags', entry.get('tags'))
    _set_list('source_urls', entry.get('source_urls'))

    _set_value('verified_at', entry.get('verified_at'), allow_placeholder=True)
    _set_value('confidence', entry.get('confidence'))

    return updated


def parse_detail(detail_url: str, html: str, logger: logging.Logger, title_data: Dict[str, Dict[str, Any]] = None) -> Optional[Dict]:
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
            cleaned = re.sub(r"(ポケモン|図鑑|Pokédex|Pokémon|Pokemon|ずかんへ)", "", txt).strip()
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

    # 住所の取得 - HTML から可能な限り抽出 (不足分は後段の title.tsv で補完)
    address = ""
    # まずWebページから住所らしき文字列を抽出
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
        "building": "",
        "city_url": "",
        "lat": lat,
        "lng": lng,
        "pokemons": pokemons,
        "detail_url": detail_url,
        "prefecture_site_url": "",
        # extended schema (for consistency with incremental updater)
        "first_seen": now_iso,
        "added_at": now_iso,  # alias for first_seen used by web UI
        "last_updated": now_iso,  # unified update timestamp
        "status": "active"
    }


def load_existing(path: str, mode: str = "ndjson") -> List[Dict]:
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


def atomic_write_ndjson(path: str, records: List[Dict]):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=d, encoding="utf-8") as tmp:
        for rec in records:
            tmp.write(json.dumps(rec, ensure_ascii=False) + "\n")
        tmp.flush(); os.fsync(tmp.fileno())
        p = tmp.name
    os.replace(p, path)

# --- diff logic

def _record_changed(new: Dict, old: Dict) -> bool:
    """Check if any core field has meaningfully changed.
    
    Treats None and empty string as equivalent to avoid false positives
    when new fields are added to the schema.
    """
    for k in CORE_COMPARE_FIELDS:
        new_val = new.get(k)
        old_val = old.get(k)
        
        # Normalize None and empty string to be equivalent
        if new_val in (None, "") and old_val in (None, ""):
            continue
        
        if new_val != old_val:
            return True
    return False


def scan_range(base: str, start: int, end: int) -> List[str]:
    base_root = base.rstrip('/')
    if not base_root.endswith('/manhole'):
        base_root = re.sub(r'/manhole/.*$', '/manhole', base_root)
        if not base_root.endswith('/manhole'):
            base_root += '/manhole'
    return [f"{base_root}/desc/{i}/?is_modal=1" for i in range(start, end + 1)]


def now_iso() -> str:
    """Return RFC3339/ISO8601 UTC timestamp (second precision) compatible with JS Date."""
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default=DEFAULT_BASE, help='Base top page URL')
    parser.add_argument('--out', default='pokefuta.ndjson', help='Primary NDJSON output path')
    parser.add_argument('--scan-max', type=int, default=500, help='Max ID to scan')
    parser.add_argument('--limit-new', type=int, default=None, help='Stop scanning after finding this many new records')
    parser.add_argument('--log-level', default='INFO', help='Log level')
    parser.add_argument('--sleep', type=float, default=DEFAULT_SLEEP, help='Sleep seconds between requests')
    parser.add_argument('--no-ml', dest='no_ml', action='store_true', help='Skip English/Chinese enrichment for speed')
    args = parser.parse_args()

    logger = setup_logger(args.log_level)
    sleep_sec = max(0.2, args.sleep)

    dataset_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'dataset')
    title_data = load_title_metadata(dataset_dir)
    logger.info("Loaded %d entries from title metadata (csv/tsv)", len(title_data))

    existing = load_existing(args.out)
    by_id: Dict[str, Dict] = {r['id']: r for r in existing if 'id' in r}

    # Ensure extended fields exist & merge static metadata before diffing
    changed: Dict[str, Dict] = {}
    for r in by_id.values():
        r.setdefault('first_seen', now_iso())
        r.setdefault('status', 'active')
        r.setdefault('added_at', r.get('first_seen'))
        if 'last_updated' not in r:
            legacy = r.get('last_seen') or r.get('source_last_checked') or r.get('first_seen')
            r['last_updated'] = legacy
        if 'last_seen' in r:
            r.pop('last_seen', None)
        if 'source_last_checked' in r:
            r.pop('source_last_checked', None)
        if apply_title_metadata(r, title_data):
            changed.setdefault(r['id'], {})['title_metadata'] = True

    new_records: List[Dict] = []
    deleted_ids: List[str] = []

    last_existing_id = 0
    if by_id:
        try:
            last_existing_id = max(int(i) for i in by_id.keys() if i.isdigit())
        except ValueError:
            last_existing_id = 0

    logger.info("Starting scan up to %d (current max existing id=%d)", args.scan_max, last_existing_id)

    try:
        for i in range(1, args.scan_max + 1):
            detail_url = f"{args.base.rstrip('/')}/desc/{i}/?is_modal=1"
            html = fetch(detail_url, logger, HEADERS)
            if html is None:
                # Mark deletion if previously active
                if str(i) in by_id and by_id[str(i)].get('status') == 'active':
                    by_id[str(i)]['status'] = 'deleted'
                    by_id[str(i)]['last_updated'] = now_iso()
                    changed[str(i)] = {'status': {'old': 'active', 'new': 'deleted'}}
                    deleted_ids.append(str(i))
                time.sleep(sleep_sec)
                continue

            parsed = parse_detail(detail_url, html, logger, title_data)
            if not parsed:
                # treat as potential deletion if existed
                if str(i) in by_id and by_id[str(i)].get('status') == 'active':
                    by_id[str(i)]['status'] = 'deleted'
                    by_id[str(i)]['last_updated'] = now_iso()
                    changed[str(i)] = {'status': {'old': 'active', 'new': 'deleted'}}
                    deleted_ids.append(str(i))
                time.sleep(sleep_sec)
                continue

            pid = parsed['id']
            now_ts = now_iso()
            parsed.setdefault('first_seen', now_ts)
            parsed.setdefault('added_at', now_ts)
            parsed.setdefault('status', 'active')
            parsed.setdefault('last_updated', now_ts)
            apply_title_metadata(parsed, title_data)

            if pid not in by_id:
                logger.info("NEW id=%s", pid)
                by_id[pid] = parsed
                new_records.append(parsed)
                if args.limit_new and len(new_records) >= args.limit_new:
                    logger.info("Limit new=%d reached; stopping scan early", args.limit_new)
                    break
            else:
                # Existing: diff
                old = by_id[pid]
                now_ts = now_iso()
                if old.get('status') == 'deleted':
                    # resurrected
                    old['status'] = 'active'
                    old['last_updated'] = now_ts
                    d = {'status': {'old': 'deleted', 'new': 'active'}}
                    changed[pid] = d if pid not in changed else {**changed[pid], **d}
                else:
                    # Check if record changed using _record_changed function
                    if _record_changed(parsed, old):
                        logger.info("CHANGED id=%s", pid)
                        # Update specific fields
                        for k in ['title', 'prefecture', 'city', 'address', 'building', 'lat', 'lng', 'pokemons', 'pokemons_en', 'pokemons_zh']:
                            if k in parsed:
                                old[k] = parsed[k]
                        old['last_updated'] = now_ts
                        changed[pid] = {'updated': True}
                # NOTE: unchanged active records do NOT update last_updated (diff noise削減)
            time.sleep(sleep_sec)
    except KeyboardInterrupt:
        logger.warning("Interrupted; proceeding to write partial results")

    # Prepare ordered list (keep stable ordering by numeric id then status)
    all_records = list(by_id.values())
    def sort_key(r):
        try:
            return (int(r.get('id', 0)), r.get('status') != 'active')
        except Exception:
            return (999999, True)
    all_records.sort(key=sort_key)

    atomic_write_ndjson(args.out, all_records)
    logger.info("Wrote %d records to %s", len(all_records), args.out)

    # Summary for CI output
    if new_records or deleted_ids or changed:
        summary = {
            'new': len(new_records),
            'deleted': len(deleted_ids),
            'changed': len(changed)
        }
        logger.info("Update summary: %s", summary)
        print("::group::pokefuta-update-summary")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print("::endgroup::")
    else:
        logger.info("No changes detected")

    sys.exit(0)

if __name__ == '__main__':
    main()
