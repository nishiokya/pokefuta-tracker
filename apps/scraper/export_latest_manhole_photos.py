#!/usr/bin/env python3
"""
Export the latest photo URL for each manhole as JSON.

This intentionally uses only Python's standard library so it can be run
locally without adding project dependencies.

Example:
  export NEXT_PUBLIC_SUPABASE_URL="https://xxxxx.supabase.co"
  export SUPABASE_SERVICE_ROLE_KEY="xxxxx"
  export R2_PUBLIC_BASE_URL="https://images.pokefuta.com"
  python3 tools/export_latest_manhole_photos.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional


DEFAULT_OUTPUT = "public/data/latest-manhole-photos.json"
DEFAULT_BATCH_SIZE = 1000
DEFAULT_TIMEOUT = 30
DEFAULT_MANHOLE_COMMENT_DISPLAY_NAME = "tako"
DEFAULT_GALLERY_LIMIT = 5


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def strip_trailing_slash(value: str) -> str:
    return value.rstrip("/")


def encode_storage_key(storage_key: str) -> str:
    return "/".join(urllib.parse.quote(part) for part in storage_key.split("/"))


def get_supabase_key() -> str:
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if service_role_key and not service_role_key.lower().startswith("placeholder"):
        return service_role_key
    anon_key = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    if anon_key:
        return anon_key
    raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY or NEXT_PUBLIC_SUPABASE_ANON_KEY is required")


def get_r2_public_base_url() -> str:
    value = os.environ.get("R2_PUBLIC_BASE_URL") or os.environ.get("R2_PUBLIC_URL")
    if not value:
        raise RuntimeError("R2_PUBLIC_BASE_URL or R2_PUBLIC_URL is required")
    return strip_trailing_slash(value)


def get_effective_r2_public_base_url() -> str:
    base_url = get_r2_public_base_url()
    if "r2.cloudflarestorage.com" not in base_url:
        return base_url

    parsed = urllib.parse.urlparse(base_url)
    if parsed.path and parsed.path != "/":
        return base_url

    bucket = require_env("R2_BUCKET")
    return f"{base_url}/{urllib.parse.quote(bucket)}"


def build_original_url(storage_key: str, base_url: str) -> str:
    encoded_key = encode_storage_key(storage_key)
    return f"{base_url}/{encoded_key}"


def parse_datetime(value: Optional[str]) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def normalize_visit(visit: Any) -> dict[str, Any]:
    if isinstance(visit, list):
        return visit[0] if visit else {}
    return visit if isinstance(visit, dict) else {}


def photo_sort_date(photo: dict[str, Any]) -> datetime:
    visit = normalize_visit(photo.get("visit"))
    return parse_datetime(visit.get("shot_at") or photo.get("created_at"))


def _lookup_user_info(
    user_info_by_auth_uid: dict[str, dict[str, Optional[str]]],
    user_id: Any,
) -> tuple[Optional[str], Optional[str]]:
    info = user_info_by_auth_uid.get(user_id) if isinstance(user_id, str) else None
    if not info:
        return None, None
    return info.get("display_name"), info.get("public_user_id")


def to_photo_entry(
    photo: dict[str, Any],
    base_url: str,
    user_info_by_auth_uid: dict[str, dict[str, Optional[str]]],
) -> dict[str, Any]:
    visit = normalize_visit(photo.get("visit"))
    storage_key = photo["storage_key"]
    original_url = build_original_url(storage_key, base_url)
    user_id = visit.get("user_id")
    display_name, public_user_id = _lookup_user_info(user_info_by_auth_uid, user_id)

    return {
        "manhole_id": photo["manhole_id"],
        "photo_id": photo["id"],
        "url": original_url,
        "original_url": original_url,
        "storage_key": storage_key,
        "content_type": photo.get("content_type"),
        "width": photo.get("width"),
        "height": photo.get("height"),
        "file_size": photo.get("file_size"),
        "created_at": photo.get("created_at"),
        "shot_at": visit.get("shot_at"),
        "comment": visit.get("comment"),
        "display_name": display_name,
        "public_user_id": public_user_id,
    }


def to_gallery_entry(
    photo: dict[str, Any],
    base_url: str,
    user_info_by_auth_uid: dict[str, dict[str, Optional[str]]],
) -> dict[str, Any]:
    visit = normalize_visit(photo.get("visit"))
    storage_key = photo["storage_key"]
    user_id = visit.get("user_id")
    display_name, public_user_id = _lookup_user_info(user_info_by_auth_uid, user_id)

    return {
        "photo_id": photo["id"],
        "url": build_original_url(storage_key, base_url),
        "storage_key": storage_key,
        "content_type": photo.get("content_type"),
        "created_at": photo.get("created_at"),
        "shot_at": visit.get("shot_at"),
        "display_name": display_name,
        "public_user_id": public_user_id,
    }


def select_gallery_photos(
    photos: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Pick gallery photos: public only, newest first, at most `limit` entries.

    The spec (pokefuta-tracker docs/MANHOLE_DETAIL_SPEC.md) requires the
    gallery to contain only is_public photos even when the export itself
    runs with --include-private.
    """
    public_photos = [
        photo
        for photo in photos
        if normalize_visit(photo.get("visit")).get("is_public")
    ]
    return sorted(public_photos, key=photo_sort_date, reverse=True)[:limit]


def supabase_get(
    path: str,
    query: dict[str, str],
    batch_size: int,
    offset: int,
    timeout: int,
) -> list[dict[str, Any]]:
    supabase_url = strip_trailing_slash(require_env("NEXT_PUBLIC_SUPABASE_URL"))
    service_role_key = get_supabase_key()

    params = dict(query)
    params["limit"] = str(batch_size)
    params["offset"] = str(offset)

    url = f"{supabase_url}/rest/v1/{path}?{urllib.parse.urlencode(params, safe='(),.!:*')}"
    request = urllib.request.Request(
        url,
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def iter_supabase_rows(
    path: str,
    query: dict[str, str],
    batch_size: int,
    timeout: int,
) -> Iterator[dict[str, Any]]:
    offset = 0

    while True:
        batch = supabase_get(path, query, batch_size, offset, timeout)
        yield from batch

        if len(batch) < batch_size:
            break
        offset += batch_size


def iter_photos(include_private: bool, batch_size: int, timeout: int) -> Iterator[dict[str, Any]]:
    select_visit = (
        "visit(shot_at,is_public,user_id,comment)"
        if include_private
        else "visit!inner(shot_at,is_public,user_id,comment)"
    )
    query = {
        "select": f"id,manhole_id,storage_key,content_type,width,height,file_size,created_at,{select_visit}",
        "manhole_id": "not.is.null",
        "storage_key": "not.is.null",
        "order": "created_at.desc,id.desc",
    }

    if not include_private:
        query["visit.is_public"] = "eq.true"

    yield from iter_supabase_rows("photo", query, batch_size, timeout)


def chunked(values: list[str], size: int) -> Iterator[list[str]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def fetch_user_info(
    auth_uids: set[str],
    batch_size: int,
    timeout: int,
) -> dict[str, dict[str, Optional[str]]]:
    """Map auth_uid -> {display_name, public_user_id (app_user.id)}."""
    user_info_by_auth_uid: dict[str, dict[str, Optional[str]]] = {}
    ids = sorted(auth_uids)

    for id_batch in chunked(ids, 100):
        query = {
            "select": "id,auth_uid,display_name",
            "auth_uid": f"in.({','.join(id_batch)})",
        }

        for user in iter_supabase_rows("app_user", query, batch_size, timeout):
            auth_uid = user.get("auth_uid")
            if isinstance(auth_uid, str):
                user_info_by_auth_uid[auth_uid] = {
                    "display_name": user.get("display_name"),
                    "public_user_id": user.get("id"),
                }

    return user_info_by_auth_uid


def fetch_auth_uids_by_display_name(
    display_name: str,
    batch_size: int,
    timeout: int,
) -> set[str]:
    query = {
        "select": "auth_uid,display_name",
        "display_name": f"eq.{display_name}",
    }

    auth_uids: set[str] = set()
    for user in iter_supabase_rows("app_user", query, batch_size, timeout):
        auth_uid = user.get("auth_uid")
        if isinstance(auth_uid, str):
            auth_uids.add(auth_uid)

    return auth_uids


def fetch_manhole_comments_by_display_name(
    display_name: str,
    batch_size: int,
    timeout: int,
) -> dict[str, list[dict[str, Any]]]:
    auth_uids = fetch_auth_uids_by_display_name(display_name, batch_size, timeout)
    if not auth_uids:
        return {}

    comments_by_manhole_id: dict[str, list[dict[str, Any]]] = {}

    for id_batch in chunked(sorted(auth_uids), 100):
        query = {
            "select": "id,manhole_id,user_id,content,created_at,updated_at",
            "user_id": f"in.({','.join(id_batch)})",
            "parent_comment_id": "is.null",
            "order": "manhole_id.asc,created_at.asc,id.asc",
        }

        for comment in iter_supabase_rows("manhole_comment", query, batch_size, timeout):
            manhole_id = comment.get("manhole_id")
            if manhole_id is None:
                continue

            key = str(manhole_id)
            comments_by_manhole_id.setdefault(key, []).append(
                {
                    "id": comment.get("id"),
                    "manhole_id": manhole_id,
                    "content": comment.get("content"),
                    "created_at": comment.get("created_at"),
                    "updated_at": comment.get("updated_at"),
                    "display_name": display_name,
                }
            )

    return {
        manhole_id: comments_by_manhole_id[manhole_id]
        for manhole_id in sorted(comments_by_manhole_id, key=lambda value: int(value))
    }


def build_payload(
    include_private: bool,
    batch_size: int,
    timeout: int,
    manhole_comment_display_name: str,
    gallery_limit: int,
) -> dict[str, Any]:
    base_url = get_effective_r2_public_base_url()
    photos_by_manhole_id: dict[int, list[dict[str, Any]]] = {}
    photo_user_ids: set[str] = set()

    for photo in iter_photos(include_private=include_private, batch_size=batch_size, timeout=timeout):
        visit = normalize_visit(photo.get("visit"))
        user_id = visit.get("user_id")
        if isinstance(user_id, str):
            photo_user_ids.add(user_id)

        photos_by_manhole_id.setdefault(int(photo["manhole_id"]), []).append(photo)

    user_info_by_auth_uid = fetch_user_info(photo_user_ids, batch_size, timeout)

    photos: dict[str, dict[str, Any]] = {}
    for manhole_id in sorted(photos_by_manhole_id):
        manhole_photos = sorted(
            photos_by_manhole_id[manhole_id],
            key=photo_sort_date,
            reverse=True,
        )
        entry = to_photo_entry(manhole_photos[0], base_url, user_info_by_auth_uid)
        entry["gallery"] = [
            to_gallery_entry(photo, base_url, user_info_by_auth_uid)
            for photo in select_gallery_photos(manhole_photos, gallery_limit)
        ]
        photos[str(manhole_id)] = entry
    manhole_comments = fetch_manhole_comments_by_display_name(
        manhole_comment_display_name,
        batch_size,
        timeout,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "pokefuta photo table",
        "image": {
            "r2_public_base_url": base_url,
        },
        "count": len(photos),
        "photos": photos,
        "manhole_comments": manhole_comments,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export latest photo URLs by manhole ID as JSON.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=os.environ.get("OUTPUT_PATH", DEFAULT_OUTPUT),
        help=f"Output JSON path. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--include-private",
        action="store_true",
        default=os.environ.get("INCLUDE_PRIVATE_PHOTOS") == "true",
        help="Include photos attached to private visits.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("PHOTO_EXPORT_BATCH_SIZE", DEFAULT_BATCH_SIZE)),
        help=f"Supabase page size. Default: {DEFAULT_BATCH_SIZE}",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("PHOTO_EXPORT_TIMEOUT", DEFAULT_TIMEOUT)),
        help=f"HTTP request timeout in seconds. Default: {DEFAULT_TIMEOUT}",
    )
    parser.add_argument(
        "--manhole-comment-display-name",
        default=os.environ.get("MANHOLE_COMMENT_DISPLAY_NAME", DEFAULT_MANHOLE_COMMENT_DISPLAY_NAME),
        help=f"Include manhole comments posted by this display_name. Default: {DEFAULT_MANHOLE_COMMENT_DISPLAY_NAME}",
    )
    parser.add_argument(
        "--gallery-limit",
        type=int,
        default=int(os.environ.get("PHOTO_EXPORT_GALLERY_LIMIT", DEFAULT_GALLERY_LIMIT)),
        help=f"Max public photos per manhole in the gallery array. Default: {DEFAULT_GALLERY_LIMIT}",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_payload(
        include_private=args.include_private,
        batch_size=args.batch_size,
        timeout=args.timeout,
        manhole_comment_display_name=args.manhole_comment_display_name,
        gallery_limit=args.gallery_limit,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as output:
        indent = None if args.compact else 2
        json.dump(payload, output, ensure_ascii=False, indent=indent)
        output.write("\n")

    print(f"Exported {payload['count']} latest manhole photos to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
