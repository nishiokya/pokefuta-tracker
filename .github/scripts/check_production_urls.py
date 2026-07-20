#!/usr/bin/env python3
"""Fail when production files contain loopback URLs."""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

URL_CANDIDATE = re.compile(
    rb"(?:https?|wss?)://[^\x00-\x20\"'`<>),;]+", re.IGNORECASE
)

# 本番成果物に焼き込まれ得るデータ・設定ファイルも対象にする。
# ここに無い拡張子は素通りするため、artifact 検査の穴になる。
# .ndjson / .txt は pages-deploy.yml が docs/*.ndjson と robots.txt を
# dist にコピーして公開しているため必須。
SOURCE_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".mjs",
    ".ndjson",
    ".py",
    ".svg",
    ".ts",
    ".txt",
    ".webmanifest",
    ".xml",
}


def iter_files(paths: list[Path]):
    for path in paths:
        if path.is_file():
            if path.suffix.lower() in SOURCE_SUFFIXES:
                yield path
            continue
        if not path.exists():
            raise FileNotFoundError(path)
        for root, _, filenames in os.walk(path):
            yield from (
                Path(root) / filename
                for filename in filenames
                if Path(filename).suffix.lower() in SOURCE_SUFFIXES
            )


def normalize_special_url_whitespace(data: bytes) -> tuple[bytes, list[int]]:
    """Remove ASCII tab/newline characters as the WHATWG URL parser does."""
    normalized = bytearray()
    line_numbers = []
    line_number = 1
    for byte in data:
        if byte not in b"\t\r\n":
            normalized.append(byte)
            line_numbers.append(line_number)
        if byte == ord("\n"):
            line_number += 1
    return bytes(normalized), line_numbers


def parse_ipv4_number(part: str) -> int | None:
    base = 10
    digits = part
    if part.lower().startswith("0x"):
        base = 16
        digits = part[2:]
    elif len(part) >= 2 and part.startswith("0"):
        base = 8
        digits = part[1:]
    if not digits:
        return 0
    try:
        return int(digits, base)
    except ValueError:
        return None


def parse_whatwg_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """Parse the non-canonical IPv4 forms accepted by browser URL parsers."""
    parts = host.removesuffix(".").split(".")
    if not 1 <= len(parts) <= 4 or any(not part for part in parts):
        return None
    numbers = [parse_ipv4_number(part) for part in parts]
    if any(number is None for number in numbers):
        return None
    values = [number for number in numbers if number is not None]
    if any(number > 255 for number in values[:-1]):
        return None
    if values[-1] >= 256 ** (5 - len(values)):
        return None
    address = sum(
        number * 256 ** (3 - index)
        for index, number in enumerate(values[:-1])
    )
    address += values[-1]
    return ipaddress.IPv4Address(address)


def is_forbidden_host(host: str) -> bool:
    host = unquote(host).lower().removesuffix(".")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = parse_whatwg_ipv4(host)
    return address is not None and (address.is_loopback or address.is_unspecified)


def find_forbidden_urls(data: bytes) -> list[tuple[int, str]]:
    original_line_numbers = []
    line_number = 1
    for byte in data:
        original_line_numbers.append(line_number)
        if byte == ord("\n"):
            line_number += 1
    normalized, normalized_line_numbers = normalize_special_url_whitespace(data)

    findings = []
    seen = set()
    for content, line_numbers in (
        (data, original_line_numbers),
        (normalized, normalized_line_numbers),
    ):
        for match in URL_CANDIDATE.finditer(content):
            url = match.group(0).decode("ascii", errors="replace")
            try:
                # Browsers treat backslashes as path separators in special URLs.
                host = urlsplit(url.replace("\\", "/")).hostname
            except ValueError:
                continue
            finding = (line_numbers[match.start()], url)
            if host and is_forbidden_host(host) and finding not in seen:
                findings.append(finding)
                seen.add(finding)
    return findings


def find_loopback_urls(
    paths: list[Path], exclude: list[str] | None = None
) -> list[tuple[Path, int, str]]:
    findings = []
    exclude = exclude or []
    for path in iter_files(paths):
        if any(path.match(pattern) for pattern in exclude):
            continue
        for line_number, url in find_forbidden_urls(path.read_bytes()):
            findings.append((path, line_number, url))
    return sorted(findings, key=lambda finding: (str(finding[0]), finding[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--exclude", action="append", default=[], help="glob to exclude (repeatable)"
    )
    args = parser.parse_args()

    try:
        findings = find_loopback_urls(args.paths, args.exclude)
    except FileNotFoundError as error:
        parser.error(f"path does not exist: {error}")

    for path, line_number, url in findings:
        print(f"{path}:{line_number}: forbidden production URL: {url}", file=sys.stderr)
    if findings:
        print(f"Found {len(findings)} loopback URL(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
