#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
キャラクターマンホール座標コレクタ (pokefuta風NDJSON)

ポケふた以外のキャラクターマンホールの緯度経度・住所を収集する。
多くのファンガイド/公式が Google マイマップ (maps/d/embed?mid=...) で設置場所を
公開しており、mid から KML をエクスポートすると全ピンの座標+名称が一括で取れる。

手法:
  1. WORKS 設定の mid から KML を取得
     https://www.google.com/maps/d/kml?mid=<MID>&forcekml=1
  2. <Folder> 単位で駐車場等の除外層をフィルタ
  3. <Placemark> の name/coordinates を抽出 (KML座標は lng,lat 順)
  4. name から character / landmark を分解
  5. 国土地理院 逆ジオコーダで prefecture/city/address を補完
     https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress
     muniCd -> 市区町村名 は https://maps.gsi.go.jp/js/muni.js で解決

出力スキーマ (pokefuta.ndjson に倣う):
  { id, work, title, character, landmark, prefecture, city, address,
    lat, lng, source_url, map_mid, marker_label, marker_color,
    status, first_seen, last_updated }

使い方:
  python collect_character_manholes.py --out character_manholes.ndjson
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

UA = {"User-Agent": "pokefuta-tracker character-manhole collector (+https://github.com/nishiokya/pokefuta-tracker)"}
REQ_TIMEOUT = 20
GSI_SLEEP = 0.5

KML_URL = "https://www.google.com/maps/d/kml?mid={mid}&forcekml=1"
GSI_REVERSE = "https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress?lat={lat}&lon={lon}"
GSI_MUNI = "https://maps.gsi.go.jp/js/muni.js"

MARKER_STYLES: Dict[str, Dict[str, str]] = {
    "ゾンビランドサガ": {"marker_label": "ゾ", "marker_color": "#10b981"},
    "ロマンシング サガ": {"marker_label": "ロ", "marker_color": "#f59e0b"},
    "弱虫ペダル": {"marker_label": "弱", "marker_color": "#ec4899"},
    "ちびまる子ちゃん": {"marker_label": "ま", "marker_color": "#8b5cf6"},
    "東海オンエア": {"marker_label": "東", "marker_color": "#14b8a6"},
    "アイドルマスター シンデレラガールズ": {"marker_label": "ア", "marker_color": "#f97316"},
}

# --- 作品ごとのソース設定 -------------------------------------------------
# name_mode:
#   "amp"        : "キャラ&目印" 形式 (& / ＆ で分割)
#   "paren"      : "マンホール（キャラ）" 形式 (括弧の中身がキャラ)
#   "zls_master" : "{市町} {設置場所}「キャラ&目印」" / "…（キャラ×目印）" 形式
# exclude_folders: フォルダ名にこれらの語を含む層は除外 (駐車場など)
WORKS: List[Dict[str, Any]] = [
    {
        "work": "ゾンビランドサガ",
        "slug": "zls",
        "mid": "1FPmlP9AkHBbCvQEnfLMQAkM-72-SANOO",
        "name_mode": "zls_master",
        "exclude_folders": ["駐車", "パーキング", "コインパーキング"],
        "prefecture": "佐賀県",
        "source_url": "https://anime-zls.hamutane.com/manhole/zls-manhole/",
    },
    {
        "work": "ロマンシング サガ",
        "slug": "romasaga",
        "mid": "1aN1RAKyja5avTteXdlrUwIEzuZ69z8g",
        "name_mode": "paren",
        "exclude_folders": ["駐車", "パーキング"],
        "prefecture": "佐賀県",
        "source_url": "https://romasaga.info/monument/manhole",
    },
    {
        "work": "弱虫ペダル",
        "slug": "yowapeda",
        "mid": "1WT8bXEgjX4QlIzDuX6LIgrFfZ9QCwDxb",
        "name_mode": "place_paren",
        "exclude_folders": ["配布", "カード", "駐車", "パーキング"],
        "prefecture": "長崎県",
        "source_url": "https://hamutane.com/manhole/yowapeda-manhole/",
    },
    {
        # ちびまる子ちゃん(静岡市)はマイマップが無いため、公式発表の9設置場所を
        # OSM/Nominatim で座標化して検証済みの座標を静的に保持する。
        # 3デザイン(区ごと)×3配色=9枚。区ごとに3枚ずつ。
        "work": "ちびまる子ちゃん",
        "slug": "chibimaruko",
        "source_type": "static",
        "prefecture": "静岡県",
        "source_url": "https://www.city.shizuoka.lg.jp/s6487/s001090.html",
        "places": [
            {"character": "まる子・友蔵", "landmark": "静岡市歴史博物館", "city": "静岡市葵区", "lat": 34.97664, "lng": 138.38500},
            {"character": "まる子・友蔵", "landmark": "静岡市役所（青葉通り）", "city": "静岡市葵区", "lat": 34.97547, "lng": 138.38288},
            {"character": "まる子・友蔵", "landmark": "静岡駅北口", "city": "静岡市葵区", "lat": 34.97179, "lng": 138.38899},
            {"character": "まる子・たまちゃん", "landmark": "静岡駅南口", "city": "静岡市駿河区", "lat": 34.97100, "lng": 138.38899},
            {"character": "まる子・たまちゃん", "landmark": "グランシップ", "city": "静岡市駿河区", "lat": 34.98555, "lng": 138.41689},
            {"character": "まる子・たまちゃん", "landmark": "日本平動物園", "city": "静岡市駿河区", "lat": 34.97982, "lng": 138.44051},
            {"character": "ちびまる子ちゃん", "landmark": "エスパルスドリームプラザ", "city": "静岡市清水区", "lat": 35.01083, "lng": 138.49276},
            {"character": "ちびまる子ちゃん", "landmark": "三保生涯学習交流館", "city": "静岡市清水区", "lat": 34.99849, "lng": 138.52039},
            {"character": "ちびまる子ちゃん", "landmark": "新清水駅", "city": "静岡市清水区", "lat": 35.01709, "lng": 138.48788},
        ],
    },
    {
        # 自治体・公式観光マップのGoogle Mapsリンクから手動確認した愛知県データ。
        "source_type": "ndjson",
        "path": "dataset/aichi_character_manholes.ndjson",
    },
]


def now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _local(tag: str) -> str:
    """Strip XML namespace: '{ns}Folder' -> 'Folder'."""
    return tag.rsplit("}", 1)[-1]


def fetch_text(url: str, retry: int = 3) -> Optional[str]:
    last = None
    for i in range(retry):
        try:
            r = requests.get(url, headers=UA, timeout=REQ_TIMEOUT)
            r.raise_for_status()
            return r.text
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.8 * (i + 1))
    print(f"WARN fetch failed {url}: {last}", file=sys.stderr)
    return None


def load_muni_table() -> Dict[str, Dict[str, str]]:
    """GSI muni.js を取得し muniCd -> {pref, city} を返す。

    muni.js は charset 未指定のため requests が ISO-8859-1 と誤判定して
    文字化けする。UTF-8 を明示してデコードする。
    """
    table: Dict[str, Dict[str, str]] = {}
    try:
        r = requests.get(GSI_MUNI, headers=UA, timeout=REQ_TIMEOUT)
        r.raise_for_status()
        txt = r.content.decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        print(f"WARN muni.js fetch failed: {e}", file=sys.stderr)
        return table
    for m in re.finditer(r'MUNI_ARRAY\["?(\d{5})"?\]\s*=\s*\'([^\']*)\'', txt):
        parts = m.group(2).split(",")
        pref = parts[1] if len(parts) > 1 else ""
        city = parts[3] if len(parts) > 3 else (parts[2] if len(parts) > 2 else "")
        table[m.group(1)] = {"pref": pref, "city": city}
    return table


def gsi_reverse(lat: float, lng: float, muni: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    """緯度経度 -> {prefecture, city, address}. 失敗時は空文字。"""
    txt = fetch_text(GSI_REVERSE.format(lat=lat, lon=lng), retry=2)
    if not txt:
        return {"prefecture": "", "city": "", "address": ""}
    try:
        j = json.loads(txt)
        res = j.get("results") or {}
        code = str(res.get("muniCd") or "").zfill(5)
        town = res.get("lv01Nm") or ""
        mc = muni.get(code, {})
        pref = mc.get("pref", "")
        city = mc.get("city", "")
        address = f"{pref}{city}{town}" if (pref or city) else town
        return {"prefecture": pref, "city": city, "address": address}
    except Exception as e:  # noqa: BLE001
        print(f"WARN gsi parse {lat},{lng}: {e}", file=sys.stderr)
        return {"prefecture": "", "city": "", "address": ""}


def split_name(name: str, mode: str) -> Dict[str, str]:
    """Placemark 名から character / landmark / city_hint を分解。title は原名を保持。"""
    title = name.strip()
    if mode == "paren":
        m = re.search(r"[（(]([^）)]+)[）)]", title)
        character = m.group(1).strip() if m else title
        return {"title": title, "character": character, "landmark": "", "city_hint": ""}
    if mode == "place_paren":
        # "設置場所（キャラ）" 形式: 括弧の前が設置場所、中身がキャラ
        m = re.search(r"[（(]([^）)]+)[）)]", title)
        if m:
            character = m.group(1).strip()
            landmark = title[: m.start()].strip()
        else:
            character = title
            landmark = ""
        return {"title": title, "character": character, "landmark": landmark, "city_hint": ""}
    if mode == "zls_master":
        # "{市町} {設置場所}「キャラ&目印」" / "…（キャラ×目印）" 形式
        rest = title
        city_hint = ""
        m_city = re.match(r"^(\S+?[市町村区])\s+(.*)$", title)
        if m_city:
            city_hint = m_city.group(1)
            rest = m_city.group(2).strip()
        # 第1/2/4弾はキャラを「」で囲む。第3弾は（キャラ×目印）。
        # 設置場所名自体が（）を含む場合があるため「」を優先し、
        # 無ければ末尾の（）を採用する。
        inside = ""
        place = rest
        m_kagi = re.search(r"「([^」]+)」", rest)
        if m_kagi:
            place = rest[: m_kagi.start()].strip()
            inside = m_kagi.group(1).strip()
        else:
            parens = list(re.finditer(r"[（(]([^）)]+)[）)]", rest))
            if parens:
                m_last = parens[-1]
                place = rest[: m_last.start()].strip()
                inside = m_last.group(1).strip()
        character = re.split(r"\s*[&＆×]\s*", inside, maxsplit=1)[0].strip() if inside else rest
        landmark = place or inside
        return {"title": title, "character": character, "landmark": landmark, "city_hint": city_hint}
    # amp mode
    parts = re.split(r"\s*[&＆]\s*", title, maxsplit=1)
    character = parts[0].strip()
    landmark = parts[1].strip() if len(parts) > 1 else ""
    return {"title": title, "character": character, "landmark": landmark, "city_hint": ""}


def parse_kml_placemarks(kml_text: str, exclude_folders: List[str]) -> List[Dict[str, str]]:
    """KML から (name, lat, lng, folder) を抽出。除外フォルダはスキップ。

    Google マイマップは Document > Folder > Placemark のフラット構造。
    フォルダ外 (Document直下) の Placemark も拾う。
    """
    root = ET.fromstring(kml_text)
    # Document 要素を探す
    doc = None
    for el in root.iter():
        if _local(el.tag) == "Document":
            doc = el
            break
    if doc is None:
        doc = root

    out: List[Dict[str, str]] = []

    def emit_placemark(pm: ET.Element, folder_name: str) -> None:
        name = ""
        coord = ""
        for child in pm.iter():
            lt = _local(child.tag)
            if lt == "name" and not name:
                name = (child.text or "").strip()
            elif lt == "coordinates" and not coord:
                coord = (child.text or "").strip()
        if not coord:
            return
        first = coord.split()[0]
        nums = first.split(",")
        if len(nums) < 2:
            return
        try:
            lng = float(nums[0])
            lat = float(nums[1])
        except ValueError:
            return
        out.append({"name": name, "lat": lat, "lng": lng, "folder": folder_name})

    handled_placemarks = set()

    for folder in doc.iter():
        if _local(folder.tag) != "Folder":
            continue
        fname = ""
        for c in folder:
            if _local(c.tag) == "name":
                fname = (c.text or "").strip()
                break
        if any(kw in fname for kw in exclude_folders):
            # 除外層内の Placemark も handled 扱いにして重複防止
            for pm in folder.iter():
                if _local(pm.tag) == "Placemark":
                    handled_placemarks.add(id(pm))
            continue
        for pm in folder.iter():
            if _local(pm.tag) == "Placemark":
                handled_placemarks.add(id(pm))
                emit_placemark(pm, fname)

    # フォルダに属さない Placemark
    for pm in doc.iter():
        if _local(pm.tag) == "Placemark" and id(pm) not in handled_placemarks:
            emit_placemark(pm, "")

    return out


def collect_static(spec: Dict[str, Any], muni: Dict[str, Dict[str, str]], no_geocode: bool) -> List[Dict[str, Any]]:
    """マイマップの無い作品: 検証済み座標を持つ静的 places から生成する。"""
    records: List[Dict[str, Any]] = []
    ts = now_iso()
    for i, place in enumerate(spec["places"], start=1):
        lat = float(place["lat"])
        lng = float(place["lng"])
        city = place.get("city", "")
        address = f"{spec.get('prefecture', '')}{city}{place.get('landmark', '')}"
        if not no_geocode:
            g = gsi_reverse(lat, lng, muni)
            if g["address"]:
                address = g["address"]
            time.sleep(GSI_SLEEP)
        records.append({
            "id": f"{spec['slug']}-{i}",
            "work": spec["work"],
            "title": f"{place.get('landmark', '')}（{place.get('character', '')}）",
            "character": place.get("character", ""),
            "landmark": place.get("landmark", ""),
            "prefecture": spec.get("prefecture", ""),
            "city": city,
            "address": address,
            "lat": lat,
            "lng": lng,
            "source_url": spec["source_url"],
            "map_mid": "",
            "status": "active",
            "first_seen": ts,
            "last_updated": ts,
        })
    print(f"  {spec['work']}: {len(records)} records (static)", file=sys.stderr)
    return records


def collect_ndjson(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """リポジトリ内の手動確認済みNDJSONを読み込む。"""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    source_path = os.path.join(repo_root, spec["path"])
    records: List[Dict[str, Any]] = []
    with open(source_path, encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{source_path}:{line_number}: invalid JSON: {e}") from e
            records.append(record)
    print(f"  {spec['path']}: {len(records)} records (ndjson)", file=sys.stderr)
    return records


def apply_marker_style(record: Dict[str, Any]) -> Dict[str, Any]:
    """作品ごとのマーカー表示情報をレコードへ付与する。"""
    style = MARKER_STYLES.get(record.get("work", ""))
    if style:
        record.update(style)
    return record


def collect_work(spec: Dict[str, Any], muni: Dict[str, Dict[str, str]], no_geocode: bool) -> List[Dict[str, Any]]:
    if spec.get("source_type") == "ndjson":
        return collect_ndjson(spec)
    if spec.get("source_type") == "static":
        return collect_static(spec, muni, no_geocode)
    kml = fetch_text(KML_URL.format(mid=spec["mid"]))
    if not kml:
        print(f"ERROR: KML取得失敗 work={spec['work']} mid={spec['mid']}", file=sys.stderr)
        return []
    pins = parse_kml_placemarks(kml, spec.get("exclude_folders", []))
    records: List[Dict[str, Any]] = []
    ts = now_iso()
    for i, pin in enumerate(pins, start=1):
        parsed = split_name(pin["name"], spec["name_mode"])
        geo = {"prefecture": spec.get("prefecture", ""), "city": "", "address": ""}
        if not no_geocode:
            g = gsi_reverse(pin["lat"], pin["lng"], muni)
            if g["prefecture"] or g["city"]:
                geo = g
            time.sleep(GSI_SLEEP)
        rec = {
            "id": f"{spec['slug']}-{i}",
            "work": spec["work"],
            "title": parsed["title"],
            "character": parsed["character"],
            "landmark": parsed["landmark"],
            "prefecture": geo["prefecture"] or spec.get("prefecture", ""),
            "city": geo["city"] or parsed.get("city_hint", ""),
            "address": geo["address"],
            "lat": pin["lat"],
            "lng": pin["lng"],
            "source_url": spec["source_url"],
            "map_mid": spec["mid"],
            "status": "active",
            "first_seen": ts,
            "last_updated": ts,
        }
        records.append(rec)
    print(f"  {spec['work']}: {len(records)} records", file=sys.stderr)
    return records


def atomic_write_ndjson(path: str, records: List[Dict[str, Any]]) -> None:
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=d, encoding="utf-8") as tmp:
        for rec in records:
            tmp.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        p = tmp.name
    os.replace(p, path)


def default_out_path() -> str:
    """docs/character_manholes.ndjson (semantic editor が読む配信先) を既定にする。"""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(repo_root, "docs", "character_manholes.ndjson")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=default_out_path(), help="出力NDJSONパス (既定: docs/character_manholes.ndjson)")
    ap.add_argument("--no-geocode", action="store_true", help="GSI逆ジオを省略 (prefecture/cityは設定値のみ)")
    args = ap.parse_args()

    muni = {} if args.no_geocode else load_muni_table()
    if not args.no_geocode:
        print(f"muni table: {len(muni)} entries", file=sys.stderr)

    all_records: List[Dict[str, Any]] = []
    for spec in WORKS:
        all_records.extend(collect_work(spec, muni, args.no_geocode))
    for record in all_records:
        apply_marker_style(record)

    atomic_write_ndjson(args.out, all_records)
    print(f"Wrote {len(all_records)} records to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
