#!/usr/bin/env python3
"""강남 핵심부 OSM POI와 실제 보행로를 Overpass에서 내려받는다."""

from __future__ import annotations

import json
import math
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "actual"
BBOX = "37.480,127.020,37.520,127.080"
ROAD_BBOXES = [
    "37.480,127.020,37.500,127.050", "37.480,127.050,37.500,127.080",
    "37.500,127.020,37.520,127.050", "37.500,127.050,37.520,127.080",
]

def request_map(bbox: str) -> ET.Element:
    south, west, north, east = bbox.split(",")
    url = f"https://api.openstreetmap.org/api/0.6/map?bbox={west},{south},{east},{north}"
    result = subprocess.run(
        ["curl", "-fLsS", "--retry", "3", "--retry-delay", "3", "--max-time", "120", url],
        check=True, capture_output=True,
    )
    return ET.fromstring(result.stdout)


def category(tags: dict) -> str | None:
    amenity = tags.get("amenity")
    if amenity == "cafe": return "cafe"
    if amenity in {"restaurant", "fast_food"}: return "restaurant"
    if amenity in {"school", "kindergarten", "college", "university"}: return "school"
    if amenity in {"hospital", "clinic", "doctors", "pharmacy"}: return "hospital"
    if amenity == "library": return "library"
    if tags.get("leisure") in {"park", "garden", "playground"}: return "park"
    if tags.get("railway") in {"station", "subway_entrance"}: return "subway"
    if tags.get("highway") == "bus_stop" or tags.get("public_transport") == "platform": return "bus_stop"
    if tags.get("shop") in {"supermarket", "convenience", "greengrocer"}: return "grocery"
    if tags.get("shop"): return "shopping"
    return None


def tags_of(element: ET.Element) -> dict:
    return {tag.attrib["k"]: tag.attrib["v"] for tag in element.findall("tag")}


def pois(payloads: list[ET.Element]) -> dict:
    features, seen = [], set()
    for element in (element for payload in payloads for element in payload.findall("node")):
        tags = tags_of(element)
        cat = category(tags)
        lon, lat = float(element.attrib["lon"]), float(element.attrib["lat"])
        key = (round(lon, 6), round(lat, 6), cat)
        if not cat or lon is None or lat is None or key in seen: continue
        seen.add(key)
        features.append({"type": "Feature", "properties": {"osm_id": element.attrib["id"],
            "osm_type": "node", "category": cat, "name": tags.get("name")},
            "geometry": {"type": "Point", "coordinates": [lon, lat]}})
    return {"type": "FeatureCollection", "features": features}


def graph(payloads: list[ET.Element]) -> dict:
    nodes = {}
    edges = []
    for payload in payloads:
      for node in payload.findall("node"):
        nodes[int(node.attrib["id"])] = [float(node.attrib["lon"]), float(node.attrib["lat"])]
      for way in payload.findall("way"):
        highway = tags_of(way).get("highway")
        if highway not in {"primary", "secondary", "tertiary", "residential", "unclassified", "service",
                            "living_street", "pedestrian", "footway", "path", "steps"}: continue
        refs = [int(nd.attrib["ref"]) for nd in way.findall("nd")]
        for a, b in zip(refs, refs[1:]):
            if a not in nodes or b not in nodes: continue
            lon1, lat1 = nodes[a]; lon2, lat2 = nodes[b]
            dy = math.radians(lat2 - lat1); dx = math.radians(lon2 - lon1)
            h = math.sin(dy/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dx/2)**2
            length = 6371000 * 2 * math.atan2(math.sqrt(h), math.sqrt(1-h))
            edges.append([a, b, round(length, 2)])
    used = {n for edge in edges for n in edge[:2]}
    return {"nodes": {str(k): v for k, v in nodes.items() if k in used}, "edges": edges}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payloads = [request_map(b) for b in ROAD_BBOXES]
    poi_data = pois(payloads)
    road_data = graph(payloads)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (OUT / "gangnam_pois.geojson").write_text(json.dumps(poi_data, ensure_ascii=False), encoding="utf-8")
    (OUT / "gangnam_walk_graph.json").write_text(json.dumps(road_data), encoding="utf-8")
    meta = {"sourceMode": "openstreetmap-api", "source": "OpenStreetMap contributors (ODbL)",
            "fetchedAt": stamp, "bbox": BBOX, "poiCount": len(poi_data["features"]),
            "nodeCount": len(road_data["nodes"]), "edgeCount": len(road_data["edges"])}
    (OUT / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(meta)


if __name__ == "__main__": main()
