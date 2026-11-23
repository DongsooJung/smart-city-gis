# Smart City GIS Analytics

> GIS-based urban analytics platform for smart city planning and policy simulation

[![CI](https://github.com/DongsooJung/smart-city-gis/actions/workflows/ci.yml/badge.svg)](https://github.com/DongsooJung/smart-city-gis/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/badge/PyPI-smartcity--gis-3776AB?style=flat-square&logo=pypi&logoColor=white)](https://pypi.org/project/smartcity-gis/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

한국 도시계획 의사결정은 여러 기관에 흩어진 데이터에 의존한다. 본 프로젝트는 인구·교통·토지이용·부동산
데이터를 결합해 **보행성·접근성·15분 도시** 지표를 계산하고 인터랙티브 지도로 시각화하는
end-to-end 분석 라이브러리다.

## 📦 Installation

```bash
pip install smartcity-gis              # 코어 (보행성·접근성·15분도시)
pip install "smartcity-gis[network]"   # + OSMnx·Pandana 네트워크 분석
pip install "smartcity-gis[viz]"       # + Folium·matplotlib 시각화
pip install "smartcity-gis[stats]"     # + PySAL 공간통계
```

## ✅ 구현 현황 (정직한 상태표)

이 저장소는 **검증된 핵심 분석 라이브러리**와 OpenStreetMap 실데이터 기반 강남 대시보드를 제공한다.
아래 표로 "실제 동작"과 "예정"을 명확히 구분한다.

| 기능 | 모듈 | 상태 | 테스트 |
|------|------|------|--------|
| 보행성 지수 (Walk Score 적응판) | `walkability.py` | ✅ 구현 (직선거리 + 네트워크 거리) | ✅ |
| Shannon 다양성 · 교차로/인구 밀도 | `walkability.py` | ✅ 구현 | ✅ |
| 격자 생성 `create_fishnet` | `geometry.py` | ✅ 구현 | ✅ |
| 2SFCA 접근성 (Luo & Wang 2003) | `accessibility.py` | ✅ 구현 (직선거리 + 네트워크 거리) | ✅ (보존법칙) |
| Gravity 접근성 모형 | `accessibility.py` | ✅ 구현 | ✅ |
| Isochrone 등시선 (networkx) | `accessibility.py` | ✅ 구현 | ✅ |
| 15분 도시 지수 (Moreno 2021) | `accessibility.py` | ✅ 구현 (직선거리 + 네트워크 거리) | ✅ |
| 시각화 (PNG/Folium/GeoJSON export) | `visualization.py` | ✅ 구현 | — |
| **인터랙티브 대시보드** | `docs/dashboard/` | ✅ 구현 (도로망 거리 기준) | — |
| OSM POI·보행망 수집 | `fetch_osm_data.py` | ✅ 구현 | 스키마 검증 |
| NSDI / V-World / KOSIS 클라이언트 | `api_clients.py` | 🚧 스텁(로드맵) | — |

## 🖥 인터랙티브 대시보드

`scripts/fetch_osm_data.py`가 OpenStreetMap의 현재 POI·보행망을 수집하고,
`scripts/build_dashboard.py`가 라이브러리로 강남 핵심부 격자 점수를 계산해
**단일 HTML 대시보드**([`docs/dashboard/index.html`](docs/dashboard/index.html))를 생성한다.
Leaflet 코로플레스(보행성/15분도시 토글) + POI 카테고리 필터 + 분포 차트로 구성된다.

```bash
python scripts/fetch_osm_data.py       # OSM 실제 POI·보행망 수집
python scripts/build_dashboard.py      # 데이터 계산 + 대시보드 생성
# docs/dashboard/index.html 을 브라우저로 열기 (또는 GitHub Pages 배포)
```

배포 대시보드는 [`data/actual/`](data/actual/)의 최신 OSM 스냅샷을 사용한다. `data/sample/`은
라이브러리 테스트와 오프라인 재현용으로만 유지한다.

## 🧭 방법론

`docs/ARCHITECTURE.md`에 수식과 참고문헌이 정리되어 있다.

1. **Walkability**: POI 카테고리 가중치 × 거리감쇠 → 0–100 (Walk Score 한국 적응)
2. **2SFCA**: 2단계 유동 집수구역, 의료 형평성 분석 표준
3. **15-Minute City**: 6대 생활 카테고리 15분 도보 도달 개수 (0–6)
4. **Isochrone**: 도로망 그래프 travel-time ego-graph → 볼록껍질 등시선

## 🧪 사례 연구 (방법론 데모)

아래는 저자가 동일 방법론을 적용/제안한 도시계획 맥락이다. 코드 저장소는 방법론을
재현하는 라이브러리와 강남 데모를 제공한다(고객 데이터는 비공개).

| 사례 | 맥락 | 방법 |
|------|------|------|
| 수원 군공항 이전 영향 | 연구 제안 | Buffer 분석, DID |
| 김포 스마트 재생 타당성 | 정책 검토 | 접근성 지수, 비용편익 |
| 부천역세권 개발 | 지자체 맥락 | 토지이용 분석 |

## 🛠 Tech Stack

- **GIS Core:** GeoPandas, Shapely, pyproj, Fiona, Rasterio
- **Network:** OSMnx, NetworkX, Pandana
- **Spatial Stats:** libpysal, esda
- **Visualization:** Folium, Kepler.gl, Matplotlib, Leaflet + Chart.js (대시보드)
- **APIs (로드맵):** V-World, KOSIS, NSDI

## 📁 Repository Structure

```
smart-city-gis/
├── .github/workflows/ci.yml         # pytest 자동화 (3.11/3.12)
├── pyproject.toml                   # 패키지 메타데이터 (pip install 지원)
├── CHANGELOG.md                     # 버전별 변경 기록
├── src/smartcity_gis/
│   ├── geometry.py                  # create_fishnet 격자 생성
│   ├── walkability.py               # 보행성·다양성·밀도
│   ├── accessibility.py             # 2SFCA·gravity·isochrone·15분도시
│   ├── visualization.py             # PNG/Folium/GeoJSON export
│   └── api_clients.py               # 공공 API 래퍼 (로드맵)
├── scripts/fetch_osm_data.py        # OSM 실데이터 수집
├── scripts/build_dashboard.py       # 대시보드 빌더
├── notebooks/01_walkability_gangnam.ipynb
├── data/actual/                     # 배포용 OSM 실제 스냅샷
├── data/sample/                     # 테스트용 강남 샘플 GeoJSON
├── docs/
│   ├── ARCHITECTURE.md              # 방법론·수식
│   ├── data_dictionary.md           # 데이터 스키마
│   ├── crs_reference.md             # 좌표계 가이드
│   ├── network_distance.md          # 네트워크 거리 접근성 방법론
│   └── dashboard/index.html         # 인터랙티브 대시보드
├── tests/                           # pytest (직선거리·통계 검증)
├── requirements.txt
└── LICENSE
```

## 🚀 Quick Start

```bash
pip install "smartcity-gis[dev]"       # PyPI 설치 (개발용 extras 포함)

# 또는 소스에서 직접:
git clone https://github.com/DongsooJung/smart-city-gis.git
cd smart-city-gis
pip install -r requirements.txt
pytest tests/ -v                     # 검증
python scripts/fetch_osm_data.py     # OSM 실제 데이터 갱신
python scripts/build_dashboard.py    # 대시보드 생성
```

## 🛣 네트워크 거리 접근성

2SFCA와 15분 도시 지수는 거리 기준을 선택할 수 있습니다. 기본값은 직선거리(Euclidean)이며,
도로망 그래프를 넘기면 실제 보행 거리로 다시 계산합니다.

```python
import osmnx as ox
from smartcity_gis import AccessibilityAnalyzer, fifteen_min_city_score

G = ox.graph_from_place("Gangnam-gu, Seoul, South Korea", network_type="walk")
analyzer = AccessibilityAnalyzer(network=G)

# 수요(인구) - 공급(용량) 사이의 네트워크 거리 기반 2SFCA
scores = analyzer.two_sfca(demand_points, supply_points, catchment_minutes=30)

# 거리 표면을 직접 확인 (미터, 도달 불가·cutoff 초과는 inf)
D = analyzer.network_distance_matrix(demand_points, supply_points, cutoff_m=2250)

# 15분 도시 지수도 네트워크 거리로
score = fifteen_min_city_score(grid, amenities, network=G)
```

- `distance_method="auto"`(기본): 네트워크가 있으면 네트워크 거리, 없으면 직선거리
- `distance_method="straight"`: 직선거리 강제 · `"network"`: 네트워크 거리 강제(그래프 없으면 `ValueError`)
- 거리 계산은 EPSG:5186 기준이며, 도달 불가·catchment 반경 밖은 가중치 0으로 처리됩니다.
- `compute_walkability(..., distance_method="network")`는 `_network_isolated` 플래그를 함께 반환합니다. 도로망 단절로 어떤 시설에도 경로가 없는 셀은 점수가 0이 되지만 "접근 없는 지역"이 아니라 "거리 산출 불가"이므로 집계에서 제외해야 합니다.
- 방법론·검증 절차·성능 지침: [`docs/network_distance.md`](docs/network_distance.md)

## 📄 License

MIT License

## 📖 Citation

If you use this library in research or policy analysis, please cite it:

```bibtex
@software{smartcitygis2026,
  author    = {Jung, Dongsoo},
  title     = {smart-city-gis: Urban accessibility analytics for Korean smart city planning},
  version   = {0.2.0},
  year      = {2026},
  publisher = {GitHub},
  doi       = {10.5281/zenodo.XXXXXXX},
  url       = {https://github.com/DongsooJung/smart-city-gis}
}
```

Citation metadata is also machine-readable in [`CITATION.cff`](CITATION.cff).
Methodology, data schema, and coordinate-system references live in
[`docs/`](docs/): [ARCHITECTURE.md](docs/ARCHITECTURE.md),
[data_dictionary.md](docs/data_dictionary.md),
[crs_reference.md](docs/crs_reference.md),
[network_distance.md](docs/network_distance.md).

## 🤝 Contributing

Issues and pull requests are welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md). Security reports: [SECURITY.md](SECURITY.md).

## 👤 Author

**Dongsoo Jung** — Ph.D. Candidate, Seoul National University
Smart City Engineering · Civil & Environmental Engineering


## 2026-10-31 수집·해석 범위 개정

- 기존 수집기의 변환 경로를 유지하며 읽기 전용 Overpass로 조회한다. 네 응답의 실제 수신 시각·DB 기준 시각·질의·해시를 metadata.json에 기록한다. 원응답은 기본 data/raw/osm(버전관리 제외), 또는 --raw-dir에 보관한다. 수집일은 현장 관측일·월간 통계 기준월이 아니다.
- POI는 연구 직사각형 안의 OSM 태그 노드다. 같은 좌표의 서로 다른 노드 ID를 합치지 않고, 경계 응답에 반복된 같은 ID만 중복 제거한다. way/relation으로 등록된 시설과 현장 영업 여부는 조사하지 않았다. 도로 그래프는 선택 highway의 중복 way/무방향 간선을 제거한다. 이전 좌표·분류별 중복 제거 저장본과 개수 증가율을 만들지 않는다.
- 연구 직사각형은 강남역 주변이며 강남구 행정경계가 아니다. 경계 밖 POI를 포함하지 않아 가장자리 효과가 있다. 보행성은 카테고리별 최근접 POI의 지수 감쇠(400m)와 1600m 한계를 사용해 가중치 합으로 정규화한 자체 지표이며 공식 Walk Score 인증값이 아니다.
- 생활 접근 0~6은 여섯 분류의 최근접 **도로망 최단거리** 1125m 이내 여부다(4.5km/h × 15분 가정). 실제 도보시간 검증값이 아니다. 도로망 근사권은 선택 무방향 그래프에서 5/10/15/20분 내 도달노드의 볼록껍질이며 통행권·횡단·출입구 연결은 전수 검증하지 않았다.
- 선택 도로망은 연결 컴포넌트 40개로 나뉘고 노드의 96.7%만 최대 연결 요소에 속한다. 시설이 하나도 없는 단절 조각에 붙은 셀 16개는 거리 점수를 산출할 수 없어 0점으로 두고 집계(평균·분포·충족률)에서 제외했으며, 지도에서는 회색 점선으로 구분해 표시한다. 격자 CSV·GeoJSON에는 `network_isolated` 열(또는 속성)이 함께 담긴다.
- 가공 생성일과 수집일을 분리하고 개소연도를 임의로 붙이지 않는다. docs/dashboard/data/에 같은 실행의 격자 CSV/GeoJSON·POI·그래프·근사권·요약·출처 JSON을 함께 생성한다. 완전한 네 응답을 확보하지 못하면 기존 수집 입력을 교체하지 않는다.

재현: `python scripts/fetch_osm_data.py --raw-dir data/raw/osm` 후 `python scripts/build_dashboard.py`, `pytest tests/`를 실행한다. 원자료 응답이 달라지는 재수집과 저장본의 오프라인 재계산을 구분한다.
