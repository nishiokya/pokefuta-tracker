#!/usr/bin/env python3
"""Fail when production files contain loopback URLs."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LOOPBACK_URL = re.compile(
    rb"(?:https?|wss?)://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])"
    # ホスト名の直後は「URLの区切り」でなければならない。行末（$）・終端記号・
    # クエリ(?)・フラグメント(#) を含めないと、ポートもパスも無い
    # `http://localhost` や `http://localhost?api=1` を取りこぼす。
    # 逆に localhost.example.com のような別ホストを誤検知しないよう、
    # 区切り文字以外が続く場合はマッチさせない。
    # 末尾の区切り記号は URL に含めない（`foo(http://localhost);` を
    # `http://localhost);` と報告しないため）。検出可否には影響しない。
    rb"(?=[:/?#\s\"'<>)\]},;]|$)(?:[^\s\"'<>)\]},;]*)",
    re.IGNORECASE,
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
            yield path
            continue
        if not path.exists():
            raise FileNotFoundError(path)
        yield from (candidate for candidate in path.rglob("*") if candidate.is_file())


def find_loopback_urls(
    paths: list[Path], exclude: list[str] | None = None
) -> list[tuple[Path, int, str]]:
    findings = []
    exclude = exclude or []
    for path in iter_files(paths):
        if path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if any(path.match(pattern) for pattern in exclude):
            continue
        for line_number, line in enumerate(path.read_bytes().splitlines(), start=1):
            # ミニファイ済みの成果物は1行に複数URLが載るので finditer で全件拾う
            for match in LOOPBACK_URL.finditer(line):
                findings.append(
                    (path, line_number, match.group(0).decode("ascii", errors="replace"))
                )
    return findings


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
