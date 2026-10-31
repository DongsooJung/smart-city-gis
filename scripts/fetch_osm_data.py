#!/usr/bin/env python3
"""Receive OSM node POIs and selected highway centerlines from read-only Overpass."""

from __future__ import annotations

import json
import math
import argparse
import hashlib
import os
import subprocess
import tempfile
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

def request_map(bbox: str, raw_dir: Path) -> tuple[ET.Element, dict]:
    query = (f'[out:xml][timeout:60];('
             f'node({bbox})[amenity~"^(cafe|restaurant|fast_food|school|kindergarten|college|university|hospital|clinic|doctors|pharmacy|library)$"];'
             f'node({bbox})[leisure~"^(park|garden|playground)$"];'
             f'node({bbox})[railway~"^(station|subway_entrance)$"];'
             f'node({bbox})[highway=bus_stop];node({bbox})[public_transport=platform];node({bbox})[shop];'
             f'way({bbox})[highway~"^(primary|secondary|tertiary|residential|unclassified|service|living_street|pedestrian|footway|path|steps)$"];'
             ');(._;>;);out meta;')
    url = "https://overpass-api.de/api/interpreter"
    started = datetime.now(timezone.utc).isoformat()
    raw_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["curl", "-fLsS", "--max-time", "80", "--user-agent", "StargateResearchGIS/0.3 (https://stargateedu.co.kr/research/)",
         "--get", "--data-urlencode", "data="+query, url],
        check=False, capture_output=True,
    )
    received = datetime.now(timezone.utc).isoformat()
    if result.returncode:
        error=result.stderr.decode('utf8',errors='replace')[-600:]
        failure={'url':url,'query':query,'startedAt':started,'failedAt':received,'curlReturnCode':result.returncode,'error':error}
        (raw_dir/(bbox.replace(',','_')+'.failure.json')).write_text(json.dumps(failure,indent=2)+'\n',encoding='utf8')
        raise RuntimeError(f'OSM request failed: {error.strip()}; existing snapshot retained')
    (raw_dir / (bbox.replace(',', '_')+'.osm.xml')).write_bytes(result.stdout)
    root = ET.fromstring(result.stdout)
    if root.tag != 'osm' or root.find('remark') is not None or root.find('error') is not None:
        raise ValueError('Incomplete OSM response; existing snapshot retained')
    meta = root.find('meta')
    osm_base = meta.get('osm_base') if meta is not None else None
    if not osm_base or not root.findall('node') or not root.findall('way'):
        raise ValueError('Missing source timestamp/nodes/ways')
    receipt={'url':url,'method':'GET','query':query,'bbox':bbox,'startedAt':started,
                  'receivedAt':received,'osmBaseTimestamp':osm_base,
                  'bytes':len(result.stdout),'sha256':hashlib.sha256(result.stdout).hexdigest()}
    (raw_dir/(bbox.replace(',','_')+'.receipt.json')).write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    return root,receipt


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
    features, seen = [], {}
    south,west,north,east=map(float,BBOX.split(','))
    for element in (element for payload in payloads for element in payload.findall("node")):
        tags = tags_of(element)
        cat = category(tags)
        lon, lat = float(element.attrib["lon"]), float(element.attrib["lat"])
        key=element.attrib['id'];signature=(lon,lat,tuple(sorted(tags.items())))
        if key in seen:
            if seen[key]!=signature:raise ValueError('Conflicting node across source responses')
            continue
        seen[key]=signature
        if not cat or not (west<=lon<=east and south<=lat<=north):continue
        features.append({"type": "Feature", "properties": {"osm_id": element.attrib["id"],
            "osm_type": "node", "category": cat, "name": tags.get("name")},
            "geometry": {"type": "Point", "coordinates": [lon, lat]}})
    return {"type": "FeatureCollection", "features": features}


def graph(payloads: list[ET.Element]) -> dict:
    nodes, ways, seen_edges = {}, {}, set()
    edges = []
    for payload in payloads:
      for node in payload.findall("node"):
        key=int(node.attrib['id']);point=[float(node.attrib['lon']),float(node.attrib['lat'])]
        if key in nodes and nodes[key]!=point:raise ValueError('Conflicting road node coordinates')
        nodes[key]=point
      for way in payload.findall("way"):
        highway = tags_of(way).get("highway")
        if highway not in {"primary", "secondary", "tertiary", "residential", "unclassified", "service",
                            "living_street", "pedestrian", "footway", "path", "steps"}: continue
        key=way.attrib['id'];refs=[int(nd.attrib['ref']) for nd in way.findall('nd')]
        if key in ways and ways[key]!=refs:raise ValueError('Conflicting way across source responses')
        ways[key]=refs
    for refs in ways.values():
        for a, b in zip(refs, refs[1:]):
            if a not in nodes or b not in nodes:raise ValueError('Incomplete way nodes')
            key=tuple(sorted((a,b)))
            if key in seen_edges:continue
            seen_edges.add(key)
            lon1, lat1 = nodes[a]; lon2, lat2 = nodes[b]
            dy = math.radians(lat2 - lat1); dx = math.radians(lon2 - lon1)
            h = math.sin(dy/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dx/2)**2
            length = 6371000 * 2 * math.atan2(math.sqrt(h), math.sqrt(1-h))
            if round(length,2)>0:edges.append([a, b, round(length, 2)])
    used = {n for edge in edges for n in edge[:2]}
    return {"nodes": {str(k): v for k, v in nodes.items() if k in used}, "edges": edges}


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument('--raw-dir',type=Path,default=ROOT/'data/raw/osm');args=parser.parse_args()
    fetched=[request_map(b,args.raw_dir) for b in ROAD_BBOXES]
    payloads,receipts=zip(*fetched)
    poi_data = pois(payloads)
    road_data = graph(payloads)
    if not poi_data['features'] or not road_data['edges']:raise ValueError('Empty source snapshot')
    for feature in poi_data['features']:
        if not all(math.isfinite(v) for v in feature['geometry']['coordinates']):raise ValueError('Non-finite POI coordinates')
    if not all(all(math.isfinite(v) for v in point) for point in road_data['nodes'].values()):raise ValueError('Non-finite road coordinates')
    if not all(math.isfinite(edge[2]) and edge[2]>0 for edge in road_data['edges']):raise ValueError('Invalid edge length')
    meta = {"sourceMode": "overpass-osm", "source": "OpenStreetMap contributors (ODbL)",
            "fetchedAt": max(r['receivedAt'] for r in receipts), "bbox": BBOX, "poiCount": len(poi_data["features"]),
            "nodeCount": len(road_data["nodes"]), "edgeCount": len(road_data["edges"]),
            "observationDate":None,"sourceResponses":list(receipts),"scope":"OSM tagged node POIs within the study rectangle; distinct node IDs, not unique real-world facilities. Selected highway centerlines; ways/relations are not POIs.",
            "methodVersion":"osm-node-ids-rectangle-v2","comparability":"Previous coordinate/category-deduplicated counts are not a comparable time series.",
            "graphLimitations":"Undirected selected-highway graph; foot/access restrictions, crossings and connectivity to actual entrances not verified."}
    OUT.mkdir(parents=True, exist_ok=True)
    # Validate all four responses before replacing any published input.
    with tempfile.TemporaryDirectory(dir=OUT) as tmp:
        for name,data in [('gangnam_pois.geojson',poi_data),('gangnam_walk_graph.json',road_data),('metadata.json',meta)]:
            f=Path(tmp)/name;f.write_text(json.dumps(data,ensure_ascii=False,indent=2 if name=='metadata.json' else None)+'\n',encoding='utf8')
        for name in ['gangnam_pois.geojson','gangnam_walk_graph.json','metadata.json']:os.replace(Path(tmp)/name,OUT/name)
    print(meta)


if __name__ == "__main__": main()
