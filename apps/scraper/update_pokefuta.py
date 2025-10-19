#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Incremental Pokefuta updater.

機能:
  * 既存の `pokefuta.ndjson` (または JSON array) を読み込み現在のマンホール一覧を再取得
  * 削除されたマンホール (HTTP 404 / ページ構造消失) を検出
  * 新規マンホール (まだファイルに存在しないIDでアクセス可能) を検出
  * 変更差分 (タイトル / 座標 / ポケモンなどスキーマフィールドの変化) を検出
  * 結果を: `pokefuta.ndjson` を更新し、変更サマリを `CHANGELOG.md` に追記
  * GitHub Actions 上で動作し、変更があれば exit 0 で終了 (ワークフロー側が自動コミット + PR)

スキーマ拡張:
  旧: { id, title, title_en, title_zh, prefecture, city, address, city_url, lat, lng, pokemons, pokemons_en, pokemons_zh, detail_url, prefecture_site_url }
  新: 旧 + { last_seen (ISO8601), first_seen (ISO8601), status }
     status: "active" | "deleted" (削除検知後も履歴維持)

使い方:
  python update_pokefuta.py --out pokefuta.ndjson --scan-max 1500

GitHub Actions 用想定引数:
  --out pokefuta.ndjson --scan-max 2000 --dataset-dir dataset --log-level INFO --write-mode ndjson

差分定義:
  * 新規: status が付与されていない ID が fetch 成功
  * 削除: 既存 status=active だった ID が 404 または座標抽出失敗
  * 変更: 同一 ID で任意フィールド値が変化 (配列は集合比較)

終了コード:
  0: 正常終了 (差分ある/なし問わず)
  2: 異常終了 (例外)
"""
import argparse, json, logging, os, re, signal, sys, time, tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests

# Reuse constants from scraper (duplicated minimal subset to avoid import side-effects)
DEFAULT_BASE = "https://local.pokemon.jp/manhole/"
HEADERS = {"User-Agent": "pokefuta-tracker-updater (+https://github.com/yourname/pokefuta-tracker)"}
HEADERS_EN = {"User-Agent": HEADERS["User-Agent"], "Accept-Language": "en-US,en;q=0.9"}
REQ_TIMEOUT = 15
SLEEP_SEC = 0.4
RETRY = 3

# --- logging

def setup_logger(level: str = "INFO") -> logging.Logger:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=lvl, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    return logging.getLogger("pokefuta-updater")

# --- file io helpers

def read_existing(path: str, logger: logging.Logger) -> List[Dict]:
    if not os.path.exists(path):
        logger.info("Existing file %s not found; starting with empty dataset", path)
        return []
    items: List[Dict] = []
    with open(path, 'r', encoding='utf-8') as f:
        first = f.read(1)
        f.seek(0)
        if first == '[':
            # JSON array
            try:
                items = json.load(f)
            except Exception as e:
                logger.error("Failed to load JSON array %s: %s", path, e)
        else:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    continue
    logger.info("Loaded %d existing records", len(items))
    return items


def atomic_write_ndjson(path: str, records: List[Dict]):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=d, encoding="utf-8") as tmp:
        for rec in records:
            tmp.write(json.dumps(rec, ensure_ascii=False) + "\n")
        tmp.flush(); os.fsync(tmp.fileno())
        tmp_path = tmp.name
    os.replace(tmp_path, path)

# --- HTTP

def fetch(url: str, logger: logging.Logger, headers: Dict = None) -> requests.Response:
    if headers is None:
        headers = HEADERS
    last = None
    for i in range(RETRY):
        try:
            r = requests.get(url, headers=headers, timeout=REQ_TIMEOUT)
            if r.status_code == 404:
                return r
            r.raise_for_status()
            return r
        except Exception as e:
            last = e
            logger.warning("GET failed (%s) retry=%d err=%s", url, i+1, e)
            time.sleep(1.0 * (i+1))
    raise RuntimeError(f"Failed to fetch {url}: {last}")

# --- parsing (simplified; aligns with scrape_pokefuta)

def parse_detail(detail_url: str, html: str) -> Optional[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    lat = lng = None
    for a in soup.select('a[href*="maps.google"]'):
        href = a.get('href','')
        m = re.search(r'q=([+-]?\d+(?:\.\d+)?),([+-]?\d+(?:\.\d+)?)', href)
        if m:
            lat = float(m.group(1)); lng = float(m.group(2)); break
    if lat is None or lng is None:
        return None
    h = soup.find(["h1","h2"])
    title = h.get_text(strip=True) if h and h.get_text(strip=True) else ""
    pokemons: List[str] = []
    for a in soup.select('a[href]'):
        t = a.get_text(strip=True)
        if t and ("図鑑" in t or "ポケモン" in t or "Pokédex" in t):
            name = re.sub(r'(図鑑|ポケモン|Pokédex)', '', t).strip()
            if name:
                pokemons.append(name)
    m = re.search(r"/desc/(\d+)/?", detail_url)
    pid = m.group(1) if m else ""
    return {
        "id": pid,
        "title": title,
        "lat": lat,
        "lng": lng,
        "pokemons": sorted(set(pokemons)),
        "detail_url": detail_url,
    }

# --- diff logic

def diff_record(old: Dict, new: Dict) -> Dict:
    changes = {}
    for k in ["title","lat","lng","pokemons"]:
        old_v = old.get(k)
        new_v = new.get(k)
        if k == "pokemons":
            old_set = set(old_v or [])
            new_set = set(new_v or [])
            if old_set != new_set:
                changes[k] = {"old": sorted(old_set), "new": sorted(new_set)}
        else:
            if old_v != new_v:
                changes[k] = {"old": old_v, "new": new_v}
    return changes

# --- main update process

def build_detail_url(base_root: str, i: int) -> str:
    base_root = base_root.rstrip('/')
    if not base_root.endswith('/manhole'):
        base_root = re.sub(r'/manhole/.*$', '/manhole', base_root)
        if not base_root.endswith('/manhole'):
            base_root += '/manhole'
    return f"{base_root}/desc/{i}/?is_modal=1"


def now_iso() -> str:
    """Return RFC3339/ISO8601 UTC timestamp (second precision) compatible with JS Date."""
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default=DEFAULT_BASE, help='Base top page URL')
    parser.add_argument('--out', default='pokefuta.ndjson', help='Primary NDJSON output path')
    parser.add_argument('--copy-to', default='', help='Optional mirror path (e.g. docs/pokefuta.ndjson)')
    parser.add_argument('--scan-max', type=int, default=1500, help='Max ID to scan')
    parser.add_argument('--log-level', default='INFO', help='Log level')
    parser.add_argument('--sleep', type=float, default=SLEEP_SEC, help='Sleep seconds between requests')
    parser.add_argument('--limit-new', type=int, default=0, help='Stop after discovering N new records (safety)')
    args = parser.parse_args()

    logger = setup_logger(args.log_level)
    sleep_sec = max(0.2, args.sleep)

    existing = read_existing(args.out, logger)
    by_id: Dict[str, Dict] = {r['id']: r for r in existing if 'id' in r}

    # Ensure extended fields exist & migrate legacy timestamps
    for r in existing:
        r.setdefault('first_seen', now_iso())
        r.setdefault('status', 'active')
        r.setdefault('added_at', r.get('first_seen'))
        if 'last_updated' not in r:
            legacy = r.get('last_seen') or r.get('source_last_checked') or r.get('first_seen')
            r['last_updated'] = legacy
        # Remove deprecated fields if present
        if 'last_seen' in r:
            r.pop('last_seen', None)
        if 'source_last_checked' in r:
            r.pop('source_last_checked', None)

    new_records: List[Dict] = []
    deleted_ids: List[str] = []
    changed: Dict[str, Dict] = {}

    last_existing_id = 0
    if by_id:
        try:
            last_existing_id = max(int(i) for i in by_id.keys() if i.isdigit())
        except ValueError:
            last_existing_id = 0

    logger.info("Starting scan up to %d (current max existing id=%d)", args.scan_max, last_existing_id)

    try:
        for i in range(1, args.scan_max + 1):
            detail_url = build_detail_url(args.base, i)
            try:
                r = fetch(detail_url, logger)
            except Exception as e:
                logger.warning("Fetch error id=%d: %s", i, e)
                continue

            if r.status_code == 404:
                # Mark deletion if previously active
                if str(i) in by_id and by_id[str(i)].get('status') == 'active':
                    by_id[str(i)]['status'] = 'deleted'
                    by_id[str(i)]['last_updated'] = now_iso()
                    changed[str(i)] = {'status': {'old': 'active', 'new': 'deleted'}}
                    deleted_ids.append(str(i))
                time.sleep(sleep_sec)
                continue

            parsed = parse_detail(detail_url, r.text)
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
                    d = diff_record(old, parsed)
                    if d:
                        logger.info("CHANGED id=%s fields=%s", pid, ','.join(d.keys()))
                        old.update({k: parsed[k] for k in ['title','lat','lng','pokemons']})
                        old['last_updated'] = now_ts
                        changed[pid] = d if pid not in changed else {**changed[pid], **d}
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
    if args.copy_to:
        try:
            # Mirror only active records for web consumption (hide deleted)
            active_records = [r for r in all_records if r.get('status') == 'active']
            atomic_write_ndjson(args.copy_to, active_records)
            logger.info("Mirrored ACTIVE dataset (%d) to %s", len(active_records), args.copy_to)
        except Exception as e:
            logger.error("Failed to mirror dataset to %s: %s", args.copy_to, e)

    # Changelog
    if new_records or deleted_ids or changed:
        ts = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        lines = [f"\n## Update {ts}"]
        if new_records:
            lines.append(f"- New ({len(new_records)}): " + ', '.join(r['id'] for r in new_records))
        if deleted_ids:
            lines.append(f"- Deleted ({len(deleted_ids)}): " + ', '.join(deleted_ids))
        # changed (excluding pure status already listed deleted)
        changed_non_status = {cid:chg for cid, chg in changed.items() if set(chg.keys()) != {'status'} or chg['status']['new']=='active'}
        if changed_non_status:
            for cid, chg in changed_non_status.items():
                parts = []
                for field, info in chg.items():
                    if field == 'status':
                        continue
                    parts.append(f"{field}")
                if parts:
                    lines.append(f"- Changed id={cid}: fields=" + ','.join(parts))
        try:
            with open('CHANGELOG.md','a',encoding='utf-8') as cf:
                cf.write('\n'.join(lines) + '\n')
        except Exception as e:
            logger.error("Failed to append CHANGELOG: %s", e)

    # Summary for CI output
    summary = {
        'new': [r['id'] for r in new_records],
        'deleted': deleted_ids,
        'changed': list(changed.keys())
    }
    print("::group::pokefuta-update-summary")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("::endgroup::")

    # If no changes, still exit 0 (workflow will decide to skip PR)
    sys.exit(0)

if __name__ == '__main__':
    main()
