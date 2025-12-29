#!/usr/bin/env python3
"""Convert pokefuta.ndjson into a KML snapshot."""

import argparse
import json
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
    pieces: List[str] = []
    if record.get("prefecture"):
        pieces.append(f"Prefecture: {record['prefecture']}")
    if record.get("city"):
        pieces.append(f"City: {record['city']}")
    if record.get("address"):
        pieces.append(f"Address: {record['address']}")
    elif record.get("address_norm"):
        pieces.append(f"Address: {record['address_norm']}")
    if record.get("place_detail"):
        pieces.append(f"Place Detail: {record['place_detail']}")
    if record.get("building"):
        pieces.append(f"Building: {record['building']}")
    if record.get("tags"):
        tags = record['tags']
        if isinstance(tags, list) and tags:
            pieces.append("Tags: " + ", ".join(str(tag) for tag in tags if tag))
    if record.get("detail_url"):
        pieces.append(f"Detail: {record['detail_url']}")
    if record.get("last_updated"):
        pieces.append(f"Last Updated: {record['last_updated']}")
    if record.get("status"):
        pieces.append(f"Status: {record['status']}")
    return "\n".join(pieces)


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
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
