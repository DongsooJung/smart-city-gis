#!/usr/bin/env python3
"""
강남구 보행성·15분도시 인터랙티브 대시보드 빌더 (v2).

라이브러리(create_fishnet → compute_walkability → fifteen_min_city_score,
AccessibilityAnalyzer.get_isochrone)를 실제로 호출해:
  - data/actual/*                    OSM 실제 POI·보행망 스냅샷
  - docs/dashboard/index.html        데이터 임베드 단일 대시보드
를 생성한다.

v2 추가:
  - 등시선(isochrone) 레이어: 강남역 기준 5/10/15/20분 도보 도달권 (get_isochrone)
  - 합성 연도 시나리오를 제거하고 최신 실제 OSM 단면만 표시

Usage:
    python scripts/build_dashboard.py
"""
from __future__ import annotations

import json
import sys
import csv
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, box

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from smartcity_gis import (  # noqa: E402
    create_fishnet, compute_walkability, fifteen_min_city_score,
)
from smartcity_gis.accessibility import AccessibilityAnalyzer  # noqa: E402

WGS84 = 4326

# 강남구 핵심부 대략 경계 (경위도)
BBOX = (127.020, 37.480, 127.080, 37.520)
YEARS = [2026]
ISO_ORIGIN = (127.0276, 37.4979)         # 강남역
ISO_TIMES = [5, 10, 15, 20]

def make_boundary() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"name": ["Gangnam station study rectangle"], "geometry": [box(*BBOX)]}, crs=WGS84)


def make_pois() -> gpd.GeoDataFrame:
    path = ROOT / "data" / "actual" / "gangnam_pois.geojson"
    pois = gpd.read_file(path).to_crs(WGS84)
    if 'opening_year' in pois.columns:pois=pois.drop(columns='opening_year')
    return pois


def make_street_graph() -> nx.Graph:
    payload = json.loads((ROOT / "data" / "actual" / "gangnam_walk_graph.json").read_text())
    graph = nx.Graph()
    for node, (lon, lat) in payload["nodes"].items(): graph.add_node(int(node), x=lon, y=lat)
    for a, b, length in payload["edges"]: graph.add_edge(a, b, length=length)
    return graph


def build():
    data_dir = ROOT / "data" / "actual"
    dash_dir = ROOT / "docs" / "dashboard"
    data_dir.mkdir(parents=True, exist_ok=True)
    dash_dir.mkdir(parents=True, exist_ok=True)
    source_metadata=json.loads((data_dir/'metadata.json').read_text(encoding='utf8'))
    source_year=int(source_metadata['fetchedAt'][:4])
    YEARS[:]=[source_year]
    built_at=datetime.now(timezone.utc).isoformat()

    boundary = make_boundary()
    pois = make_pois()
    grid = create_fishnet(boundary, cell_size=250)

    # ---- 최신 OSM 단면 점수 계산 ----
    walk_by_year, s15_by_year, mean_by_year = {}, {}, {}
    for y in YEARS:
        sub = pois
        if len(sub) == 0:
            walk_by_year[y] = [0.0] * len(grid)
            s15_by_year[y] = [0.0] * len(grid)
            mean_by_year[y] = 0.0
            continue
        w = compute_walkability(grid, sub, decay="exponential")["walkability_score"]
        s = fifteen_min_city_score(grid, sub)
        walk_by_year[y] = [round(float(v), 1) for v in w]
        s15_by_year[y] = [round(float(v), 2) for v in s]
        mean_by_year[y] = round(float(w.mean()), 1)

    # 최신연도(2026)를 기준 레이어로
    latest = YEARS[-1]
    walk = grid.copy()
    walk["walkability_score"] = walk_by_year[latest]
    walk["score_15min"] = s15_by_year[latest]
    walk["cell_id"] = grid["cell_id"].values

    # ---- 등시선 (강남역, get_isochrone) ----
    graph = make_street_graph()
    analyzer = AccessibilityAnalyzer(graph)
    iso = analyzer.get_isochrone(ISO_ORIGIN, trip_times=ISO_TIMES, travel_speed=4.5)
    iso_geo = json.loads(iso.isochrones.to_json())

    # ---- 실제 OSM 분석 결과 저장 ----
    boundary.to_file(data_dir / "gangnam_boundary.geojson", driver="GeoJSON")
    pois.to_file(data_dir / "gangnam_pois.geojson", driver="GeoJSON")
    walk[["cell_id", "walkability_score", "score_15min", "geometry"]].to_file(
        data_dir / "gangnam_grid_scores.geojson", driver="GeoJSON"
    )
    iso.isochrones.to_file(data_dir / "gangnam_isochrone_gangnam_stn.geojson", driver="GeoJSON")

    # ---- 대시보드 JSON ----
    grid_geo = json.loads(
        walk[["cell_id", "walkability_score", "score_15min", "geometry"]].to_crs(WGS84).to_json()
    )
    pois_geo = json.loads(pois.to_crs(WGS84).to_json())

    ws = np.array(walk_by_year[latest])
    stats = {
        "n_cells": int(len(walk)),
        "n_pois": int(len(pois)),
        "walk_mean": mean_by_year[latest],
        "walk_max": round(float(ws.max()), 1),
        "score15_mean": round(float(np.mean(s15_by_year[latest])), 2),
        "pct_15min_ok": round(float(np.mean(np.array(s15_by_year[latest]) >= 4) * 100), 1),
        "cat_counts": pois["category"].value_counts().to_dict(),
        "hist": np.histogram(ws, bins=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100])[0].tolist(),
    }
    if not np.isfinite(ws).all() or ((ws<0)|(ws>100)).any():raise ValueError('Invalid walkability score')
    if not all(0<=v<=6 for v in s15_by_year[latest]):raise ValueError('Invalid six-category score')
    if sum(stats['cat_counts'].values())!=stats['n_pois'] or sum(stats['hist'])!=stats['n_cells']:raise ValueError('Totals do not reconcile')
    metadata={**source_metadata,'builtAt':built_at,'observationDate':None,
              'analysis':{'gridMeters':250,'distanceCrs':'EPSG:5186','coordinateCrs':'EPSG:4326','scoreDistance':'Euclidean, not network walking distance','radiusMeters15MinuteScore':1125,'assumedSpeedKmh':4.5,'meanWeighting':'unweighted cells; edge cells intersect study rectangle','isochrone':'undirected selected-highway graph, reachable-node convex hull'},
              'limitations':['강남역 일대 직사각형이며 강남구 행정경계가 아닙니다.','OSM 태그가 있는 노드만 사용하며 시설 전수·way/relation 시설·현장 영업 여부는 미확인입니다.','보행성·6개 생활분류 점수는 직선거리 기반입니다. 15분은 4.5km/h로 환산한 반경1125m 가정입니다.','등시선은 선택 도로망 도달노드의 볼록껍질 근사입니다. 보행 통행권·횡단·출입구 연결을 전수 검증하지 않았습니다.','분석 경계 밖 POI 누락에 따른 가장자리 효과가 있습니다.','POI 식별·범위와 도로 중복 제거가 달라 이전 저장본과 증가율·시계열 비교를 하지 않습니다.']}
    public_data=dash_dir/'data';public_data.mkdir(exist_ok=True)
    for name,obj in [('metadata.json',metadata),('stats.json',stats),('grid.geojson',grid_geo),('pois.geojson',pois_geo),('isochrones.geojson',iso_geo)]:
        (public_data/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2 if name in ['metadata.json','stats.json'] else None)+'\n',encoding='utf8')
    shutil.copyfile(data_dir/'gangnam_walk_graph.json',public_data/'walk-graph.json')
    with (public_data/'grid.csv').open('w',newline='',encoding='utf8') as file:
        writer=csv.writer(file);writer.writerow(['cell_id','walkability_score','score_15min','source_collected_at','file_generated_at','metric_basis'])
        for row in grid_geo['features']:
            props=row['properties'];writer.writerow([props['cell_id'],props['walkability_score'],props['score_15min'],source_metadata['fetchedAt'],built_at,'euclidean_osm_tagged_nodes'])

    html = HTML_TEMPLATE
    repl = {
        "__GRID__": json.dumps(grid_geo, ensure_ascii=False),
        "__POIS__": json.dumps(pois_geo, ensure_ascii=False),
        "__ISO__": json.dumps(iso_geo, ensure_ascii=False),
        "__STATS__": json.dumps(stats, ensure_ascii=False),
        "__WALK_BY_YEAR__": json.dumps(walk_by_year, ensure_ascii=False),
        "__S15_BY_YEAR__": json.dumps(s15_by_year, ensure_ascii=False),
        "__MEAN_BY_YEAR__": json.dumps(mean_by_year, ensure_ascii=False),
        "__YEARS__": json.dumps(YEARS),
        "__ORIGIN__": json.dumps(ISO_ORIGIN),
        "__METADATA__":json.dumps(metadata,ensure_ascii=False),
    }
    for k, v in repl.items():
        html = html.replace(k, v.replace('<','\\u003c'))
    (dash_dir / "index.html").write_text(html, encoding="utf-8")

    print(f"grid cells : {len(walk)}")
    print(f"pois       : {len(pois)}  (연도범위 {min(YEARS)}-{max(YEARS)})")
    print("연도별 평균 보행성:", {y: mean_by_year[y] for y in YEARS})
    print(f"isochrone  : {len(iso.isochrones)} bands @ 강남역 {ISO_TIMES}min")
    print(f"→ {dash_dir / 'index.html'}")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>강남역 일대 보행성 · 생활 접근성 | Smart City GIS</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root{--bg:#0f1419;--panel:#1a2129;--panel2:#222c37;--line:#2e3a46;--ink:#e8edf2;--muted:#8fa0b0;--accent:#4ade80;--accent2:#38bdf8}
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;font-family:'Segoe UI',-apple-system,'Malgun Gothic',sans-serif;background:var(--bg);color:var(--ink)}
  #app{display:grid;grid-template-columns:350px 1fr;grid-template-rows:auto 1fr;height:100vh}
  header{grid-column:1/3;padding:13px 20px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:14px;background:var(--panel)}
  header h1{font-size:17px;margin:0;font-weight:650}
  header .sub{color:var(--muted);font-size:12px}
  aside{border-right:1px solid var(--line);background:var(--panel);overflow-y:auto;padding:15px}
  main{position:relative}
  #map{position:absolute;inset:0}
  .card{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:13px}
  .card h3{margin:0 0 10px;font-size:11.5px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);font-weight:600}
  .stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
  .stat{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
  .stat .v{font-size:19px;font-weight:700;color:var(--accent)}
  .stat .l{font-size:11px;color:var(--muted);margin-top:2px}
  .toggle-row{display:flex;gap:6px;margin-bottom:10px}
  .toggle-row button{flex:1;padding:8px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:8px;cursor:pointer;font-size:12.5px;transition:.15s}
  .toggle-row button.active{background:var(--accent);color:#06210f;border-color:var(--accent);font-weight:650}
  .btn{width:100%;padding:8px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:8px;cursor:pointer;font-size:12.5px;transition:.15s}
  .btn.on{background:var(--accent2);color:#04222e;border-color:var(--accent2);font-weight:650}
  label.chk{display:flex;align-items:center;gap:7px;font-size:12.5px;padding:3px 0;cursor:pointer}
  label.chk .dot{width:10px;height:10px;border-radius:2px;display:inline-block}
  .legend{display:flex;flex-direction:column;gap:4px;font-size:11.5px}
  .legend .row{display:flex;align-items:center;gap:8px}
  .legend .sw{width:26px;height:12px;border-radius:2px}
  canvas{max-width:100%}
  .muted{color:var(--muted);font-size:11.5px;line-height:1.5}
  .leaflet-popup-content-wrapper{background:var(--panel2);color:var(--ink);border-radius:8px}
  .leaflet-popup-tip{background:var(--panel2)}
  .pill{display:inline-block;padding:1px 7px;border-radius:20px;background:var(--panel);border:1px solid var(--line);font-size:11px;color:var(--muted);margin-left:8px}
  .portal-link{margin-left:auto;font-size:12px;color:var(--accent2);text-decoration:none;border:1px solid var(--line);padding:5px 11px;border-radius:8px;transition:.15s;white-space:nowrap}
  .portal-link:hover{background:var(--accent2);color:#04222e;border-color:var(--accent2)}
  .year-head{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:6px}
  .year-head .yr{font-size:26px;font-weight:800;color:var(--accent2)}
  .year-head .ym{font-size:12px;color:var(--muted)}
  input[type=range]{width:100%;accent-color:var(--accent2)}
  .play-row{display:flex;gap:6px;margin-top:8px}
  .play-row button{flex:1;padding:6px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:7px;cursor:pointer;font-size:12px}
  .source-card{overflow-wrap:anywhere;line-height:1.65}.source-card p{font-size:12px;margin:8px 0}.source-card a{color:var(--accent2);text-decoration:underline}.downloads{display:flex;flex-wrap:wrap;gap:7px 12px;font-size:12px}
  @media(max-width:760px){#app{grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(360px,55vh) auto;height:auto}header{grid-column:1;flex-wrap:wrap;min-width:0;padding:12px}header h1{font-size:16px}aside{grid-row:3;border-right:0;min-width:0;overflow-y:visible}main{grid-row:2;min-width:0;min-height:360px}.stat-grid{min-width:0}}
</style>
</head>
<body>
<div id="app">
  <header>
    <h1>강남역 일대 보행성 · 생활 접근성</h1>
    <span class="sub">OSM 태그 노드 단면 · 직선거리 기반 점수 · 도로망 근사권</span>
    <span class="pill" id="modePill">보행성 지수</span>
    <a class="portal-link" href="https://stargateedu.co.kr/research/" target="_blank" rel="noopener">← STARGATE 연구 대시보드</a>
  </header>

  <aside>
    <div class="card">
      <h3>지표 선택</h3>
      <div class="toggle-row">
        <button id="btnWalk" class="active" onclick="setMode('walk')">보행성 0–100</button>
        <button id="btn15" onclick="setMode('s15')">생활 접근 0–6</button>
      </div>
      <div class="legend" id="legend"></div>
    </div>

    <div class="card">
      <h3>실데이터 스냅샷</h3>
      <div class="year-head"><span class="yr" id="yrLabel">2026</span>
        <span class="ym" id="yrMean">평균 보행성 —</span></div>
      <p class="muted" style="margin:8px 0 0">OpenStreetMap 태그 노드의 수집 단면입니다. 수집일은 현장 관측일·개소연도·월간 통계 기준이 아닙니다.</p>
    </div>

    <section class="card source-card" id="source-review" aria-labelledby="source-title">
      <h3 id="source-title">자료 기준·계산 범위</h3>
      <p id="source-dates"></p><p id="source-database"></p>
      <p>강남역 주변 직사각형(동경127.020~127.080·북위37.480~37.520)입니다. 강남구 행정경계가 아닙니다. OSM에 태그가 있는 노드만 세며 시설 전수나 실제 영업 여부를 뜻하지 않습니다.</p>
      <p>보행성·생활 접근 점수는 직선거리 기반입니다. 15분은 속도4.5km/h·반경1125m 가정이며 실제 도보시간을 검증한 값이 아닙니다. 경계 밖 POI 누락의 영향과 원자료 갱신 지연이 있습니다.</p>
      <p>등시선은 선택 도로망 도달노드의 볼록껍질 근사입니다. 통행권·횡단·출입구 연결은 미확인입니다. 이전 저장본과 수집 범위·중복 제거 방식이 달라 증가율로 비교하지 않습니다.</p>
      <div class="downloads"><a href="data/metadata.json" download>출처·수집시각 JSON</a><a href="data/grid.csv" download>격자 CSV</a><a href="data/grid.geojson" download>격자 GeoJSON</a><a href="data/pois.geojson" download>POI 노드</a><a href="data/walk-graph.json" download>도로망</a><a href="data/isochrones.geojson" download>근사권</a><a href="data/stats.json" download>요약 JSON</a></div>
      <p><a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors · ODbL</a></p>
    </section>

    <div class="card">
      <h3>선택 도로망 근사 도달권</h3>
      <button id="isoBtn" class="btn" onclick="toggleIso()">⏱ 등시선 표시 (5·10·15·20분)</button>
      <div class="legend" id="isoLegend" style="margin-top:10px;display:none"></div>
    </div>

    <div class="card">
      <h3>요약 통계</h3>
      <div class="stat-grid" id="stats"></div>
    </div>

    <div class="card">
      <h3>보행성 점수 분포 (현재 스냅샷)</h3>
      <canvas id="hist" height="150"></canvas>
    </div>

    <div class="card">
      <h3>POI 카테고리 (표시 토글)</h3>
      <div id="poiToggles"></div>
    </div>
  </aside>

  <main><div id="map"></div></main>
</div>

<script>
const GRID = __GRID__;
const POIS = __POIS__;
const ISO  = __ISO__;
const STATS = __STATS__;
const WALK_BY_YEAR = __WALK_BY_YEAR__;
const S15_BY_YEAR  = __S15_BY_YEAR__;
const MEAN_BY_YEAR = __MEAN_BY_YEAR__;
const YEARS = __YEARS__;
const ORIGIN = __ORIGIN__;
const META = __METADATA__;
const safeText=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

const CAT_COLORS = {
  cafe:'#f59e0b', restaurant:'#ef4444', grocery:'#22c55e', shopping:'#a855f7',
  school:'#3b82f6', hospital:'#ec4899', park:'#10b981', library:'#14b8a6',
  subway:'#eab308', bus_stop:'#94a3b8'
};
const ISO_COLORS = {5:'#38bdf8',10:'#22c55e',15:'#eab308',20:'#f97316'};

let mode='walk';
let yearIdx = YEARS.length-1;
let playTimer=null;

const map = L.map('map',{zoomControl:true}).setView([37.500,127.050],13);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  {attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',maxZoom:19}).addTo(map);

function rampWalk(v){
  const s=[[255,255,229],[247,252,185],[217,240,163],[173,221,142],[120,198,121],[65,171,93],[35,132,67],[0,104,55],[0,69,41]];
  const t=Math.max(0,Math.min(1,v/100))*(s.length-1),i=Math.floor(t),f=t-i,a=s[i],b=s[Math.min(i+1,s.length-1)];
  return `rgb(${Math.round(a[0]+(b[0]-a[0])*f)},${Math.round(a[1]+(b[1]-a[1])*f)},${Math.round(a[2]+(b[2]-a[2])*f)})`;
}
function ramp15(v){
  const s=[[215,48,39],[252,141,89],[254,224,139],[217,239,139],[145,207,96],[26,152,80]];
  const t=Math.max(0,Math.min(1,v/6))*(s.length-1),i=Math.floor(t),f=t-i,a=s[i],b=s[Math.min(i+1,s.length-1)];
  return `rgb(${Math.round(a[0]+(b[0]-a[0])*f)},${Math.round(a[1]+(b[1]-a[1])*f)},${Math.round(a[2]+(b[2]-a[2])*f)})`;
}

function yearKey(){ return String(YEARS[yearIdx]); }
function walkVal(i){ return WALK_BY_YEAR[yearKey()][i]; }
function s15Val(i){ return S15_BY_YEAR[yearKey()][i]; }
function valOf(p){ const i=p.cell_id; return mode==='walk'? walkVal(i) : s15Val(i); }
function colorOf(p){ return mode==='walk'? rampWalk(walkVal(p.cell_id)) : ramp15(s15Val(p.cell_id)); }

const gridLayer = L.geoJSON(GRID,{
  style:f=>({fillColor:colorOf(f.properties),weight:.4,color:'#0f1419',fillOpacity:.72}),
  onEachFeature:(f,l)=>{
    l.on('click',()=>{const i=f.properties.cell_id;
      l.bindPopup(`<b>셀 #${i}</b> · ${META.fetchedAt.slice(0,10)} 수집<br>보행성: <b>${walkVal(i)}</b>/100<br>직선거리 생활 접근: <b>${s15Val(i)}</b>/6`).openPopup();});
    l.on('mouseover',()=>l.setStyle({weight:1.6,color:'#fff'}));
    l.on('mouseout',()=>l.setStyle({weight:.4,color:'#0f1419'}));
  }
}).addTo(map);

// ---- 등시선 레이어 ----
const isoLayer = L.geoJSON(ISO,{
  style:f=>({color:ISO_COLORS[f.properties.minutes]||'#fff',weight:2,fillColor:ISO_COLORS[f.properties.minutes]||'#fff',fillOpacity:.14}),
  onEachFeature:(f,l)=>l.bindPopup(`강남역 도보 <b>${f.properties.minutes}분</b> 도달권`)
});
const originMarker = L.circleMarker([ORIGIN[1],ORIGIN[0]],{radius:6,color:'#fff',weight:2,fillColor:'#38bdf8',fillOpacity:1}).bindPopup('강남역 (등시선 기준점)');
let isoOn=false;
function toggleIso(){
  isoOn=!isoOn;
  const btn=document.getElementById('isoBtn'), lg=document.getElementById('isoLegend');
  if(isoOn){ isoLayer.addTo(map); originMarker.addTo(map); btn.classList.add('on'); lg.style.display='flex'; }
  else { map.removeLayer(isoLayer); map.removeLayer(originMarker); btn.classList.remove('on'); lg.style.display='none'; }
}
function renderIsoLegend(){
  document.getElementById('isoLegend').innerHTML =
    [5,10,15,20].map(m=>`<div class="row"><span class="sw" style="background:${ISO_COLORS[m]};opacity:.6"></span>${m}분 도보</div>`).join('');
}

// ---- POI 레이어 ----
const poiLayers={};
Object.keys(CAT_COLORS).forEach(c=>poiLayers[c]=L.layerGroup());
POIS.features.forEach(f=>{
  const cat=f.properties.category, c=f.geometry.coordinates;
  const m=L.circleMarker([c[1],c[0]],{radius:3.4,color:CAT_COLORS[cat]||'#888',weight:1,fillColor:CAT_COLORS[cat]||'#888',fillOpacity:.9});
  m.bindPopup(`<b>${safeText(cat)}</b> · OSM 태그 노드${f.properties.name?`<br>${safeText(f.properties.name)}`:''}`);
  if(poiLayers[cat]) poiLayers[cat].addLayer(m);
});

function restyleGrid(){ gridLayer.setStyle(f=>({fillColor:colorOf(f.properties),weight:.4,color:'#0f1419',fillOpacity:.72})); }

function setMode(m){
  mode=m;
  document.getElementById('btnWalk').classList.toggle('active',m==='walk');
  document.getElementById('btn15').classList.toggle('active',m==='s15');
  document.getElementById('modePill').textContent = m==='walk'?'보행성 지수':'직선거리 생활 접근';
  restyleGrid(); renderLegend(); renderHist();
}

function refreshYear(){
  const y=YEARS[yearIdx];
  document.getElementById('yrLabel').textContent=META.fetchedAt.slice(0,10)+' 수집';
  document.getElementById('yrMean').textContent='평균 보행성 '+MEAN_BY_YEAR[String(y)];
  restyleGrid(); renderHist(); renderStats();
}
function renderLegend(){
  const el=document.getElementById('legend'); const rows=[];
  const stops = mode==='walk'? [0,20,40,60,80,100] : [0,1,2,3,4,5,6];
  const rf = mode==='walk'? rampWalk : ramp15;
  for(let i=0;i<stops.length-1;i++)
    rows.push(`<div class="row"><span class="sw" style="background:${rf((stops[i]+stops[i+1])/2)}"></span>${stops[i]}–${stops[i+1]}</div>`);
  el.innerHTML=rows.join('');
}

function renderStats(){
  const y=String(YEARS[yearIdx]);
  const wy=WALK_BY_YEAR[y], sy=S15_BY_YEAR[y];
  const mean=MEAN_BY_YEAR[y];
  const mx=Math.max(...wy).toFixed(1);
  const s15m=(sy.reduce((a,b)=>a+b,0)/sy.length).toFixed(2);
  const ok=(sy.filter(v=>v>=4).length/sy.length*100).toFixed(1);
  const cards=[[mean,'평균 보행성'],[mx,'최고 보행성'],[s15m,'평균 생활 접근'],[ok+'%','직선거리 충족셀(≥4)'],[STATS.n_cells,'격자수'],[STATS.n_pois,'표본 POI 노드']];
  document.getElementById('stats').innerHTML=cards.map(c=>`<div class="stat"><div class="v">${c[0]}</div><div class="l">${c[1]}</div></div>`).join('');
}

let histChart=null;
function renderHist(){
  const y=String(YEARS[yearIdx]); const wy=WALK_BY_YEAR[y];
  const bins=new Array(10).fill(0);
  wy.forEach(v=>{let b=Math.min(9,Math.floor(v/10)); bins[b]++;});
  const labels=Array.from({length:10},(_,i)=>i*10+'–'+((i+1)*10));
  if(histChart) histChart.destroy();
  histChart=new Chart(document.getElementById('hist'),{type:'bar',
    data:{labels,datasets:[{data:bins,backgroundColor:labels.map((_,i)=>rampWalk(i*10+5))}]},
    options:{plugins:{legend:{display:false}},scales:{
      x:{ticks:{color:'#8fa0b0',font:{size:9},maxRotation:60,minRotation:60},grid:{display:false}},
      y:{ticks:{color:'#8fa0b0'},grid:{color:'#2e3a46'}}}}});
}

function renderPoiToggles(){
  document.getElementById('poiToggles').innerHTML=Object.keys(CAT_COLORS).map(cat=>{
    const n=STATS.cat_counts[cat]||0;
    return `<label class="chk"><input type="checkbox" data-cat="${cat}" onchange="togglePoi(this)">
      <span class="dot" style="background:${CAT_COLORS[cat]}"></span>${cat} <span class="pill">${n}</span></label>`;
  }).join('');
}
function togglePoi(cb){const cat=cb.dataset.cat; if(cb.checked) poiLayers[cat].addTo(map); else map.removeLayer(poiLayers[cat]);}

// init
document.getElementById('source-dates').textContent='수집 완료(UTC) '+META.fetchedAt+' · 계산 파일 생성(UTC) '+META.builtAt+' · 현장 관측일 미확인';
document.getElementById('source-database').textContent='원자료 DB 기준(UTC): '+([...new Set((META.sourceResponses||[]).map(r=>r.osmBaseTimestamp))].join(' / ')||'이전 수집본 미기록')+' · 응답들의 수집 단면이며 동시 관측 전수조사가 아닙니다.';
renderLegend(); renderIsoLegend(); renderStats(); renderHist(); renderPoiToggles(); refreshYear();
map.fitBounds(gridLayer.getBounds(),{padding:[20,20]});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    build()
