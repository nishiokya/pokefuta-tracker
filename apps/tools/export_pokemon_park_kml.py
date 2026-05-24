#!/usr/bin/env python3
"""Convert dataset/pokemon_park.tsv entries into a KML snapshot."""

import argparse
import csv
from pathlib import Path
from typing import Dict, Iterable, List, Optional
import xml.etree.ElementTree as ET

KML_NS = "http://www.opengis.net/kml/2.2"
ET.register_namespace("", KML_NS)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="dataset/pokemon_park.tsv",
        help="Path to the source TSV file",
    )
    parser.add_argument(
        "--output",
        default="docs/pokemon_park.kml",
        help="Path where the generated KML will be written",
    )
    parser.add_argument(
        "--document-name",
        default="Pokemon Park Installations",
        help="<Document><name> value for the KML output",
    )
    return parser.parse_args()


def _safe_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"TSV file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [row for row in reader if any(row.values())]


def _format_description(row: Dict[str, str]) -> str:
    parts: List[str] = []
    if row.get("pref_name"):
        parts.append(f"Prefecture: {row['pref_name']}")
    if row.get("city"):
        parts.append(f"City: {row['city']}")
    if row.get("pokemon"):
        parts.append(f"Pokemon: {row['pokemon']}")
    if row.get("park_series"):
        parts.append(f"Series: {row['park_series']}")
    if row.get("status"):
        parts.append(f"Status: {row['status']}")
    if row.get("open_date"):
        parts.append(f"Open Date: {row['open_date']}")
    if row.get("official_url"):
        parts.append(f"Official: {row['official_url']}")
    if row.get("note"):
        parts.append(f"Note: {row['note']}")
    return "\n".join(parts)


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


def _build_kml(rows: Iterable[Dict[str, str]], document_name: str) -> ET.ElementTree:
    kml = ET.Element(f"{{{KML_NS}}}kml")
    document = ET.SubElement(kml, f"{{{KML_NS}}}Document")
    name_elem = ET.SubElement(document, f"{{{KML_NS}}}name")
    name_elem.text = document_name

    for row in rows:
        lat = _safe_float(row.get("lat", ""))
        lng = _safe_float(row.get("lng", ""))
        if lat is None or lng is None:
            continue

        placemark = ET.SubElement(document, f"{{{KML_NS}}}Placemark")
        name = ET.SubElement(placemark, f"{{{KML_NS}}}name")
        display_name = row.get("name") or row.get("id") or "Pokemon Park"
        name.text = display_name

        description = ET.SubElement(placemark, f"{{{KML_NS}}}description")
        description.text = _format_description(row)

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

    rows = _load_rows(input_path)
    tree = _build_kml(rows, document_name=args.document_name)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
