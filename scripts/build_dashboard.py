#!/usr/bin/env python3
"""
강남구 보행성·15분도시 인터랙티브 대시보드 빌더 (v2).

라이브러리(create_fishnet → compute_walkability → fifteen_min_city_score,
AccessibilityAnalyzer.get_isochrone)를 실제로 호출해:
  - data/sample/*.geojson            재현용 샘플 데이터
  - docs/dashboard/index.html        데이터 임베드 단일 대시보드
를 생성한다.

v2 추가:
  - 등시선(isochrone) 레이어: 강남역 기준 5/10/15/20분 도보 도달권 (get_isochrone)
  - 시계열 슬라이더: POI 개소 연도(2019–2026) 기반 개발 시나리오로
    연도별 보행성/15분점수를 재계산해 연도 이동 시 지도 갱신

Usage:
    python scripts/build_dashboard.py
"""
from __future__ import annotations

import json
import sys
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
SEED = 42

# 강남구 핵심부 대략 경계 (경위도)
BBOX = (127.020, 37.480, 127.080, 37.520)
YEARS = list(range(2019, 2027))          # 2019 ~ 2026
ISO_ORIGIN = (127.0276, 37.4979)         # 강남역
ISO_TIMES = [5, 10, 15, 20]

# 역세권 클러스터 중심 (lon, lat, 상대밀도)
CLUSTERS = [
    (127.0276, 37.4979, 1.4),   # 강남역
    (127.0364, 37.5008, 1.1),   # 역삼역
    (127.0230, 37.5045, 1.0),   # 신논현역
    (127.0559, 37.5088, 1.2),   # 삼성역/코엑스
    (127.0473, 37.5040, 0.9),   # 선릉역
    (127.0350, 37.4869, 0.5),   # 도곡/매봉 (주거)
    (127.0668, 37.4900, 0.4),   # 개포동 (주거·상업부족)
]

CATEGORY_MIX = {
    "cafe": 0.22, "restaurant": 0.24, "grocery": 0.08, "shopping": 0.10,
    "school": 0.07, "hospital": 0.06, "park": 0.04, "library": 0.03,
    "subway": 0.06, "bus_stop": 0.10,
}


def make_boundary() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"name": ["Gangnam (core)"], "geometry": [box(*BBOX)]}, crs=WGS84)


def make_pois(n: int = 320) -> gpd.GeoDataFrame:
    """POI 생성 + 개소 연도(opening_year) 부여(최근일수록 신설 多)."""
    rng = np.random.default_rng(SEED)
    cats = list(CATEGORY_MIX)
    probs = np.array(list(CATEGORY_MIX.values())); probs = probs / probs.sum()
    weights = np.array([c[2] for c in CLUSTERS]); weights = weights / weights.sum()

    # 연도 가중치: 과거에 이미 다수 존재, 이후 완만히 증가
    yprob = np.linspace(1.0, 2.2, len(YEARS)); yprob = yprob / yprob.sum()

    lons, lats, categories, oyears = [], [], [], []
    for _ in range(n):
        ci = rng.choice(len(CLUSTERS), p=weights)
        clon, clat, _ = CLUSTERS[ci]
        lon = float(np.clip(clon + rng.normal(0, 0.006), BBOX[0], BBOX[2]))
        lat = float(np.clip(clat + rng.normal(0, 0.004), BBOX[1], BBOX[3]))
        lons.append(lon); lats.append(lat)
        categories.append(str(rng.choice(cats, p=probs)))
        oyears.append(int(rng.choice(YEARS, p=yprob)))

    return gpd.GeoDataFrame(
        {"category": categories, "opening_year": oyears},
        geometry=[Point(x, y) for x, y in zip(lons, lats)],
        crs=WGS84,
    )


def make_street_graph(step_deg: float = 0.0016) -> nx.Graph:
    """bbox를 덮는 격자형 합성 도로망 (노드 x·y=경위도, 4-이웃 연결)."""
    xs = np.arange(BBOX[0], BBOX[2] + step_deg, step_deg)
    ys = np.arange(BBOX[1], BBOX[3] + step_deg, step_deg)
    G = nx.Graph()
    idx = {}
    for i, y in enumerate(ys):
        for j, x in enumerate(xs):
            nid = i * len(xs) + j
            idx[(i, j)] = nid
            G.add_node(nid, x=float(x), y=float(y))
    for i in range(len(ys)):
        for j in range(len(xs)):
            if j + 1 < len(xs):
                G.add_edge(idx[(i, j)], idx[(i, j + 1)])
            if i + 1 < len(ys):
                G.add_edge(idx[(i, j)], idx[(i + 1, j)])
    return G


def build():
    data_dir = ROOT / "data" / "sample"
    dash_dir = ROOT / "docs" / "dashboard"
    data_dir.mkdir(parents=True, exist_ok=True)
    dash_dir.mkdir(parents=True, exist_ok=True)

    boundary = make_boundary()
    pois = make_pois()
    grid = create_fishnet(boundary, cell_size=250)

    # ---- 연도별(개발 시나리오) 점수 재계산 ----
    walk_by_year, s15_by_year, mean_by_year = {}, {}, {}
    for y in YEARS:
        sub = pois[pois["opening_year"] <= y]
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

    # ---- 샘플 데이터 저장 ----
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
    }
    for k, v in repl.items():
        html = html.replace(k, v)
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
<title>강남구 보행성 · 15분도시 대시보드 | Smart City GIS</title>
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
  .year-head{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:6px}
  .year-head .yr{font-size:26px;font-weight:800;color:var(--accent2)}
  .year-head .ym{font-size:12px;color:var(--muted)}
  input[type=range]{width:100%;accent-color:var(--accent2)}
  .play-row{display:flex;gap:6px;margin-top:8px}
  .play-row button{flex:1;padding:6px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:7px;cursor:pointer;font-size:12px}
</style>
</head>
<body>
<div id="app">
  <header>
    <h1>🌆 강남구 보행성 · 15분도시 대시보드</h1>
    <span class="sub">Walk Score(한국판) · 15-Minute City(Moreno 2021) · Isochrone</span>
    <span class="pill" id="modePill">보행성 지수</span>
  </header>

  <aside>
    <div class="card">
      <h3>지표 선택</h3>
      <div class="toggle-row">
        <button id="btnWalk" class="active" onclick="setMode('walk')">보행성 0–100</button>
        <button id="btn15" onclick="setMode('s15')">15분도시 0–6</button>
      </div>
      <div class="legend" id="legend"></div>
    </div>

    <div class="card">
      <h3>시계열 (개발 시나리오)</h3>
      <div class="year-head"><span class="yr" id="yrLabel">2026</span>
        <span class="ym" id="yrMean">평균 보행성 —</span></div>
      <input type="range" id="yrSlider" min="0" max="0" step="1" value="0" oninput="onYear(this.value)"/>
      <div class="play-row">
        <button id="playBtn" onclick="togglePlay()">▶ 재생</button>
        <button onclick="onYearIdx(YEARS.length-1)">최신(2026)</button>
      </div>
      <p class="muted" style="margin:8px 0 0">POI 개소 연도 기반 보행성 재계산. 연도별로 시설이 늘며 지도가 변합니다(시나리오).</p>
    </div>

    <div class="card">
      <h3>등시선 (강남역 도보권)</h3>
      <button id="isoBtn" class="btn" onclick="toggleIso()">⏱ 등시선 표시 (5·10·15·20분)</button>
      <div class="legend" id="isoLegend" style="margin-top:10px;display:none"></div>
    </div>

    <div class="card">
      <h3>요약 통계</h3>
      <div class="stat-grid" id="stats"></div>
    </div>

    <div class="card">
      <h3>보행성 점수 분포 (선택 연도)</h3>
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
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
  {attribution:'© OpenStreetMap © CARTO',subdomains:'abcd',maxZoom:19}).addTo(map);

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
      l.bindPopup(`<b>셀 #${i}</b> · ${YEARS[yearIdx]}<br>보행성: <b>${walkVal(i)}</b>/100<br>15분도시: <b>${s15Val(i)}</b>/6`).openPopup();});
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
  m.bindPopup(`<b>${cat}</b> · 개소 ${f.properties.opening_year}`);
  if(poiLayers[cat]) poiLayers[cat].addLayer(m);
});

function restyleGrid(){ gridLayer.setStyle(f=>({fillColor:colorOf(f.properties),weight:.4,color:'#0f1419',fillOpacity:.72})); }

function setMode(m){
  mode=m;
  document.getElementById('btnWalk').classList.toggle('active',m==='walk');
  document.getElementById('btn15').classList.toggle('active',m==='s15');
  document.getElementById('modePill').textContent = m==='walk'?'보행성 지수':'15분도시 지수';
  restyleGrid(); renderLegend(); renderHist();
}

function onYear(v){ yearIdx=+v; refreshYear(); }
function onYearIdx(i){ yearIdx=i; document.getElementById('yrSlider').value=i; refreshYear(); }
function refreshYear(){
  const y=YEARS[yearIdx];
  document.getElementById('yrLabel').textContent=y;
  document.getElementById('yrMean').textContent='평균 보행성 '+MEAN_BY_YEAR[String(y)];
  restyleGrid(); renderHist(); renderStats();
}
function togglePlay(){
  const btn=document.getElementById('playBtn');
  if(playTimer){ clearInterval(playTimer); playTimer=null; btn.textContent='▶ 재생'; return; }
  btn.textContent='⏸ 정지';
  playTimer=setInterval(()=>{
    yearIdx=(yearIdx+1)%YEARS.length;
    document.getElementById('yrSlider').value=yearIdx; refreshYear();
  },900);
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
  const cards=[[mean,'평균 보행성'],[mx,'최고 보행성'],[s15m,'평균 15분점수'],[ok+'%','15분 충족셀(≥4)'],[STATS.n_cells,'격자수'],[STATS.n_pois,'전체 POI']];
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
const sl=document.getElementById('yrSlider'); sl.max=YEARS.length-1; sl.value=yearIdx;
renderLegend(); renderIsoLegend(); renderStats(); renderHist(); renderPoiToggles(); refreshYear();
map.fitBounds(gridLayer.getBounds(),{padding:[20,20]});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    build()
