#!/usr/bin/env python3
"""Import sibling-site manhole photos as local, popup-sized JPEG assets."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import io
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, urlparse, urlunparse

import requests
from PIL import Image, ImageOps


ID_KEYS = (
    "manhole_id",
    "manholeId",
    "pokefuta_id",
    "pokefutaId",
    "id",
)
URL_KEYS = (
    "latest_image_url",
    "latestImageUrl",
    "image_url",
    "imageUrl",
    "photo_url",
    "photoUrl",
    "url",
)


def load_env_file(path: str) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def aws_quote(value: str, safe: str = "") -> str:
    return quote(value, safe=safe)


def signing_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    key_date = hmac.new(("AWS4" + secret_key).encode(), date_stamp.encode(), hashlib.sha256).digest()
    key_region = hmac.new(key_date, region.encode(), hashlib.sha256).digest()
    key_service = hmac.new(key_region, service.encode(), hashlib.sha256).digest()
    return hmac.new(key_service, b"aws4_request", hashlib.sha256).digest()


def build_r2_object_url(endpoint: str, bucket: str, storage_key: str) -> str:
    parsed = urlparse(endpoint)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("R2_ENDPOINT must be an absolute URL")
    host = parsed.netloc
    path_prefix = parsed.path.strip("/")
    if bucket and not host.startswith(f"{bucket}."):
        host = f"{bucket}.{host}"
    object_path = "/".join(part for part in (path_prefix, storage_key.lstrip("/")) if part)
    return urlunparse((parsed.scheme, host, "/" + object_path, "", "", ""))


def presign_r2_get_object(storage_key: str, expires: int = 3600) -> str:
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    endpoint = os.environ.get("R2_ENDPOINT") or os.environ.get("R2_PUBLIC_URL")
    bucket = os.environ.get("R2_BUCKET", "")
    if not access_key or not secret_key or not endpoint:
        raise ValueError("R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, and R2_ENDPOINT are required")

    object_url = build_r2_object_url(endpoint, bucket, storage_key)
    parsed = urlparse(object_url)
    now = dt.datetime.now(dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    region = "auto"
    service = "s3"
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    credential = f"{access_key}/{credential_scope}"
    query_pairs = [
        ("X-Amz-Algorithm", "AWS4-HMAC-SHA256"),
        ("X-Amz-Content-Sha256", "UNSIGNED-PAYLOAD"),
        ("X-Amz-Credential", credential),
        ("X-Amz-Date", amz_date),
        ("X-Amz-Expires", str(expires)),
        ("X-Amz-SignedHeaders", "host"),
        ("x-amz-checksum-mode", "ENABLED"),
        ("x-id", "GetObject"),
    ]
    canonical_query = "&".join(
        f"{aws_quote(key)}={aws_quote(value)}" for key, value in sorted(query_pairs)
    )
    canonical_uri = "/" + "/".join(aws_quote(part) for part in parsed.path.lstrip("/").split("/"))
    canonical_headers = f"host:{parsed.netloc}\n"
    signed_headers = "host"
    payload_hash = "UNSIGNED-PAYLOAD"
    canonical_request = "\n".join([
        "GET",
        canonical_uri,
        canonical_query,
        canonical_headers,
        signed_headers,
        payload_hash,
    ])
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        amz_date,
        credential_scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])
    signature = hmac.new(
        signing_key(secret_key, date_stamp, region, service),
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        "",
        canonical_query + f"&X-Amz-Signature={signature}",
        "",
    ))


def iter_records(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return

    if isinstance(payload, dict):
        for key in ("items", "photos", "data", "records", "manholes"):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        yield item
                return
            if isinstance(value, dict):
                for item_id, item_value in value.items():
                    if isinstance(item_value, dict):
                        yield {"id": item_id, **item_value}
                    elif isinstance(item_value, str):
                        yield {"id": item_id, "url": item_value}
                return
        for key, value in payload.items():
            if isinstance(value, dict):
                item = {"id": key, **value}
                yield item
            elif isinstance(value, str):
                yield {"id": key, "url": value}


def pick_first(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = record.get(key)
        if value:
            return value
    return None


def get_photo_url(record: dict[str, Any]) -> str | None:
    direct = pick_first(record, URL_KEYS)
    if isinstance(direct, str):
        return direct

    for key in ("latest_photo", "latestPhoto", "photo", "image"):
        value = record.get(key)
        if isinstance(value, dict):
            nested = pick_first(value, URL_KEYS)
            if isinstance(nested, str):
                return nested

    for key in ("photos", "images"):
        value = record.get(key)
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                nested = pick_first(first, URL_KEYS)
                if isinstance(nested, str):
                    return nested
    return None


def get_storage_key(record: dict[str, Any]) -> str | None:
    value = record.get("storage_key") or record.get("storageKey") or record.get("key")
    return str(value).lstrip("/") if value else None


def sanitize_id(raw_id: Any) -> str | None:
    text = str(raw_id or "").strip()
    if not text:
        return None
    match = re.search(r"\d+", text)
    return match.group(0) if match else None


def validate_url(raw_url: str) -> str | None:
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return raw_url


def redact_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if not parsed.scheme or not parsed.netloc:
        return "<invalid-url>"
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def crop_to_square(image: Image.Image, size: int) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("RGB")
    width, height = image.size
    crop_size = min(width, height)
    left = (width - crop_size) // 2
    top = (height - crop_size) // 2
    cropped = image.crop((left, top, left + crop_size, top + crop_size))
    return cropped.resize((size, size), Image.Resampling.LANCZOS)


def download_image(session: requests.Session, url: str, timeout: int) -> Image.Image:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return Image.open(io.BytesIO(response.content))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="docs/latest-manhole-photos.json")
    parser.add_argument("--output-dir", default="dataset/manhole/image")
    parser.add_argument("--size", type=int, default=720)
    parser.add_argument("--quality", type=int, default=82)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--limit", type=int, default=0, help="For smoke tests; 0 means all.")
    parser.add_argument("--env-file", default=".env.local")
    parser.add_argument("--presign-r2", action="store_true", help="Generate signed R2 URLs from storage_key.")
    parser.add_argument("--presign-expires", type=int, default=3600)
    parser.add_argument(
        "--public-base-url",
        default="",
        help="Override image URL with this public base plus each record's storage_key.",
    )
    args = parser.parse_args()
    load_env_file(args.env_file)

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input JSON not found: {input_path}")

    with input_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    seen: set[str] = set()
    imported = 0
    attempted = 0
    skipped = 0
    failed = 0

    for record in iter_records(payload):
        manhole_id = sanitize_id(pick_first(record, ID_KEYS))
        storage_key = get_storage_key(record)
        if args.presign_r2 and storage_key:
            url = presign_r2_get_object(storage_key, args.presign_expires)
        elif args.public_base_url and storage_key:
            url = args.public_base_url.rstrip("/") + "/" + storage_key
        else:
            url = get_photo_url(record)
        url = validate_url(url) if url else None
        if not manhole_id or not url or manhole_id in seen:
            skipped += 1
            continue

        seen.add(manhole_id)
        attempted += 1
        output_path = output_dir / f"{manhole_id}_latest.jpeg"
        try:
            image = download_image(session, url, args.timeout)
            cropped = crop_to_square(image, args.size)
            cropped.save(output_path, "JPEG", quality=args.quality, optimize=True, progressive=True)
            imported += 1
            print(f"imported id={manhole_id} -> {output_path}")
        except Exception as exc:
            failed += 1
            print(f"failed id={manhole_id} url={redact_url(url)}: {exc}")

        if args.limit and attempted >= args.limit:
            break

    print(f"summary imported={imported} skipped={skipped} failed={failed} output_dir={output_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
