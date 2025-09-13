#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pokefuta data cleaning and changelog generation script.

Cleans the pokefuta.ndjson file and generates changelog markdown
when IDs are added or removed.
"""
import argparse
import json
import logging
import os
import tempfile
from datetime import datetime
from typing import List, Set, Tuple
import re

def setup_logger(level: str = "INFO") -> logging.Logger:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=lvl, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    return logging.getLogger("pokefuta-cleaner")

def clean_pokemon_names(pokemons: List[str]) -> List[str]:
    """Clean and normalize Pokemon names."""
    cleaned = []
    for pokemon in pokemons:
        # Remove common suffixes and normalize
        clean_name = re.sub(r'(ずかん|図鑑|へ|の|Pokédex)$', '', pokemon.strip())
        clean_name = re.sub(r'(ローカルActs.*ページ|.*県ページ|都道府県.*ページ)', '', clean_name).strip()

        if clean_name and len(clean_name) > 1 and not re.match(r'^(ローカル|Acts|ページ).*', clean_name):
            cleaned.append(clean_name)

    return list(set(cleaned))  # Remove duplicates

def extract_prefecture_from_title(title: str) -> str:
    """Extract prefecture from title."""
    if title and '/' in title:
        prefecture_part = title.split('/')[0].strip()
        if re.match(r'.*[都道府県]$', prefecture_part):
            return prefecture_part
    return ""

def extract_city_from_title(title: str) -> str:
    """Extract city from title."""
    if title and '/' in title:
        parts = title.split('/')
        if len(parts) >= 2:
            return parts[1].strip()
    return ""

def clean_pokefuta_data(input_file: str, output_file: str, logger: logging.Logger) -> Tuple[Set[str], Set[str]]:
    """
    Clean pokefuta data and return old and new ID sets.

    Returns:
        Tuple[Set[str], Set[str]]: (old_ids, new_ids)
    """
    # Read existing IDs if file exists
    old_ids = set()
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        old_ids.add(data['id'])
        except Exception as e:
            logger.warning(f"Could not read existing file {output_file}: {e}")

    # Process new data
    cleaned_data = []
    new_ids = set()

    logger.info(f"Cleaning data from {input_file}")

    with open(input_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue

            try:
                data = json.loads(line)

                # Clean and normalize data
                cleaned_item = {
                    'id': data['id'],
                    'title': data.get('title', ''),
                    'prefecture': extract_prefecture_from_title(data.get('title', '')) or data.get('prefecture', ''),
                    'city': extract_city_from_title(data.get('title', '')),
                    'lat': data['lat'],
                    'lng': data['lng'],
                    'pokemons': clean_pokemon_names(data.get('pokemons', [])),
                    'detail_url': data['detail_url'],
                    'prefecture_site_url': data.get('prefecture_site_url', ''),
                    'source_last_checked': data['source_last_checked']
                }

                cleaned_data.append(cleaned_item)
                new_ids.add(data['id'])

            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error on line {line_num}: {e}")
            except KeyError as e:
                logger.error(f"Missing required field on line {line_num}: {e}")

    # Sort by ID for consistent ordering
    cleaned_data.sort(key=lambda x: int(x['id']))

    # Write cleaned data
    logger.info(f"Writing {len(cleaned_data)} cleaned records to {output_file}")

    with tempfile.NamedTemporaryFile('w', delete=False, dir=os.path.dirname(output_file), encoding='utf-8') as tmp:
        for item in cleaned_data:
            json.dump(item, tmp, ensure_ascii=False, separators=(',', ':'))
            tmp.write('\n')
        tmp.flush()
        os.fsync(tmp.fileno())
        temp_path = tmp.name

    os.replace(temp_path, output_file)

    logger.info(f"Data cleaning complete. Old IDs: {len(old_ids)}, New IDs: {len(new_ids)}")
    return old_ids, new_ids

def generate_change_report(old_ids: Set[str], new_ids: Set[str]) -> Tuple[Set[str], Set[str], str]:
    """Generate change report."""
    added_ids = new_ids - old_ids
    removed_ids = old_ids - new_ids

    report_lines = [
        f"Pokefuta Data Change Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"Total IDs before: {len(old_ids)}",
        f"Total IDs after:  {len(new_ids)}",
        f"Net change:       {len(new_ids) - len(old_ids):+d}",
        ""
    ]

    if added_ids:
        report_lines.extend([
            f"🆕 Added IDs ({len(added_ids)}):",
            "  " + ", ".join(sorted(added_ids, key=int)),
            ""
        ])

    if removed_ids:
        report_lines.extend([
            f"🗑️ Removed IDs ({len(removed_ids)}):",
            "  " + ", ".join(sorted(removed_ids, key=int)),
            ""
        ])

    if not added_ids and not removed_ids:
        report_lines.append("ℹ️ No changes detected.")

    return added_ids, removed_ids, "\n".join(report_lines)

def update_changelog(added_ids: Set[str], removed_ids: Set[str], changelog_path: str, logger: logging.Logger):
    """Update CHANGELOG.md with the changes."""

    if not added_ids and not removed_ids:
        logger.info("No changes detected, skipping changelog update")
        return False

    date_str = datetime.now().strftime('%Y-%m-%d')

    # Create changelog entry
    changelog_entry = [
        f"## [{date_str}] - Automatic Data Update",
        ""
    ]

    if added_ids:
        changelog_entry.extend([
            f"### Added ({len(added_ids)} items)",
            ""
        ])
        sorted_added = sorted(added_ids, key=int)
        for id_chunk in [sorted_added[i:i+20] for i in range(0, len(sorted_added), 20)]:
            changelog_entry.append(f"- IDs: {', '.join(id_chunk)}")
        changelog_entry.append("")

    if removed_ids:
        changelog_entry.extend([
            f"### Removed ({len(removed_ids)} items)",
            ""
        ])
        sorted_removed = sorted(removed_ids, key=int)
        for id_chunk in [sorted_removed[i:i+20] for i in range(0, len(sorted_removed), 20)]:
            changelog_entry.append(f"- IDs: {', '.join(id_chunk)}")
        changelog_entry.append("")

    changelog_entry.extend([
        f"**Total changes:** {len(added_ids) + len(removed_ids)}",
        f"**Net change:** {len(added_ids) - len(removed_ids):+d}",
        "",
        "---",
        ""
    ])

    # Read existing changelog
    existing_content = ""
    if os.path.exists(changelog_path):
        with open(changelog_path, 'r', encoding='utf-8') as f:
            existing_content = f.read()

    # Create new content
    if existing_content:
        # Insert after the first heading
        lines = existing_content.split('\n')
        insert_pos = 1
        for i, line in enumerate(lines):
            if line.startswith('## ') and i > 0:
                insert_pos = i
                break

        new_lines = lines[:insert_pos] + changelog_entry + lines[insert_pos:]
        new_content = '\n'.join(new_lines)
    else:
        # Create new changelog
        header = [
            "# Pokefuta Tracker Changelog",
            "",
            "All notable changes to the pokefuta data will be documented in this file.",
            "",
            "The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).",
            ""
        ]
        new_content = '\n'.join(header + changelog_entry)

    # Write updated changelog
    with open(changelog_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    logger.info(f"Updated changelog: {changelog_path}")
    return True

def create_summary_file(added_ids: Set[str], removed_ids: Set[str], summary_path: str, logger: logging.Logger):
    """Create a summary file for the PR description."""

    if not added_ids and not removed_ids:
        return

    summary = {
        "date": datetime.now().strftime('%Y-%m-%d'),
        "total_changes": len(added_ids) + len(removed_ids),
        "added_count": len(added_ids),
        "removed_count": len(removed_ids),
        "net_change": len(added_ids) - len(removed_ids),
        "added_ids": sorted(list(added_ids), key=int),
        "removed_ids": sorted(list(removed_ids), key=int)
    }

    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info(f"Created summary file: {summary_path}")

def should_create_pr(added_ids: Set[str], removed_ids: Set[str]) -> bool:
    """Determine if a PR should be created based on changes."""
    return bool(added_ids or removed_ids)

def main():
    parser = argparse.ArgumentParser(description="Clean pokefuta data and generate changelog")
    parser.add_argument("--input", default="pokefuta.ndjson", help="Input NDJSON file")
    parser.add_argument("--output", default="pokefuta.ndjson", help="Output NDJSON file")
    parser.add_argument("--changelog", default="../../CHANGELOG.md", help="Changelog file path")
    parser.add_argument("--summary", default="change_summary.json", help="Summary file path")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    parser.add_argument("--no-changelog", action="store_true", help="Skip changelog update")

    args = parser.parse_args()

    logger = setup_logger(args.log_level)

    try:
        # Clean data
        old_ids, new_ids = clean_pokefuta_data(args.input, args.output, logger)

        # Generate change report
        added_ids, removed_ids, report = generate_change_report(old_ids, new_ids)

        logger.info("Change report:")
        logger.info("\n" + report)

        # Update changelog and create summary if changes detected
        if added_ids or removed_ids:
            if not args.no_changelog:
                changelog_updated = update_changelog(added_ids, removed_ids, args.changelog, logger)
                if changelog_updated:
                    logger.info("Changelog updated successfully")

            create_summary_file(added_ids, removed_ids, args.summary, logger)

            # Create a flag file to indicate PR should be created
            with open("create_pr.flag", "w") as f:
                f.write("1")

            logger.info("PR creation flag set")
        else:
            logger.info("No changes detected, skipping changelog and PR creation")

        logger.info("Data cleaning and changelog generation complete")

    except Exception as e:
        logger.error(f"Error during data cleaning: {e}")
        raise

if __name__ == "__main__":
    main()