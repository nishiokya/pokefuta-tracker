#!/usr/bin/env python3
"""Validate each record in a Pokéfuta location research NDJSON file."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from jsonschema import Draft202012Validator, FormatChecker, RefResolver


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = PROJECT_ROOT / "schemas" / "pokefuta-location-research.schema.json"
TAG_SCHEMA = PROJECT_ROOT / "schemas" / "manhole-tags.schema.json"


@dataclass(frozen=True)
class ValidationIssue:
    line: int
    message: str
    column: int | None = None

    def format(self, path: Path) -> str:
        location = f"{path}:{self.line}"
        if self.column is not None:
            location += f":{self.column}"
        return f"{location}: {self.message}"


def load_validator(schema_path: Path = DEFAULT_SCHEMA) -> Draft202012Validator:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    tag_schema = json.loads(TAG_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator.check_schema(tag_schema)
    resolver = RefResolver.from_schema(
        schema,
        store={
            tag_schema["$id"]: tag_schema,
            "manhole-tags.schema.json": tag_schema,
        },
    )
    return Draft202012Validator(
        schema,
        resolver=resolver,
        format_checker=FormatChecker(),
    )


def _schema_message(error) -> str:
    path = ".".join(str(part) for part in error.absolute_path)
    prefix = f"{path}: " if path else ""
    return f"{prefix}{error.message}"


CANDIDATE_SCALAR_FIELDS = ("building", "place_detail", "landmark")


def _confidence_messages(record: dict) -> list[str]:
    """Cross-field checks that JSON Schema cannot express.

    Enforces the documented rule that the top-level ``confidence`` equals the
    minimum confidence of every adopted field, and that each candidate field
    carries a matching ``field_confidence`` entry. Without this, an ``accept``
    record can pass with ``confidence: 3`` while a field is only ``0``–``2``.
    """
    candidate = record.get("candidate")
    field_confidence = record.get("field_confidence")
    confidence = record.get("confidence")
    if not isinstance(candidate, dict) or not isinstance(field_confidence, dict):
        return []

    messages: list[str] = []
    leaves: list[int] = []

    for field in CANDIDATE_SCALAR_FIELDS:
        if field not in candidate:
            continue
        value = field_confidence.get(field)
        if isinstance(value, int):
            leaves.append(value)
        else:
            messages.append(
                f"field_confidence: candidate '{field}' has no confidence entry"
            )

    if "tags" in candidate:
        candidate_tags = set(candidate.get("tags") or [])
        tag_confidence = field_confidence.get("tags")
        tag_confidence = tag_confidence if isinstance(tag_confidence, dict) else {}
        for tag in sorted(candidate_tags - set(tag_confidence)):
            messages.append(
                f"field_confidence.tags: tag '{tag}' has no confidence entry"
            )
        leaves.extend(v for v in tag_confidence.values() if isinstance(v, int))

    if isinstance(confidence, int) and leaves and confidence != min(leaves):
        messages.append(
            f"confidence: {confidence} must equal the minimum field confidence "
            f"{min(leaves)}"
        )

    return messages


def validate_file(
    path: Path,
    validator: Draft202012Validator,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen_ids: dict[str, int] = {}

    with path.open(encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            if not raw_line.strip():
                issues.append(ValidationIssue(line_number, "blank lines are not allowed"))
                continue

            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                issues.append(
                    ValidationIssue(line_number, f"invalid JSON: {exc.msg}", exc.colno)
                )
                continue

            for error in sorted(
                validator.iter_errors(record),
                key=lambda item: list(item.absolute_path),
            ):
                issues.append(ValidationIssue(line_number, _schema_message(error)))

            if isinstance(record, dict):
                for message in _confidence_messages(record):
                    issues.append(ValidationIssue(line_number, message))

            record_id = record.get("id") if isinstance(record, dict) else None
            if not isinstance(record_id, str):
                continue
            if record_id in seen_ids:
                issues.append(
                    ValidationIssue(
                        line_number,
                        f"duplicate id {record_id!r}; first seen on line "
                        f"{seen_ids[record_id]}",
                    )
                )
            else:
                seen_ids[record_id] = line_number

    return issues


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="research NDJSON file to validate")
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help=f"record schema (default: {DEFAULT_SCHEMA})",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        validator = load_validator(args.schema)
        issues = validate_file(args.path, validator)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"{args.path}: unable to validate: {exc}", file=sys.stderr)
        return 2

    if issues:
        for issue in issues:
            print(issue.format(args.path), file=sys.stderr)
        print(f"{args.path}: {len(issues)} error(s)", file=sys.stderr)
        return 1

    print(f"{args.path}: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
