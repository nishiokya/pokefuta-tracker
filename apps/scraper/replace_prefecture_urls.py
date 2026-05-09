#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Replace prefecture site URL text with actual URLs

Converts "ローカルActs{都道府県}ページへ" to actual municipality URLs
"""
import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import datetime
from typing import Dict, Tuple

from prefecture_url_mapping import PREFECTURE_TEXT_TO_URL

def setup_logger(level: str = "INFO") -> logging.Logger:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=lvl, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    return logging.getLogger("replace-prefecture-urls")


def replace_prefecture_urls(input_path: str, output_path: str, logger: logging.Logger) -> Tuple[int, int, int]:
    """
    Replace prefecture URL text with actual URLs.
    
    Returns: (replaced_count, failed_count, unchanged_count)
    """
    logger.info(f"Loading records from {input_path}")
    
    records = []
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
    except Exception as e:
        logger.error(f"Error reading input file: {e}")
        return 0, len(records), 0
    
    logger.info(f"Loaded {len(records)} records")
    
    replaced_count = 0
    unchanged_count = 0
    failed_count = 0
    
    for i, record in enumerate(records):
        try:
            record_id = record.get('id', f'unknown-{i}')
            
            # Skip if not a prefecture site
            if not record.get('is_prefecture_site', False):
                unchanged_count += 1
                continue
            
            prefecture_site_url = record.get('prefecture_site_url', '')
            
            # Check if URL needs to be replaced
            if prefecture_site_url in PREFECTURE_TEXT_TO_URL:
                actual_url = PREFECTURE_TEXT_TO_URL[prefecture_site_url]
                record['prefecture_site_url'] = actual_url
                replaced_count += 1
                logger.info(f"ID {record_id}: Replaced '{prefecture_site_url}' with '{actual_url}'")
            elif prefecture_site_url.startswith('https://'):
                # Already a URL, skip
                unchanged_count += 1
                logger.debug(f"ID {record_id}: Already a URL: {prefecture_site_url}")
            else:
                logger.warning(f"ID {record_id}: Unknown URL format: {prefecture_site_url}")
                failed_count += 1
        
        except Exception as e:
            logger.error(f"Error processing record {i}: {e}")
            failed_count += 1
    
    # Write output
    logger.info(f"Writing replaced records to {output_path}")
    d = os.path.dirname(os.path.abspath(output_path)) or "."
    os.makedirs(d, exist_ok=True)
    
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, dir=d, encoding="utf-8") as tmp:
            for record in records:
                tmp.write(json.dumps(record, ensure_ascii=False) + "\n")
            tmp.flush()
            os.fsync(tmp.fileno())
            p = tmp.name
        os.replace(p, output_path)
        logger.info(f"✓ Wrote {len(records)} records to {output_path}")
    except Exception as e:
        logger.error(f"Error writing output: {e}")
        failed_count += 1
        return replaced_count, failed_count, unchanged_count
    
    return replaced_count, failed_count, unchanged_count


def main():
    parser = argparse.ArgumentParser(description="Replace prefecture site URL text with actual URLs")
    parser.add_argument("--input", default="pokefuta_cleaned.ndjson", help="Input NDJSON file")
    parser.add_argument("--output", default="pokefuta_with_urls.ndjson", help="Output NDJSON file")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    
    args = parser.parse_args()
    logger = setup_logger(args.log_level)
    
    if not os.path.exists(args.input):
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)
    
    logger.info(f"Starting prefecture URL replacement")
    logger.info(f"Input: {args.input}")
    logger.info(f"Output: {args.output}")
    
    try:
        replaced, failed, unchanged = replace_prefecture_urls(args.input, args.output, logger)
        logger.info(f"✓ Replacement complete:")
        logger.info(f"  - Replaced: {replaced}")
        logger.info(f"  - Unchanged: {unchanged}")
        logger.info(f"  - Failed: {failed}")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(2)


if __name__ == '__main__':
    main()
