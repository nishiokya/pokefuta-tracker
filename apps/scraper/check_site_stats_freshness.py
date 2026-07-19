#!/usr/bin/env python3
"""Fail when pokefuta.com serves stale site statistics."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.request import Request, urlopen

UPSTREAM_URL = "https://data.pokefuta.com/api/site-stats.json"
SITE_URL = "https://pokefuta.com/api/site-stats"
TIMEOUT = 30
STAT_KEYS = (
    "manholes",
    "manholes_with_photos",
    "posts",
    "public_posts",
    "private_posts",
)


def fetch_json(url: str) -> tuple[dict[str, Any], dict[str, str]]:
    request = Request(url, headers={"User-Agent": "pokefuta-stats-monitor/1.0"})
    with urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
        payload = json.load(response)
        headers = {key.lower(): value for key, value in response.headers.items()}
    if not isinstance(payload, dict):
        raise ValueError(f"{url} did not return a JSON object")
    return payload, headers


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("generated_at is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("generated_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate(
    upstream: dict[str, Any],
    site: dict[str, Any],
    site_headers: dict[str, str],
    *,
    now: datetime,
    max_age: timedelta,
) -> list[str]:
    errors: list[str] = []
    try:
        generated_at = parse_timestamp(site.get("generated_at"))
        if now - generated_at > max_age:
            errors.append(
                f"site generated_at is stale: {generated_at.isoformat()} "
                f"(maximum age: {max_age})"
            )
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))

    for key in STAT_KEYS:
        if upstream.get(key) != site.get(key):
            errors.append(
                f"{key} differs: upstream={upstream.get(key)!r}, site={site.get(key)!r}"
            )

    if site_headers.get("x-nextjs-cache", "").upper() == "HIT":
        errors.append("x-nextjs-cache: HIT indicates that the route was statically cached")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-url", default=UPSTREAM_URL)
    parser.add_argument("--site-url", default=SITE_URL)
    parser.add_argument("--max-age-hours", type=float, default=30)
    # 総待ち時間はワークフローの timeout-minutes 内に収めること（現状 3回 × 240秒 = 8分）
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--retry-seconds", type=int, default=240)
    args = parser.parse_args()

    for attempt in range(1, args.attempts + 1):
        try:
            upstream, _ = fetch_json(args.upstream_url)
            site, site_headers = fetch_json(args.site_url)
            errors = validate(
                upstream,
                site,
                site_headers,
                now=datetime.now(timezone.utc),
                max_age=timedelta(hours=args.max_age_hours),
            )
        except Exception as exc:  # Network and malformed responses must fail the monitor.
            errors = [f"request failed: {exc}"]

        if not errors:
            print("Site statistics are fresh and match the upstream snapshot.")
            return 0
        print(f"Attempt {attempt}/{args.attempts}: {'; '.join(errors)}", file=sys.stderr)
        if attempt < args.attempts:
            time.sleep(args.retry_seconds)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
