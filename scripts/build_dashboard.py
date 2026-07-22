#!/usr/bin/env python3
"""
강남구 보행성·15분도시 인터랙티브 대시보드 빌더.

라이브러리(create_fishnet → compute_walkability → fifteen_min_city_score)를
실제로 호출해 격자 점수를 계산하고,
  - data/sample/*.geojson  (재현용 샘플 데이터)
  - docs/dashboard/index.html  (데이터 임베드 단일 파일 대시보드)
를 생성한다.

Usage:
    python scripts/build_dashboard.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import geopandas as gpd
from shapely.geometry import Point, box

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from smartcity_gis import create_fishnet, compute_walkability, fifteen_min_city_score  # noqa: E402

WGS84 = 4326
SEED = 42

# 강남구 핵심부 대략 경계 (경위도)
BBOX = (127.020, 37.480, 127.080, 37.520)

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
    rng = np.random.default_rng(SEED)
    cats = list(CATEGORY_MIX)
    probs = np.array(list(CATEGORY_MIX.values()))
    probs = probs / probs.sum()

    weights = np.array([c[2] for c in CLUSTERS])
    weights = weights / weights.sum()

    lons, lats, categories = [], [], []
    for _ in range(n):
        ci = rng.choice(len(CLUSTERS), p=weights)
        clon, clat, _ = CLUSTERS[ci]
        lon = clon + rng.normal(0, 0.006)
        lat = clat + rng.normal(0, 0.004)
        lon = float(np.clip(lon, BBOX[0], BBOX[2]))
        lat = float(np.clip(lat, BBOX[1], BBOX[3]))
        lons.append(lon)
        lats.append(lat)
        categories.append(str(rng.choice(cats, p=probs)))

    return gpd.GeoDataFrame(
        {"category": categories},
        geometry=[Point(x, y) for x, y in zip(lons, lats)],
        crs=WGS84,
    )


def build():
    data_dir = ROOT / "data" / "sample"
    dash_dir = ROOT / "docs" / "dashboard"
    data_dir.mkdir(parents=True, exist_ok=True)
    dash_dir.mkdir(parents=True, exist_ok=True)

    boundary = make_boundary()
    pois = make_pois()
    grid = create_fishnet(boundary, cell_size=250)

    walk = compute_walkability(grid, pois, decay="exponential")
    walk["score_15min"] = fifteen_min_city_score(grid, pois).values
    walk["walkability_score"] = walk["walkability_score"].round(1)
    walk["score_15min"] = walk["score_15min"].round(2)
    walk["cell_id"] = grid["cell_id"].values

    # --- 샘플 데이터 저장 ---
    boundary.to_file(data_dir / "gangnam_boundary.geojson", driver="GeoJSON")
    pois.to_file(data_dir / "gangnam_pois.geojson", driver="GeoJSON")
    walk[["cell_id", "walkability_score", "score_15min", "geometry"]].to_file(
        data_dir / "gangnam_grid_scores.geojson", driver="GeoJSON"
    )

    # --- 대시보드용 JSON ---
    grid_geo = json.loads(
        walk[["cell_id", "walkability_score", "score_15min", "geometry"]].to_crs(WGS84).to_json()
    )
    pois_geo = json.loads(pois.to_crs(WGS84).to_json())

    ws = walk["walkability_score"]
    stats = {
        "n_cells": int(len(walk)),
        "n_pois": int(len(pois)),
        "walk_mean": round(float(ws.mean()), 1),
        "walk_max": round(float(ws.max()), 1),
        "walk_p90": round(float(ws.quantile(0.9)), 1),
        "score15_mean": round(float(walk["score_15min"].mean()), 2),
        "pct_15min_ok": round(float((walk["score_15min"] >= 4).mean() * 100), 1),
        "cat_counts": pois["category"].value_counts().to_dict(),
        "hist": np.histogram(ws, bins=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100])[0].tolist(),
    }

    html = HTML_TEMPLATE
    html = html.replace("__GRID__", json.dumps(grid_geo, ensure_ascii=False))
    html = html.replace("__POIS__", json.dumps(pois_geo, ensure_ascii=False))
    html = html.replace("__STATS__", json.dumps(stats, ensure_ascii=False))
    (dash_dir / "index.html").write_text(html, encoding="utf-8")

    print(f"grid cells : {len(walk)}")
    print(f"pois       : {len(pois)}")
    print(f"walk mean  : {stats['walk_mean']}  max {stats['walk_max']}")
    print(f"15min mean : {stats['score15_mean']}  (>=4 : {stats['pct_15min_ok']}%)")
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
  :root{
    --bg:#0f1419; --panel:#1a2129; --panel2:#222c37; --line:#2e3a46;
    --ink:#e8edf2; --muted:#8fa0b0; --accent:#4ade80; --accent2:#38bdf8;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;font-family:'Segoe UI',-apple-system,'Malgun Gothic',sans-serif;background:var(--bg);color:var(--ink)}
  #app{display:grid;grid-template-columns:340px 1fr;grid-template-rows:auto 1fr;height:100vh}
  header{grid-column:1/3;padding:14px 20px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:16px;background:var(--panel)}
  header h1{font-size:18px;margin:0;font-weight:650}
  header .sub{color:var(--muted);font-size:12.5px}
  aside{border-right:1px solid var(--line);background:var(--panel);overflow-y:auto;padding:16px}
  main{position:relative}
  #map{position:absolute;inset:0}
  .card{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:14px}
  .card h3{margin:0 0 10px;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);font-weight:600}
  .stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
  .stat{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
  .stat .v{font-size:20px;font-weight:700;color:var(--accent)}
  .stat .l{font-size:11px;color:var(--muted);margin-top:2px}
  .toggle-row{display:flex;gap:6px;margin-bottom:10px}
  .toggle-row button{flex:1;padding:8px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:8px;cursor:pointer;font-size:12.5px;transition:.15s}
  .toggle-row button.active{background:var(--accent);color:#06210f;border-color:var(--accent);font-weight:650}
  label.chk{display:flex;align-items:center;gap:7px;font-size:12.5px;padding:3px 0;cursor:pointer;color:var(--ink)}
  label.chk .dot{width:10px;height:10px;border-radius:2px;display:inline-block}
  .legend{display:flex;flex-direction:column;gap:4px;font-size:11.5px}
  .legend .row{display:flex;align-items:center;gap:8px}
  .legend .sw{width:26px;height:12px;border-radius:2px}
  canvas{max-width:100%}
  .muted{color:var(--muted);font-size:11.5px;line-height:1.5}
  .leaflet-popup-content-wrapper{background:var(--panel2);color:var(--ink);border-radius:8px}
  .leaflet-popup-tip{background:var(--panel2)}
  .pill{display:inline-block;padding:1px 7px;border-radius:20px;background:var(--panel);border:1px solid var(--line);font-size:11px;color:var(--muted);margin-left:8px}
</style>
</head>
<body>
<div id="app">
  <header>
    <h1>🌆 강남구 보행성 · 15분도시 대시보드</h1>
    <span class="sub">Smart City GIS Analytics · Walk Score(한국 적응판) + 15-Minute City (Moreno 2021)</span>
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
      <h3>요약 통계</h3>
      <div class="stat-grid" id="stats"></div>
    </div>

    <div class="card">
      <h3>보행성 점수 분포</h3>
      <canvas id="hist" height="150"></canvas>
    </div>

    <div class="card">
      <h3>POI 카테고리 (표시 토글)</h3>
      <div id="poiToggles"></div>
    </div>

    <div class="card">
      <h3>카테고리별 POI 수</h3>
      <canvas id="catChart" height="180"></canvas>
    </div>

    <div class="card">
      <p class="muted">셀을 클릭하면 상세 점수를 봅니다. 데이터는 라이브러리 함수로 생성한
      재현 가능한 샘플이며(강남 핵심부, seed=42), 실제 정책판단 전 공공데이터로 교체하십시오.</p>
    </div>
  </aside>

  <main><div id="map"></div></main>
</div>

<script>
const GRID = __GRID__;
const POIS = __POIS__;
const STATS = __STATS__;

const CAT_COLORS = {
  cafe:'#f59e0b', restaurant:'#ef4444', grocery:'#22c55e', shopping:'#a855f7',
  school:'#3b82f6', hospital:'#ec4899', park:'#10b981', library:'#14b8a6',
  subway:'#eab308', bus_stop:'#94a3b8'
};

const map = L.map('map',{zoomControl:true}).setView([37.500,127.050],13);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
  {attribution:'© OpenStreetMap © CARTO',subdomains:'abcd',maxZoom:19}).addTo(map);

// ---- 색상 램프 ----
function rampWalk(v){ // YlGn 0-100
  const s=[[255,255,229],[247,252,185],[217,240,163],[173,221,142],[120,198,121],[65,171,93],[35,132,67],[0,104,55],[0,69,41]];
  const t=Math.max(0,Math.min(1,v/100))*(s.length-1); const i=Math.floor(t),f=t-i;
  const a=s[i],b=s[Math.min(i+1,s.length-1)];
  return `rgb(${Math.round(a[0]+(b[0]-a[0])*f)},${Math.round(a[1]+(b[1]-a[1])*f)},${Math.round(a[2]+(b[2]-a[2])*f)})`;
}
function ramp15(v){ // RdYlGn 0-6
  const s=[[215,48,39],[252,141,89],[254,224,139],[217,239,139],[145,207,96],[26,152,80]];
  const t=Math.max(0,Math.min(1,v/6))*(s.length-1); const i=Math.floor(t),f=t-i;
  const a=s[i],b=s[Math.min(i+1,s.length-1)];
  return `rgb(${Math.round(a[0]+(b[0]-a[0])*f)},${Math.round(a[1]+(b[1]-a[1])*f)},${Math.round(a[2]+(b[2]-a[2])*f)})`;
}

let mode='walk';
function valOf(p){ return mode==='walk'? p.walkability_score : p.score_15min; }
function colorOf(p){ return mode==='walk'? rampWalk(p.walkability_score) : ramp15(p.score_15min); }

const gridLayer = L.geoJSON(GRID,{
  style:f=>({fillColor:colorOf(f.properties),weight:.4,color:'#0f1419',fillOpacity:.72}),
  onEachFeature:(f,l)=>{
    const p=f.properties;
    l.bindPopup(`<b>셀 #${p.cell_id}</b><br>보행성: <b>${p.walkability_score}</b> / 100<br>15분도시: <b>${p.score_15min}</b> / 6`);
    l.on('mouseover',()=>l.setStyle({weight:1.6,color:'#fff'}));
    l.on('mouseout',()=>l.setStyle({weight:.4,color:'#0f1419'}));
  }
}).addTo(map);

// ---- POI 레이어 (카테고리별) ----
const poiLayers={};
Object.keys(CAT_COLORS).forEach(cat=>{
  poiLayers[cat]=L.layerGroup();
});
POIS.features.forEach(f=>{
  const cat=f.properties.category; const c=f.geometry.coordinates;
  const m=L.circleMarker([c[1],c[0]],{radius:3.4,color:CAT_COLORS[cat]||'#888',
    weight:1,fillColor:CAT_COLORS[cat]||'#888',fillOpacity:.9});
  m.bindPopup(`<b>${cat}</b>`);
  if(poiLayers[cat]) poiLayers[cat].addLayer(m);
});

function setMode(m){
  mode=m;
  document.getElementById('btnWalk').classList.toggle('active',m==='walk');
  document.getElementById('btn15').classList.toggle('active',m==='s15');
  document.getElementById('modePill').textContent = m==='walk'?'보행성 지수':'15분도시 지수';
  gridLayer.setStyle(f=>({fillColor:colorOf(f.properties),weight:.4,color:'#0f1419',fillOpacity:.72}));
  renderLegend();
}

function renderLegend(){
  const el=document.getElementById('legend');
  const rows=[];
  if(mode==='walk'){
    [0,20,40,60,80,100].forEach((v,i,arr)=>{ if(i<arr.length-1){
      rows.push(`<div class="row"><span class="sw" style="background:${rampWalk((v+arr[i+1])/2)}"></span>${v}–${arr[i+1]}</div>`);}});
  } else {
    [0,1,2,3,4,5,6].forEach((v,i,arr)=>{ if(i<arr.length-1){
      rows.push(`<div class="row"><span class="sw" style="background:${ramp15((v+arr[i+1])/2)}"></span>${v}–${arr[i+1]}</div>`);}});
  }
  el.innerHTML=rows.join('');
}

// ---- 통계 카드 ----
function renderStats(){
  const s=STATS;
  const cards=[
    [s.walk_mean,'평균 보행성'],[s.walk_max,'최고 보행성'],
    [s.score15_mean,'평균 15분점수'],[s.pct_15min_ok+'%','15분도시 충족셀(≥4)'],
    [s.n_cells,'분석 격자수'],[s.n_pois,'POI 수'],
  ];
  document.getElementById('stats').innerHTML=cards.map(c=>
    `<div class="stat"><div class="v">${c[0]}</div><div class="l">${c[1]}</div></div>`).join('');
}

// ---- POI 토글 ----
function renderPoiToggles(){
  const el=document.getElementById('poiToggles');
  el.innerHTML=Object.keys(CAT_COLORS).map(cat=>{
    const n=STATS.cat_counts[cat]||0;
    return `<label class="chk"><input type="checkbox" data-cat="${cat}" onchange="togglePoi(this)">
      <span class="dot" style="background:${CAT_COLORS[cat]}"></span>${cat} <span class="pill">${n}</span></label>`;
  }).join('');
}
function togglePoi(cb){
  const cat=cb.dataset.cat;
  if(cb.checked) poiLayers[cat].addTo(map); else map.removeLayer(poiLayers[cat]);
}

// ---- 차트 ----
function renderCharts(){
  const labels=['0','10','20','30','40','50','60','70','80','90'].map((x,i)=>x+'–'+((i+1)*10));
  new Chart(document.getElementById('hist'),{
    type:'bar',
    data:{labels,datasets:[{data:STATS.hist,backgroundColor:labels.map((_,i)=>rampWalk(i*10+5))}]},
    options:{plugins:{legend:{display:false}},scales:{
      x:{ticks:{color:'#8fa0b0',font:{size:9},maxRotation:60,minRotation:60},grid:{display:false}},
      y:{ticks:{color:'#8fa0b0'},grid:{color:'#2e3a46'}}}}
  });
  const cc=STATS.cat_counts; const cats=Object.keys(CAT_COLORS);
  new Chart(document.getElementById('catChart'),{
    type:'bar',
    data:{labels:cats,datasets:[{data:cats.map(c=>cc[c]||0),backgroundColor:cats.map(c=>CAT_COLORS[c])}]},
    options:{indexAxis:'y',plugins:{legend:{display:false}},scales:{
      x:{ticks:{color:'#8fa0b0'},grid:{color:'#2e3a46'}},
      y:{ticks:{color:'#8fa0b0',font:{size:10}},grid:{display:false}}}}
  });
}

renderLegend(); renderStats(); renderPoiToggles(); renderCharts();
map.fitBounds(gridLayer.getBounds(),{padding:[20,20]});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    build()
