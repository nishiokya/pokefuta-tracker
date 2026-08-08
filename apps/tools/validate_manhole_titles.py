#!/usr/bin/env python3
"""Validate dataset/manhole_titles.json and its tag vocabulary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from validate_location_research import load_validator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = PROJECT_ROOT / "dataset" / "manhole_titles.json"
DEFAULT_SCHEMA = PROJECT_ROOT / "schemas" / "manhole-titles.schema.json"


def validate(path: Path, schema_path: Path = DEFAULT_SCHEMA) -> list[str]:
    validator = load_validator(schema_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    messages = []
    for error in sorted(
        validator.iter_errors(data),
        key=lambda item: list(item.absolute_path),
    ):
        location = ".".join(str(part) for part in error.absolute_path)
        prefix = f"{location}: " if location else ""
        messages.append(f"{prefix}{error.message}")
    return messages


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        messages = validate(args.path, args.schema)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"{args.path}: unable to validate: {exc}", file=sys.stderr)
        return 2

    if messages:
        for message in messages:
            print(f"{args.path}: {message}", file=sys.stderr)
        print(f"{args.path}: {len(messages)} error(s)", file=sys.stderr)
        return 1

    print(f"{args.path}: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
