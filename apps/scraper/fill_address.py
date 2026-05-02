#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fill missing address fields in pokefuta.ndjson (one-off utility).

Usage:
  python apps/scraper/fill_address.py --in pokefuta.ndjson --out pokefuta.ndjson
  python apps/scraper/fill_address.py --in pokefuta.ndjson --out pokefuta_filled.ndjson
"""
from __future__ import annotations
import argparse, json, logging, os, re, tempfile, time
from typing import Dict, List

import requests
from bs4 import BeautifulSoup
from lxml import html as lxml_html

HEADERS = {"User-Agent": "pokefuta-address-filler (+https://github.com/nishiokya/pokefuta-tracker)"}
REQ_TIMEOUT = 15
RETRY = 3
DEFAULT_SLEEP = 0.5


def setup_logger(level: str = "INFO") -> logging.Logger:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=lvl, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    return logging.getLogger("pokefuta-address-fill")


def fetch(url: str, logger: logging.Logger) -> str | None:
    last_err = None
    for i in range(RETRY):
        try:
            r = requests.get(url, headers=HEADERS, timeout=REQ_TIMEOUT)
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


def _clean_addr(s: str) -> str:
    s = re.sub(r"^(住所|所在地|設置場所|設置地点|設置住所)[：:]\s*", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def extract_address(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    def _extract_address_from_xpath() -> str:
        try:
            tree = lxml_html.fromstring(html)
        except Exception:
            return ""

        label_words = ["住所", "所在地", "設置場所", "設置地点", "設置住所"]

        # 1) dl / table のラベル-値構造
        for label in label_words:
            xpath_candidates = [
                f"//dt[starts-with(normalize-space(.), '{label}')]/following-sibling::dd[1]",
                f"//th[starts-with(normalize-space(.), '{label}')]/following-sibling::td[1]",
                f"//td[starts-with(normalize-space(.), '{label}')]/following-sibling::td[1]",
            ]
            for xp in xpath_candidates:
                nodes = tree.xpath(xp)
                for n in nodes:
                    text = " ".join(n.itertext()).strip()
                    if text:
                        return _clean_addr(text)

        # 2) ラベルと住所が同一ノードにある場合
        for label in label_words:
            nodes = tree.xpath(
                f"//*[contains(normalize-space(.), '{label}')][not(self::script) and not(self::style)]"
            )
            for n in nodes:
                text = " ".join(n.itertext()).strip()
                m = re.search(r"(住所|所在地|設置場所|設置地点|設置住所)[：:]\s*(.+)", text)
                if m and m.group(2).strip():
                    return _clean_addr(m.group(0))

        # 3) class / id に address を含む要素
        nodes = tree.xpath(
            "//*[contains(translate(@class,'ADDRESS','address'),'address') or "
            "contains(translate(@id,'ADDRESS','address'),'address')]"
        )
        for n in nodes:
            text = " ".join(n.itertext()).strip()
            if text and re.search(r"(?:県|府|道|都).*(?:市|区|町|村)", text):
                return _clean_addr(text)

        return ""

    def _extract_address_from_jsonld() -> str:
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.get_text() or "")
            except Exception:
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                addr = item.get("address")
                if isinstance(addr, str) and addr.strip():
                    return _clean_addr(addr)
                if isinstance(addr, dict):
                    parts = [
                        addr.get("postalCode"),
                        addr.get("addressRegion"),
                        addr.get("addressLocality"),
                        addr.get("streetAddress"),
                    ]
                    joined = "".join([p for p in parts if p])
                    if joined.strip():
                        return _clean_addr(joined)
        return ""

    # 1) JSON-LD
    address = _extract_address_from_jsonld()

    # 2) XPath でラベル構造を探索
    if not address:
        address = _extract_address_from_xpath()

    # 3) ラベル付き項目（BeautifulSoup）
    if not address:
        label_patterns = ["住所", "所在地", "設置場所", "設置地点", "設置住所"]
        label_re = re.compile("|".join(label_patterns))
        for node in soup.find_all(string=label_re):
            if not node or not node.parent:
                continue
            parent = node.parent
            text = parent.get_text(" ", strip=True)
            m = re.search(r"(住所|所在地|設置場所|設置地点|設置住所)[：:]\s*(.+)", text)
            if m and m.group(2).strip():
                return _clean_addr(m.group(0))
            if parent.name in ["dt", "th"]:
                sib = parent.find_next_sibling(["dd", "td"])
                if sib and sib.get_text(strip=True):
                    return _clean_addr(sib.get_text(" ", strip=True))

    # 4) フォールバック
    text_content = soup.get_text()
    address_patterns = [
        r'([^。\n]*(?:県|府|道|都)[^。\n]*(?:市|区|町|村)[^。\n]*(?:\d+[-−‐]\d+[-−‐]\d+|\d+丁目|\d+番地)[^。\n]*)',
        r'([^。\n]*(?:県|府|道|都)[^。\n]*(?:市|区|町|村)[^。\n]{0,20})',
        r'([^。\n]*(?:市|区|町|村)[^。\n]*(?:\d+[-−‐]\d+[-−‐]\d+|\d+丁目|\d+番地)[^。\n]*)',
    ]
    candidates: List[str] = []
    for pattern in address_patterns:
        candidates.extend(re.findall(pattern, text_content))
    if candidates:
        candidates = [c.strip() for c in candidates if c.strip()]
        with_digits = [c for c in candidates if re.search(r"\d", c)]
        picked = max(with_digits or candidates, key=len)
        return _clean_addr(picked)
    return ""


def load_ndjson(path: str) -> List[Dict]:
    records: List[Dict] = []
    with open(path, "r", encoding="utf-8") as f:
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
    return records


def atomic_write_ndjson(path: str, rows: List[Dict]):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=d, encoding="utf-8") as tmp:
        for r in rows:
            tmp.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.flush(); os.fsync(tmp.fileno())
        p = tmp.name
    os.replace(p, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_path", required=True, help="Input ndjson path")
    parser.add_argument("--out", dest="out_path", required=True, help="Output ndjson path")
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP, help="Sleep seconds between requests")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N successful updates")
    args = parser.parse_args()

    logger = setup_logger(args.log_level)
    sleep_sec = max(0.1, args.sleep)

    records = load_ndjson(args.in_path)
    logger.info("Loaded records=%d", len(records))

    updated = 0
    for rec in records:
        if args.limit and updated >= args.limit:
            break
        if rec.get("address"):
            continue
        url = rec.get("detail_url")
        if not url:
            continue
        html = fetch(url, logger)
        if not html:
            time.sleep(sleep_sec)
            continue
        addr = extract_address(html)
        if addr:
            rec["address"] = addr
            updated += 1
        time.sleep(sleep_sec)

    atomic_write_ndjson(args.out_path, records)
    logger.info("DONE updated=%d out=%s", updated, args.out_path)


if __name__ == "__main__":
    main()
