#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prefecture-based manhole URL cleaner

This script:
1. Extracts prefecture site URLs from pokemons field (e.g., "ローカルActs岩手県ページへ")
2. Moves them to prefecture_site_url field
3. Adds is_prefecture_site flag to track if manhole data comes from prefecture sites
4. Cleans pokemons list to contain only actual pokemon names
"""
import argparse
import json
import logging
import os
import re
import sys
import tempfile
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Constants
PREFECTURE_PATTERN = r'ローカルActs([^\s]*)(?:県|府|道|都)?ページへ'
PREFECTURES = [
    '北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県',
    '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
    '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県',
    '岐阜県', '愛知県', '三重県', '滋賀県', '京都府', '大阪府', '兵庫県',
    '奈良県', '和歌山県', '鳥取県', '島根県', '岡山県', '広島県', '山口県',
    '徳島県', '香川県', '愛媛県', '高知県', '福岡県', '佐賀県', '長崎県',
    '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県'
]

def setup_logger(level: str = "INFO") -> logging.Logger:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=lvl, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    return logging.getLogger("clean-prefecture-urls")


def extract_prefecture_url(pokemons: List[str]) -> Tuple[Optional[str], List[str], bool]:
    """
    Extract prefecture site URL from pokemons list.
    Returns: (prefecture_url, cleaned_pokemons, is_prefecture_site)
    """
    prefecture_url = None
    is_prefecture_site = False
    cleaned_pokemons = []
    
    for pokemon in pokemons:
        if isinstance(pokemon, str):
            match = re.search(PREFECTURE_PATTERN, pokemon)
            if match:
                prefecture_name = match.group(1)
                # Construct the prefecture name (add 県/府/道/都 if not already included)
                if not any(pref in pokemon for pref in PREFECTURES):
                    # Try to match the prefecture name
                    for pref in PREFECTURES:
                        if pref.replace('県', '').replace('府', '').replace('道', '').replace('都', '') in prefecture_name:
                            prefecture_url = pokemon
                            is_prefecture_site = True
                            break
                    if not prefecture_url:
                        prefecture_url = pokemon
                        is_prefecture_site = True
                else:
                    prefecture_url = pokemon
                    is_prefecture_site = True
            else:
                cleaned_pokemons.append(pokemon)
        else:
            cleaned_pokemons.append(pokemon)
    
    return prefecture_url, cleaned_pokemons, is_prefecture_site


def clean_records(input_path: str, output_path: str, logger: logging.Logger) -> Tuple[int, int, int]:
    """
    Clean records:
    - Extract prefecture URLs from pokemons field
    - Add is_prefecture_site flag
    - Move URLs to prefecture_site_url
    
    Returns: (cleaned_count, failed_count, unchanged_count)
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
    
    cleaned_count = 0
    unchanged_count = 0
    failed_count = 0
    
    for i, record in enumerate(records):
        try:
            record_id = record.get('id', f'unknown-{i}')
            
            # Initialize fields if not present
            if 'is_prefecture_site' not in record:
                record['is_prefecture_site'] = False
            
            pokemons = record.get('pokemons', [])
            if not isinstance(pokemons, list):
                pokemons = [pokemons] if pokemons else []
            
            # Extract prefecture URL
            pref_url, cleaned_pokemons, is_pref = extract_prefecture_url(pokemons)
            
            if pref_url:
                # Update record
                record['pokemons'] = cleaned_pokemons
                record['is_prefecture_site'] = True
                
                # Store the prefecture URL pattern (for reference)
                if 'prefecture_site_url' not in record or not record['prefecture_site_url']:
                    record['prefecture_site_url'] = pref_url
                
                cleaned_count += 1
                logger.info(f"ID {record_id}: Extracted prefecture URL: {pref_url}")
                logger.info(f"  - Cleaned pokemons: {cleaned_pokemons}")
            else:
                unchanged_count += 1
                logger.debug(f"ID {record_id}: No prefecture URL found")
        
        except Exception as e:
            logger.error(f"Error processing record {i}: {e}")
            failed_count += 1
    
    # Write output
    logger.info(f"Writing cleaned records to {output_path}")
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
        return cleaned_count, failed_count, unchanged_count
    
    return cleaned_count, failed_count, unchanged_count


def main():
    parser = argparse.ArgumentParser(description="Clean prefecture-based manhole URLs from pokemons field")
    parser.add_argument("--input", default="pokefuta.ndjson", help="Input NDJSON file")
    parser.add_argument("--output", default="pokefuta_cleaned.ndjson", help="Output NDJSON file")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    
    args = parser.parse_args()
    logger = setup_logger(args.log_level)
    
    if not os.path.exists(args.input):
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)
    
    logger.info(f"Starting prefecture URL cleaning")
    logger.info(f"Input: {args.input}")
    logger.info(f"Output: {args.output}")
    
    try:
        cleaned, failed, unchanged = clean_records(args.input, args.output, logger)
        logger.info(f"✓ Cleaning complete:")
        logger.info(f"  - Cleaned: {cleaned}")
        logger.info(f"  - Unchanged: {unchanged}")
        logger.info(f"  - Failed: {failed}")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(2)


if __name__ == '__main__':
    main()
