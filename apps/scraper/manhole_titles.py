#!/usr/bin/env python3
"""Compute manhole 称号 (title badges) from pokefuta.ndjson + manhole_titles.json master.

Called by update_pokefuta.py to pre-compute titles and store them in pokefuta.ndjson.
LP generators (generate_manhole_pages.py, generate_manhole_ogp.py) read
manhole["titles"] directly — no need to access manhole_titles.json at render time.
"""
from __future__ import annotations

import math
from typing import Optional


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def _filter_pokemons(raw: list) -> list[str]:
    return [p for p in raw if isinstance(p, str) and p.strip() and "ローカルActs" not in p]


def _beats_min(v: float, best: Optional[float], mid: str, best_id: Optional[str]) -> bool:
    """Return True if v should replace the current minimum best."""
    if best is None:
        return True
    try:
        return v < best or (v == best and int(mid) < int(best_id))
    except ValueError:
        return v < best


def _beats_max(v: float, best: Optional[float], mid: str, best_id: Optional[str]) -> bool:
    """Return True if v should replace the current maximum best."""
    if best is None:
        return True
    try:
        return v > best or (v == best and int(mid) < int(best_id))
    except ValueError:
        return v > best


def build_title_context(manholes: list[dict], master: dict) -> dict:
    """Scan all active manholes once to build aggregates needed for title computation.

    Returns a context dict with keys:
      pref_count, city_count, pokemon_count, top_pref, top_pref_count,
      north_id, south_id, east_id, west_id, newest_date, pioneer_threshold,
      coords, islands, lakes, vocabulary.
    """
    vocabulary: dict = master.get("vocabulary", {})
    islands: list = master.get("islands", [])
    lakes: list = master.get("lakes", [])

    pref_count: dict[str, int] = {}
    city_count: dict[str, int] = {}
    pokemon_count: dict[str, int] = {}
    coords: list[tuple[str, float, float]] = []

    north_id = south_id = east_id = west_id = None
    north_lat = south_lat = east_lng = west_lng = None
    newest_date: Optional[str] = None

    for m in manholes:
        if m.get("status") != "active":
            continue
        mid = str(m.get("id", "")).strip()
        pref = m.get("prefecture", "")
        city = m.get("city", "")

        if pref:
            pref_count[pref] = pref_count.get(pref, 0) + 1
        if pref or city:
            key = f"{pref}|{city}"
            city_count[key] = city_count.get(key, 0) + 1

        for pk in _filter_pokemons(m.get("pokemons", [])):
            pokemon_count[pk] = pokemon_count.get(pk, 0) + 1

        lat_raw, lng_raw = m.get("lat"), m.get("lng")
        if lat_raw is not None and lng_raw is not None:
            lat, lng = float(lat_raw), float(lng_raw)
            coords.append((mid, lat, lng))
            if _beats_max(lat, north_lat, mid, north_id):
                north_lat, north_id = lat, mid
            if _beats_min(lat, south_lat, mid, south_id):
                south_lat, south_id = lat, mid
            if _beats_max(lng, east_lng, mid, east_id):
                east_lng, east_id = lng, mid
            if _beats_min(lng, west_lng, mid, west_id):
                west_lng, west_id = lng, mid

        added = m.get("added_at") or ""
        if added and (newest_date is None or added > newest_date):
            newest_date = added

    # Prefecture with the most manholes (tie-break: alphabetically first)
    top_pref, top_pref_count = "", 0
    for p, c in sorted(pref_count.items()):
        if c > top_pref_count:
            top_pref, top_pref_count = p, c

    pioneer_threshold: int = vocabulary.get("pioneer", {}).get("id_threshold", 30)

    return {
        "pref_count": pref_count,
        "city_count": city_count,
        "pokemon_count": pokemon_count,
        "top_pref": top_pref,
        "top_pref_count": top_pref_count,
        "north_id": north_id,
        "south_id": south_id,
        "east_id": east_id,
        "west_id": west_id,
        "newest_date": newest_date,
        "pioneer_threshold": pioneer_threshold,
        "coords": coords,
        "islands": islands,
        "lakes": lakes,
        "vocabulary": vocabulary,
    }


def nearby_count(mid: str, lat, lng, coords: list[tuple], km: float) -> int:
    """Count active manholes within `km` km using precomputed coords list."""
    if lat is None or lng is None:
        return 0
    flat, flng = float(lat), float(lng)
    return sum(
        1 for oid, olat, olng in coords
        if oid != mid and _haversine(flat, flng, olat, olng) <= km
    )


def compute_titles(manhole: dict, ctx: dict, *, nc50: int, nc100: int) -> list[dict]:
    """Return title list (priority desc) for one active manhole.

    Each title dict: {"key": str, "label": str, "emoji": str, "hashtag": str, "priority": int}
    Tier 1 titles are derived from ctx (built from all active manholes).
    Tier 2 titles use ctx["islands"] / ctx["lakes"] / manhole["tags"] from pokefuta.ndjson.
    nc100: active manholes within 100 km; nc50: within 50 km (pre-computed by caller).
    """
    vocab: dict = ctx["vocabulary"]
    mid = str(manhole.get("id", "")).strip()
    pref = manhole.get("prefecture", "")
    city = manhole.get("city", "")
    tags: list = manhole.get("tags", []) or []
    added = manhole.get("added_at", "") or ""

    def _entry(key: str, **overrides) -> Optional[dict]:
        v = vocab.get(key, {})
        if not v.get("enabled", True):
            return None
        label = v.get("label", key)
        hashtag = v.get("hashtag", "")
        hashtag_extra = v.get("hashtag_extra", "")
        # Replace standard placeholders
        label = label.replace("{prefecture}", pref).replace("{city}", city)
        hashtag = hashtag.replace("{prefecture}", pref).replace("{city}", city)
        hashtag_extra = hashtag_extra.replace("{prefecture}", pref).replace("{city}", city)
        # Replace extra placeholders from overrides
        for k, val in overrides.items():
            label = label.replace(f"{{{k}}}", str(val))
            hashtag = hashtag.replace(f"{{{k}}}", str(val))
            hashtag_extra = hashtag_extra.replace(f"{{{k}}}", str(val))
        # Combine hashtag_extra (e.g. "#{island}") into hashtag field
        if hashtag_extra:
            hashtag = f"{hashtag} {hashtag_extra}".strip()
        return {
            "key": key,
            "label": label,
            "emoji": v.get("emoji", ""),
            "hashtag": hashtag,
            "priority": v.get("priority", 0),
        }

    results: list[dict] = []

    # --- Tier 1: auto-calculated ---

    if ctx["north_id"] == mid:
        if t := _entry("north_end"):
            results.append(t)
    if ctx["south_id"] == mid:
        if t := _entry("south_end"):
            results.append(t)
    if ctx["east_id"] == mid:
        if t := _entry("east_end"):
            results.append(t)
    if ctx["west_id"] == mid:
        if t := _entry("west_end"):
            results.append(t)

    pokemons = _filter_pokemons(manhole.get("pokemons", []))

    # unique_pokemon: one badge per pokemon that appears nowhere else nationwide
    for pk in pokemons:
        if ctx["pokemon_count"].get(pk, 0) == 1:
            if t := _entry("unique_pokemon", pokemon=pk):
                results.append(t)

    # only_in_pref: this prefecture has exactly 1 active manhole
    pref_unique = pref and ctx["pref_count"].get(pref, 0) == 1
    if pref_unique:
        if t := _entry("only_in_pref"):
            results.append(t)

    # rare_pokemon: primary pokemon total 2-3 (excludes count=1 covered by unique_pokemon)
    if pokemons:
        primary_count = ctx["pokemon_count"].get(pokemons[0], 0)
        if 2 <= primary_count <= 3:
            if t := _entry("rare_pokemon", count=primary_count):
                results.append(t)

    # lone_100 / lone: ぽつんと一枚。100km圏→lone_100、50km圏→lone（上位が該当すれば下位は付与しない）
    if manhole.get("lat") is not None:
        if nc100 == 0:
            if t := _entry("lone_100"):
                results.append(t)
        elif nc50 == 0:
            if t := _entry("lone"):
                results.append(t)

    # only_in_city: city has exactly 1 manhole AND only_in_pref is NOT set
    city_key = f"{pref}|{city}"
    if (pref or city) and ctx["city_count"].get(city_key, 0) == 1 and not pref_unique:
        if t := _entry("only_in_city"):
            results.append(t)

    # pref_top: manhole's prefecture is the one with the most manholes nationwide
    if pref and pref == ctx["top_pref"]:
        if t := _entry("pref_top", count=ctx["top_pref_count"]):
            results.append(t)

    # newest: added_at matches the globally newest date
    if added and ctx["newest_date"] and added[:10] == ctx["newest_date"][:10]:
        if t := _entry("newest"):
            results.append(t)

    # pioneer: id <= threshold
    try:
        if int(mid) <= ctx["pioneer_threshold"]:
            if t := _entry("pioneer"):
                results.append(t)
    except ValueError:
        pass

    # --- Tier 2: manual master ---

    # remote_island: check islands list (ids take priority over prefecture+city match)
    for island_entry in ctx["islands"]:
        ids = [str(i) for i in (island_entry.get("ids") or [])]
        island_name = island_entry.get("island", "")
        if ids:
            if mid in ids:
                if t := _entry("remote_island", island=island_name):
                    results.append(t)
                break
        else:
            if (island_entry.get("prefecture") == pref and
                    island_entry.get("city") == city):
                if t := _entry("remote_island", island=island_name):
                    results.append(t)
                break

    # seaside: tags contains "beach" or "seaside"
    if any(tag in ("beach", "seaside") for tag in tags):
        if t := _entry("seaside"):
            results.append(t)

    # station_front / near_station: 駅前・駅近タグ（より具体的な方のみ表示）
    if "station_front" in tags:
        if t := _entry("station_front"):
            results.append(t)
    elif "near_station" in tags:
        if t := _entry("near_station"):
            results.append(t)

    # lakeside: check lakes list
    for lake_entry in ctx["lakes"]:
        ids = [str(i) for i in (lake_entry.get("ids") or [])]
        lake_name = lake_entry.get("lake", "")
        if ids:
            if mid in ids:
                if t := _entry("lakeside", lake=lake_name):
                    results.append(t)
                break
        else:
            if (lake_entry.get("prefecture") == pref and
                    lake_entry.get("city") == city):
                if t := _entry("lakeside", lake=lake_name):
                    results.append(t)
                break

    # Sort by priority desc; stable sort preserves catalog insertion order for ties
    results.sort(key=lambda x: -x["priority"])
    return results
