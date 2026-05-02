#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Address-only updater for pokefuta.ndjson

This script updates only the 'address' field in existing pokefuta records
while preserving all other fields (including added_at, first_seen, etc.)
"""
import argparse
import json
import logging
import os
import re
import sys
import tempfile
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

# Constants
DEFAULT_BASE = "https://local.pokemon.jp/manhole/"
HEADERS = {"User-Agent": "pokefuta-address-updater (+https://github.com/nishiokya/pokefuta-tracker)"}
REQ_TIMEOUT = 15
RETRY = 3
DEFAULT_SLEEP = 0.3

def setup_logger(level: str = "INFO") -> logging.Logger:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=lvl, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    return logging.getLogger("pokefuta-address-updater")


def fetch(url: str, logger: logging.Logger, headers: Dict[str, str]) -> Optional[str]:
    """Fetch URL with retries"""
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
            logger.debug("fetch failed (%s) retry=%d err=%s", url, i + 1, e)
            time.sleep(0.5 * (i + 1))
    logger.warning("giving up %s: %s", url, last_err)
    return None


def extract_address(html: str) -> str:
    """Extract address from HTML using improved patterns"""
    soup = BeautifulSoup(html, "html.parser")
    text_content = soup.get_text()
    
    # Improved address patterns (same as scrape_pokefuta.py)
    address_patterns = [
        # パターン1: 県名 + 市区町村 + (丁目|番地|号|番|複合数字)
        r'([^。\n]*(?:県|府|道|都)[^。\n]*(?:市|区|町|村)[^。\n]*(?:\d+[-−‐]\d+[-−‐]\d+|\d+[-−‐]\d+|\d+丁目|\d+番地|\d+号|\d+番)[^。\n]*)',
        # パターン2: 市区町村 + (丁目|番地|号|番|複合数字)
        r'([^。\n]*(?:市|区|町|村)[^。\n]*(?:\d+[-−‐]\d+[-−‐]\d+|\d+[-−‐]\d+|\d+丁目|\d+番地|\d+号|\d+番)[^。\n]*)',
        # パターン3: 県名 + 市区町村のみ
        r'([^。\n]*(?:県|府|道|都)[^。\n]*(?:市|区|町|村)[^。、\n]*)',
    ]
    
    for pattern in address_patterns:
        matches = re.findall(pattern, text_content)
        if matches:
            address = max(matches, key=len).strip()
            # パターン3の場合は短すぎないか確認
            if len(address) < 4 and pattern == address_patterns[2]:
                continue
            return address
    
    return ""


def update_address_only(input_path: str, output_path: str, logger: logging.Logger) -> tuple:
    """Update address field for existing records"""
    
    # Read existing data
    existing_records = []
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                existing_records.append(json.loads(line))
    
    logger.info(f"Loaded {len(existing_records)} existing records")
    
    updated = 0
    failed = 0
    skipped = 0
    
    for record in existing_records:
        record_id = record.get('id')
        
        # Skip if already has address
        if record.get('address'):
            skipped += 1
            continue
        
        # Try to fetch and extract address
        detail_url = record.get('detail_url')
        if not detail_url:
            logger.warning(f"ID {record_id}: No detail_url")
            failed += 1
            continue
        
        html = fetch(detail_url, logger, HEADERS)
        if not html:
            logger.debug(f"ID {record_id}: Failed to fetch {detail_url}")
            failed += 1
            time.sleep(DEFAULT_SLEEP)
            continue
        
        # Extract address
        address = extract_address(html)
        
        if address:
            record['address'] = address
            updated += 1
            logger.info(f"ID {record_id}: Updated address = '{address}'")
        else:
            logger.debug(f"ID {record_id}: Could not extract address")
            failed += 1
        
        time.sleep(DEFAULT_SLEEP)
    
    # Write output
    d = os.path.dirname(os.path.abspath(output_path)) or "."
    os.makedirs(d, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=d, encoding="utf-8") as tmp:
        for record in existing_records:
            tmp.write(json.dumps(record, ensure_ascii=False) + "\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        p = tmp.name
    os.replace(p, output_path)
    
    logger.info(f"Wrote {len(existing_records)} records to {output_path}")
    logger.info(f"Updated: {updated}, Failed: {failed}, Skipped (already filled): {skipped}")
    
    return updated, failed, skipped


def main():
    parser = argparse.ArgumentParser(description="Update address field only in pokefuta.ndjson")
    parser.add_argument("--input", default="pokefuta.ndjson", help="Input NDJSON file")
    parser.add_argument("--output", default="pokefuta.ndjson", help="Output NDJSON file")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    
    args = parser.parse_args()
    logger = setup_logger(args.log_level)
    
    if not os.path.exists(args.input):
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)
    
    logger.info(f"Starting address-only update")
    logger.info(f"Input: {args.input}")
    logger.info(f"Output: {args.output}")
    
    try:
        updated, failed, skipped = update_address_only(args.input, args.output, logger)
        logger.info(f"✓ Update complete: {updated} updated, {failed} failed, {skipped} already filled")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(2)


if __name__ == '__main__':
    main()
