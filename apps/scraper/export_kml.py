#!/usr/bin/env python3
"""Convert pokefuta.ndjson into a KML snapshot."""

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

KML_NS = "http://www.opengis.net/kml/2.2"
ET.register_namespace("", KML_NS)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="apps/scraper/pokefuta.ndjson",
        help="Path to the source NDJSON file",
    )
    parser.add_argument(
        "--output",
        default="docs/pokefuta.kml",
        help="Path where the generated KML will be written",
    )
    parser.add_argument(
        "--include-deleted",
        action="store_true",
        help="Include records whose status is not active",
    )
    parser.add_argument(
        "--document-name",
        default="Pokéfuta Manholes",
        help="<Document><name> value for the KML output",
    )
    return parser.parse_args()


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_records(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"NDJSON file not found: {path}")
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            records.append(obj)
    return records


def _format_name(record: Dict[str, Any]) -> str:
    title = (record.get("title") or "").strip()
    fallback = f"Pokéfuta #{record.get('id', '?')}"
    pokemons = record.get("pokemons") or []
    if isinstance(pokemons, list) and pokemons:
        pokemon_summary = ", ".join(str(p) for p in pokemons if p)
        if pokemon_summary:
            return f"{title or fallback} ({pokemon_summary})"
    return title or fallback


def _format_description(record: Dict[str, Any]) -> str:
    br = "<br/>"
    lines: List[str] = []

    def _add(label: str, value: Optional[Any]) -> None:
        if value is None:
            return
        if isinstance(value, list):
            filtered = [str(v) for v in value if v]
            if not filtered:
                return
            safe_value = html.escape(", ".join(filtered))
        else:
            value_str = str(value).strip()
            if not value_str:
                return
            safe_value = html.escape(value_str)
        lines.append(f"<strong>{label}:</strong> {safe_value}{br}")

    pref = record.get("prefecture")
    city = record.get("city")
    location_vals = [str(v).strip() for v in [pref, city] if v]
    if location_vals:
        lines.append(
            f"<strong>Location:</strong> {html.escape(' / '.join(location_vals))}{br}"
        )

    pokemons = record.get("pokemons")
    if isinstance(pokemons, list) and pokemons:
        _add("Pokémon", pokemons)

    _add("Address", record.get("address") or record.get("address_norm"))
    _add("Place Detail", record.get("place_detail"))
    _add("Building", record.get("building"))
    _add("Tags", record.get("tags"))

    detail_url = record.get("detail_url")
    if detail_url:
        safe_url = html.escape(str(detail_url), quote=True)
        lines.append(
            f'<strong>Detail:</strong> <a href="{safe_url}" target="_blank" rel="noreferrer noopener">公式サイト</a>{br}'
        )

    lat = record.get("lat")
    lng = record.get("lng")
    if lat is not None and lng is not None:
        safe_lat = html.escape(str(lat))
        safe_lng = html.escape(str(lng))
        map_url = f"https://www.google.com/maps/search/?api=1&query={safe_lat},{safe_lng}"
        lines.append(
            f'<strong>Map:</strong> <a href="{map_url}" target="_blank" rel="noreferrer noopener">Open in Google Maps</a>{br}'
        )

    _add("Last Updated", record.get("last_updated"))
    _add("Status", record.get("status"))

    if record.get("id") is not None:
        lines.append(f"<em>ID: {html.escape(str(record['id']))}</em>{br}")

    if not lines:
        return "<em>No metadata</em>"
    return "\n".join(lines)


def _indent(elem: ET.Element, level: int = 0) -> None:
    indent = "\n" + "  " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = indent + "  "
        child_count = len(elem)
        for index, child in enumerate(elem):
            _indent(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = indent + ("  " if index < child_count - 1 else "")
        if not elem.tail or not elem.tail.strip():
            elem.tail = indent
    else:
        if not elem.tail or not elem.tail.strip():
            elem.tail = indent


def build_kml(records: List[Dict[str, Any]], *, include_deleted: bool, document_name: str) -> ET.ElementTree:
    kml = ET.Element(f"{{{KML_NS}}}kml")
    document = ET.SubElement(kml, f"{{{KML_NS}}}Document")
    name_elem = ET.SubElement(document, f"{{{KML_NS}}}name")
    name_elem.text = document_name + (" (all statuses)" if include_deleted else " (active only)")

    def record_sort_key(rec: Dict[str, Any]):
        try:
            rid = int(rec.get("id", 0))
        except (TypeError, ValueError):
            rid = 0
        return (rid, rec.get("title") or "")

    for record in sorted(records, key=record_sort_key):
        status = record.get("status", "active")
        if not include_deleted and status != "active":
            continue
        lat = _safe_float(record.get("lat"))
        lng = _safe_float(record.get("lng"))
        if lat is None or lng is None:
            continue

        placemark = ET.SubElement(document, f"{{{KML_NS}}}Placemark")
        name = ET.SubElement(placemark, f"{{{KML_NS}}}name")
        name.text = _format_name(record)

        description = ET.SubElement(placemark, f"{{{KML_NS}}}description")
        description.text = _format_description(record)

        point = ET.SubElement(placemark, f"{{{KML_NS}}}Point")
        coordinates = ET.SubElement(point, f"{{{KML_NS}}}coordinates")
        coordinates.text = f"{lng},{lat},0"

    _indent(kml)
    return ET.ElementTree(kml)


def main() -> None:
    args = _parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records = _load_records(input_path)
    tree = build_kml(records, include_deleted=args.include_deleted, document_name=args.document_name)
    xml_bytes = ET.tostring(tree.getroot(), encoding="utf-8", xml_declaration=True)
    xml_text = xml_bytes.decode("utf-8")
    xml_text = _wrap_description_cdata(xml_text)
    output_path.write_text(xml_text, encoding="utf-8")
    print(f"Wrote {output_path}")


def _wrap_description_cdata(xml_text: str) -> str:
    pattern = re.compile(r"(<description>)(.*?)(</description>)", re.S)

    def _replace(match: re.Match[str]) -> str:
        inner = match.group(2)
        unescaped = html.unescape(inner)
        return f"{match.group(1)}<![CDATA[{unescaped}]]>{match.group(3)}"

    return pattern.sub(_replace, xml_text)


if __name__ == "__main__":
    main()
