"""同一自治体で重複する表示名を区別するための place_label の算出。

`title` は local.pokemon.jp の見出しをそのまま格納しているため
「鹿児島県/指宿市」のように**自治体単位**でしか区別できず、
指宿市9枚・町田市6枚のように同じ文字列が地図上に並んでしまう。

そこで重複しているレコードにだけ `place_label`（場所の名前）を付与する。
`title` は upstream 原文のまま残す（差分検知の基準に使うため）ので、
表示側は `place_label || title` で読むこと。

**ポケモン名は place_label に焼き込まない。** 理由:

- 地図ポップアップはポケモン名チップを見出しの直下に既に並べており重複する
- サイトは ja/en/ko/zh の多言語ビルドがある。日本語名を焼き込むと英語版でも
  日本語が出てしまう（表示時に組み立てれば `pokemon_metadata.json` で変換できる）
- `pokemons` は公式ページのアンカーテキストからのヒューリスティック抽出で不安定

命名規則:

    building あり : 指宿市 砂むし会館砂楽
    building なし : 斑鳩町 興留7丁目3

ただし同一住所に複数枚ある16件（町田市6・小笠原村4・鳥羽市2・下関市2・台東区上野2）は
場所では原理的に区別できない。この分だけ `place_ambiguous` を立て、
**表示側が言語ごとに変換したポケモン名を添えて** 区別する。
place_label 自体は日本語文字列を増やさない。
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, List, Optional

# 「指宿」→「指宿市」のように、住所から自治体の接尾辞を復元するときに使う。
# record["city"] は strip_municipality_suffix() 済みで接尾辞が落ちている。
_MUNICIPALITY_SUFFIX = "[市区町村]"


def municipality_label(record: Dict[str, Any]) -> str:
    """接尾辞つきの自治体名を返す（例: 指宿 -> 指宿市）。

    record["city"] は接尾辞が落ちているので、住所側に残っている
    「指宿市」を探して復元する。住所から復元できないときは city をそのまま返す。
    """
    city = str(record.get("city") or "").strip()
    address = str(record.get("address") or "").strip()
    if not city:
        return str(record.get("prefecture") or "").strip()
    if address:
        m = re.search(re.escape(city) + _MUNICIPALITY_SUFFIX, address)
        if m:
            return m.group(0)
    return city


def town_label(record: Dict[str, Any], city_label: str) -> str:
    """住所から自治体より後ろを返す（例: 興留7丁目3）。

    丁目・番地まで残す。ここを切り落とすと斑鳩町の3枚（興留7丁目3 / 5丁目5 /
    2丁目1）や倉敷市・小千谷市が区別できなくなる。
    政令市の区（右京区…）も落とさずに含める。住所には
    「新潟県小千谷市小千谷市城内1-8-22」のように自治体名が二重に入った
    実データがあるため、繰り返し分は取り除く。
    """
    address = str(record.get("address") or "").strip()
    if not address or not city_label:
        return ""
    idx = address.find(city_label)
    if idx < 0:
        return ""
    rest = address[idx + len(city_label):]
    while rest.startswith(city_label):
        rest = rest[len(city_label):]
    # 「浅野三丁目5　あさの汐風公園」のように住所欄へ施設名が全角スペースで
    # 続いている実データがあるので空白を整える
    rest = re.sub(r"\s+", " ", rest.replace("　", " "))
    rest = rest.strip(" -－・")
    # 「京都府ニンテンドーミュージアム施設内（宇治市小倉町神楽田56番地）」のように
    # 自治体名が括弧の内側にある住所では閉じ括弧だけが残る。対応する開き括弧が
    # 無い閉じ括弧は落とす
    while rest and rest[-1] in "）)":
        opener = "（" if rest[-1] == "）" else "("
        if rest.count(opener) >= rest.count(rest[-1]):
            break
        rest = rest[:-1].rstrip(" 　")
    return rest


def landmark_label(record: Dict[str, Any], city_label: str) -> str:
    """設置場所の施設名を表示用に整える。

    building は manhole_titles.json 由来の手動メタデータで、
    全角スペース区切りや「指宿市 指宿図書館」のように自治体名を
    含む値が混在しているため正規化する。
    """
    building = str(record.get("building") or "").replace("　", " ")
    building = re.sub(r"\s+", " ", building).strip()
    if not building:
        return ""
    if city_label and building.startswith(city_label):
        building = building[len(city_label):].strip()
    return building


def build_place_label(record: Dict[str, Any], *, prefer_address: bool = False) -> str:
    """1レコードの place_label を組み立てる（自治体名込み・ポケモン名なし）。

    prefer_address=True のときは building を無視して住所を使う。
    東大阪市の2枚のように「同じ公園だが住所が違う」ケースを解くための再算出用。
    """
    city_label = municipality_label(record)
    place = "" if prefer_address else landmark_label(record, city_label)
    if not place:
        place = town_label(record, city_label)
    return f"{city_label} {place}".strip() if place else city_label


def _group_key(record: Dict[str, Any]) -> str:
    title = str(record.get("title") or "").strip()
    if title:
        return title
    return f"{record.get('prefecture', '')}/{record.get('city', '')}"


def _counts(values: Iterable[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def _is_active(record: Dict[str, Any]) -> bool:
    return record.get("status") == "active"


def attach_place_labels(records: Iterable[Dict[str, Any]],
                        *, active_predicate: Optional[Callable[[Dict[str, Any]], bool]] = None) -> int:
    """title が重複している active レコードに place_label を付与する。

    place_label まで同じになってしまうレコードには `place_ambiguous: True` を立てる
    （表示側がポケモン名を添えて区別する）。一意な title を持つレコードからは
    両フィールドを取り除く。付与した件数を返す。

    active_predicate は「生きているレコード」の判定を差し替えるためのもの。
    Supabase 由来のアプリ用スナップショットは status ではなく is_active を持つ。
    """
    is_active = active_predicate or _is_active
    all_records: List[Dict[str, Any]] = list(records)

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for record in all_records:
        if not is_active(record):
            record.pop("place_label", None)
            record.pop("place_ambiguous", None)
            continue
        groups.setdefault(_group_key(record), []).append(record)

    attached = 0
    for group in groups.values():
        if len(group) < 2:
            for record in group:
                record.pop("place_label", None)
                record.pop("place_ambiguous", None)
            continue

        labels = {id(r): build_place_label(r) for r in group}

        # 同じ施設名になったものは住所で再算出する。東大阪市の2枚は
        # どちらも building が「花園中央公園」だが住所（松原南1-1 / 2-6）で分かれる。
        counts = _counts(labels.values())
        for record in group:
            if counts[labels[id(record)]] > 1:
                # 住所が取れないときは build_place_label が自治体名だけを返す。
                # 「指宿市 施設名」から「指宿市」へ後退させないため、住所由来の
                # place 部分が取れたときだけ差し替える
                if town_label(record, municipality_label(record)):
                    labels[id(record)] = build_place_label(record, prefer_address=True)

        counts = _counts(labels.values())
        for record in group:
            label = labels[id(record)]
            record["place_label"] = label
            if counts[label] > 1:
                record["place_ambiguous"] = True
            else:
                record.pop("place_ambiguous", None)
            attached += 1

    return attached


def pokemon_suffix(record: Dict[str, Any], *, separator: str = "・",
                   brackets: str = "（）") -> str:
    """ポケモン名を括弧で括った接尾辞を返す。曖昧な場所の区別用。"""
    pokemons = [str(p).strip() for p in (record.get("pokemons") or []) if str(p).strip()]
    if not pokemons:
        return ""
    open_b, close_b = brackets[0], brackets[1]
    return f"{open_b}{separator.join(pokemons)}{close_b}"


def compose_display_name(record: Dict[str, Any], *,
                         always_with_pokemon: bool = False) -> str:
    """Python 側の消費者（KML など）向けに1本の表示名を組み立てる。

    always_with_pokemon=True は KML のようにポケモン名を別枠で見せられない
    出力向け。既定では `place_ambiguous` のときだけポケモン名を添える。
    """
    base = str(record.get("place_label") or record.get("title") or "").strip()
    if always_with_pokemon or record.get("place_ambiguous"):
        suffix = pokemon_suffix(record)
        if suffix:
            return f"{base}{suffix}"
    return base
