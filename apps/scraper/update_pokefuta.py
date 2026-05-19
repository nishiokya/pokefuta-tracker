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
import argparse, json, logging, os, re, signal, sys, time, tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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

# ウェブスクレイプ由来フィールド — 変化時に last_updated を更新する
# 手動メタデータ(tags/address_norm/building など)はここに含めない
CORE_COMPARE_FIELDS = [
    "title", "prefecture", "city", "address",
    "lat", "lng", "pokemons", "detail_url",
    "prefecture_site_url", "status", "is_prefecture_site"
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


def load_manhole_titles_master(dataset_dir: str) -> Dict:
    """Load full dataset/manhole_titles.json and return the raw master dict."""
    path = os.path.join(dataset_dir, 'manhole_titles.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load {path}: {e}", file=sys.stderr)
        return {}


def _compute_and_attach_titles(all_records: List[Dict], dataset_dir: str,
                                logger: logging.Logger) -> None:
    """Compute 称号 titles for all records and store as manhole["titles"]."""
    try:
        from manhole_titles import build_title_context
        from manhole_titles import nearby_count as _nc
        from manhole_titles import compute_titles
    except ImportError as exc:
        logger.warning("manhole_titles module not found; skipping title computation: %s", exc)
        return

    master = load_manhole_titles_master(dataset_dir)
    if not master:
        logger.warning("manhole_titles.json not loaded; skipping title computation")
        return

    ctx = build_title_context(all_records, master)
    attached = 0
    for r in all_records:
        if r.get("status") != "active":
            r.pop("titles", None)
            continue
        mid = str(r.get("id", ""))
        n = _nc(mid, r.get("lat"), r.get("lng"), ctx["coords"])
        titles = compute_titles(r, ctx, nc=n)
        if titles:
            r["titles"] = titles
            attached += 1
        else:
            r.pop("titles", None)
    logger.info("Titles attached for %d active records", attached)


def load_manhole_titles_json(dataset_dir: str) -> Tuple[Dict[str, Dict[str, Any]], List[Dict]]:
    """Load dataset/manhole_titles.json.

    Returns (manholes_by_id, city_links_list).
    manholes_by_id: {"404": {"building": ..., "tags": [...], ...}, ...}
    city_links_list: [{"prefecture": ..., "city": ..., "url": ...}, ...]
    """
    path = os.path.join(dataset_dir, 'manhole_titles.json')
    if not os.path.exists(path):
        print(f"Warning: {path} not found")
        return {}, []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            master = json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load {path}: {e}")
        return {}, []

    manholes: Dict[str, Dict[str, Any]] = {
        str(rid): entry
        for rid, entry in master.get('manholes', {}).items()
        if isinstance(entry, dict)
    }
    city_links: List[Dict] = master.get('city_links', [])
    return manholes, city_links


def build_city_url_index(city_links: List[Dict]) -> Dict[Tuple[str, str], str]:
    """Build (prefecture, normalized_city) -> url index from city_links.

    For each entry indexes both the original name and the suffix-stripped form
    (e.g. "指宿市" → also "指宿") so ndjson city values match.
    Uses re.sub to strip exactly one trailing suffix character, avoiding
    over-stripping of names like "四日市市" (would wrongly become "四日").
    """
    idx: Dict[Tuple[str, str], str] = {}
    for entry in city_links:
        pref = (entry.get('prefecture') or '').strip()
        city = (entry.get('city') or '').strip()
        url = (entry.get('url') or '').strip()
        if not (pref and city and url):
            continue
        idx[(pref, city)] = url
        stripped = re.sub(r'[市区町村]$', '', city)
        if stripped != city:
            idx[(pref, stripped)] = url
    return idx


def lookup_city_url(city_url_idx: Dict[Tuple[str, str], str], pref: str, city: str) -> str:
    """Resolve city_url for a record, with ward-level and prefecture fallbacks.

    Lookup order:
      1. Exact city match (e.g. "指宿" or "指宿市")
      2. Parent designated-city match for ward-level values
         (e.g. "名古屋市中区" → try "名古屋市")
      3. Prefecture-wide fallback ("（県全体案内）")
    """
    url = city_url_idx.get((pref, city), '')
    if url:
        return url
    # Ward-level: "名古屋市中区" → parent "名古屋市"
    m = re.match(r'(.+市)(.+[区])$', city)
    if m:
        url = city_url_idx.get((pref, m.group(1)), '')
        if url:
            return url
    return city_url_idx.get((pref, '（県全体案内）'), '')


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
    _set_value('prefecture', entry.get('prefecture'))
    _set_value('city', entry.get('city'))
    _set_value('place_detail', entry.get('place_detail'), allow_placeholder=True)
    _set_value('landmark', entry.get('landmark'), allow_placeholder=True)
    _set_value('access', entry.get('access'), allow_placeholder=True)

    best_address = entry.get('address_norm') or entry.get('address_raw')
    _set_value('address', best_address)

    _set_list('tags', entry.get('tags'))

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
    # "ローカルActs北海道ページへ" のような都道府県遷移リンクは除外する
    pokemons: List[str] = []
    for a in soup.select("a[href]"):
        txt = a.get_text(strip=True)
        if not txt or "ローカルActs" in txt:
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
    
    # Detect prefecture_site_url from link text
    prefecture_site_url = ""
    is_prefecture_site = False
    for a in soup.select("a[href]"):
        txt = a.get_text(strip=True)
        if "ローカルActs" in txt and "ページへ" in txt:
            href = a.get("href", "")
            if href and "/municipality/" in href:
                prefecture_site_url = href
                is_prefecture_site = True
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
        "prefecture_site_url": prefecture_site_url,
        # extended schema (for consistency with incremental updater)
        "first_seen": now_iso,
        "added_at": now_iso,  # alias for first_seen used by web UI
        "last_updated": now_iso,  # unified update timestamp
        "status": "active",
        "is_prefecture_site": is_prefecture_site
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
    title_data, city_links = load_manhole_titles_json(dataset_dir)
    city_url_idx = build_city_url_index(city_links)
    logger.info("Loaded %d manholes, %d city_links from manhole_titles.json", len(title_data), len(city_links))

    existing = load_existing(args.out)
    by_id: Dict[str, Dict] = {r['id']: r for r in existing if 'id' in r}

    # Ensure extended fields exist & merge static metadata before diffing.
    # Metadata changes (tags, building, city_url …) do NOT bump last_updated.
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
        for _f in ('parking', 'nearby_spots', 'source_urls', 'address_raw', 'address_norm'):
            r.pop(_f, None)
        if apply_title_metadata(r, title_data):
            changed.setdefault(r['id'], {})['title_metadata'] = True
        # Always sync city_url from city_links (source of truth, no last_updated bump)
        pref = r.get('prefecture', '')
        city = r.get('city', '')
        url = lookup_city_url(city_url_idx, pref, city)
        if url and r.get('city_url') != url:
            r['city_url'] = url

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
            # Sync city_url from city_links for new records
            pref = parsed.get('prefecture', '')
            city = parsed.get('city', '')
            url = lookup_city_url(city_url_idx, pref, city)
            if url:
                parsed['city_url'] = url

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

    # Compute titles for all records and store in pokefuta.ndjson
    _compute_and_attach_titles(all_records, dataset_dir, logger)

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
