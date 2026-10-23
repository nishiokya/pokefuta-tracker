"""図鑑のページ生成器が共通で使う、マンホールのデータの読み込みと加工（内部ライブラリ）。

県・市町村・trip・特集・英語/繁体字の各ページが generate_prefecture_pages の private 関数を
直接借りていたので、ここへ移した。画像フォルダ（ROOT）に依存するものはここに置かない。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

try:
    from apps.scraper.display_names import compose_display_name, municipality_label
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from display_names import compose_display_name, municipality_label


FORM_PREFIX = {
    "alola": "アローラ",
    "galar": "ガラル",
    "hisui": "ヒスイ",
    "paldea": "パルデア",
}


def load_records(path: Path) -> list[dict]:
    by_id: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        record_id = str(record.get("id", "")).strip()
        if not record_id:
            continue
        by_id[record_id] = {**by_id.get(record_id, {}), **record}
    return [
        record for record in by_id.values()
        if record.get("status", "active") == "active"
    ]


def load_photos(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    raw_photos = payload.get("photos", {}) if isinstance(payload, dict) else {}
    if not isinstance(raw_photos, dict):
        return {}
    return {
        str(manhole_id): photo
        for manhole_id, photo in raw_photos.items()
        if isinstance(photo, dict)
    }


def normalize_katakana(text: str) -> str:
    return "".join(
        chr(ord(char) + 0x60) if "ぁ" <= char <= "ゖ" else char
        for char in text
    )


def load_pokemon_slugs(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for pokemon in json.loads(path.read_text(encoding="utf-8")):
        if not isinstance(pokemon, dict):
            continue
        name = pokemon.get("names", {}).get("ja", "")
        slug = pokemon.get("slug", "")
        form = pokemon.get("form") or ""
        if not name or not slug:
            continue
        if name not in result or not form:
            result[name] = slug
        prefix = FORM_PREFIX.get(form)
        if prefix:
            result.setdefault(prefix + name, slug)
    for name, slug in list(result.items()):
        result.setdefault(normalize_katakana(name), slug)
    return result


def clean_pokemons(record: dict) -> list[str]:
    return [
        pokemon for pokemon in record.get("pokemons", [])
        if isinstance(pokemon, str)
        and pokemon.strip()
        and "ローカルActs" not in pokemon
    ]


def manhole_name(record: dict) -> str:
    # 正本のマンホール名。city は公式の生の値（「町田」「台東区上野」）で、
    # 同じ自治体の蓋を区別できないので名前には使わない。
    return compose_display_name(record) or municipality_label(record) or "所在地不明"


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def guide_stop_name(record: dict) -> str:
    # 施設名のない蓋は「長崎県/長崎市」になる。県ページ内の案内では県名が重複するので省く。
    return manhole_name(record).removeprefix(f'{record.get("prefecture", "")}/')


def google_maps_url(record: dict) -> str:
    lat = record.get("lat")
    lng = record.get("lng")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return ""
    return f"https://www.google.com/maps?q={lat},{lng}"
