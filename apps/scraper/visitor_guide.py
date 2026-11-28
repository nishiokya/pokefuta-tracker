"""Select public visitor notes and nearby scenery for one lid's detail page."""

import re
import unicodedata
from datetime import datetime, timezone


def visit_note_text(value: object) -> str:
    """Match the studio's visit-comment-quality filter for photo notes."""
    text = " ".join(value.split()) if isinstance(value, str) else ""
    compact = "".join(text.lower().split())
    if len(compact) < 5 or len(set(compact)) <= 2:
        return ""
    if all(ch.isdecimal() or unicodedata.category(ch)[0] in "PS" for ch in compact):
        return ""
    if len(compact) <= 10 and re.search("テスト|test", compact):
        return ""
    return text


def _order(entry: dict) -> tuple[datetime, str]:
    raw = entry.get("created_at") or ""
    try:
        date = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        date = date if date.tzinfo else date.replace(tzinfo=timezone.utc)
    except ValueError:
        date = datetime.min.replace(tzinfo=timezone.utc)
    return date, entry.get("photo_id") or entry.get("id") or ""


def select_guide(photos: list[dict], comments: list[dict], users: dict) -> dict:
    notes = [
        {"content": row["content"].strip(), "created_at": row["created_at"], "id": row["id"]}
        for row in comments if (row.get("content") or "").strip()
    ]
    scenery = []
    for photo in photos:
        visit = photo["visit"]
        if not visit.get("is_public"):
            continue
        entry = {
            "photo_id": photo["id"],
            "created_at": visit.get("created_at") or photo["created_at"],
            "shot_at": visit.get("shot_at"),
            "display_name": users.get(visit.get("user_id"), {}).get("display_name"),
        }
        if photo.get("is_landscape"):
            scenery.append(entry)
        content = visit_note_text(visit.get("comment"))
        if content:
            notes.append({**entry, "content": content})

    # Several photos from one visit share the same note. Repeated identical tips
    # from different visits also only need to appear once, with the newest source.
    unique = {}
    for note in sorted(notes, key=_order, reverse=True):
        unique.setdefault(" ".join(note["content"].split()), note)
        if len(unique) == 3:
            break
    return {"notes": list(unique.values()), "scenery": sorted(scenery, key=_order, reverse=True)[:2]}


def legacy_guide(photo: dict) -> dict:
    """Bridge the last daily snapshot before visitor_guides was introduced."""
    text = visit_note_text(photo.get("comment"))
    photo_id = photo.get("photo_id")
    if not text or not photo_id or not any(g.get("photo_id") == photo_id for g in photo.get("gallery", [])):
        return {}
    note = {key: photo.get(key) for key in ("photo_id", "shot_at", "created_at", "display_name")}
    return {"notes": [{**note, "content": text}]}
