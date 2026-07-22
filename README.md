# Smart City GIS Analytics

> GIS-based urban analytics platform for smart city planning and policy simulation

[![CI](https://github.com/DongsooJung/smart-city-gis/actions/workflows/ci.yml/badge.svg)](https://github.com/DongsooJung/smart-city-gis/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

한국 도시계획 의사결정은 여러 기관에 흩어진 데이터에 의존한다. 본 프로젝트는 인구·교통·토지이용·부동산
데이터를 결합해 **보행성·접근성·15분 도시** 지표를 계산하고 인터랙티브 지도로 시각화하는
end-to-end 분석 라이브러리다.

## ✅ 구현 현황 (정직한 상태표)

이 저장소는 **검증된 핵심 분석 라이브러리**이며, 외부 API 연동은 로드맵 단계다.
아래 표로 "실제 동작"과 "예정"을 명확히 구분한다.

| 기능 | 모듈 | 상태 | 테스트 |
|------|------|------|--------|
| 보행성 지수 (Walk Score 적응판) | `walkability.py` | ✅ 구현 | ✅ |
| Shannon 다양성 · 교차로/인구 밀도 | `walkability.py` | ✅ 구현 | ✅ |
| 격자 생성 `create_fishnet` | `geometry.py` | ✅ 구현 | ✅ |
| 2SFCA 접근성 (Luo & Wang 2003) | `accessibility.py` | ✅ 구현 | ✅ (보존법칙) |
| Gravity 접근성 모형 | `accessibility.py` | ✅ 구현 | ✅ |
| Isochrone 등시선 (networkx) | `accessibility.py` | ✅ 구현 | ✅ |
| 15분 도시 지수 (Moreno 2021) | `accessibility.py` | ✅ 구현 | ✅ |
| 시각화 (PNG/Folium/GeoJSON export) | `visualization.py` | ✅ 구현 | — |
| **인터랙티브 대시보드** | `docs/dashboard/` | ✅ 구현 | — |
| NSDI / V-World / KOSIS / OSM 클라이언트 | `api_clients.py` | 🚧 스텁(로드맵) | — |

## 🖥 인터랙티브 대시보드

`scripts/build_dashboard.py`가 라이브러리로 강남 핵심부 격자 점수를 계산해
**단일 HTML 대시보드**([`docs/dashboard/index.html`](docs/dashboard/index.html))를 생성한다.
Leaflet 코로플레스(보행성/15분도시 토글) + POI 카테고리 필터 + 분포 차트로 구성된다.

```bash
python scripts/build_dashboard.py      # 데이터 계산 + 대시보드 생성
# docs/dashboard/index.html 을 브라우저로 열기 (또는 GitHub Pages 배포)
```

샘플 데이터는 [`data/sample/`](data/sample/)에 GeoJSON으로 동봉되어 재현 가능하다.

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
├── src/smartcity_gis/
│   ├── geometry.py                  # create_fishnet 격자 생성
│   ├── walkability.py               # 보행성·다양성·밀도
│   ├── accessibility.py             # 2SFCA·gravity·isochrone·15분도시
│   ├── visualization.py             # PNG/Folium/GeoJSON export
│   └── api_clients.py               # 공공 API 래퍼 (로드맵)
├── scripts/build_dashboard.py       # 대시보드 빌더
├── notebooks/01_walkability_gangnam.ipynb
├── data/sample/                     # 재현용 강남 샘플 GeoJSON
├── docs/
│   ├── ARCHITECTURE.md              # 방법론·수식
│   ├── data_dictionary.md           # 데이터 스키마
│   ├── crs_reference.md             # 좌표계 가이드
│   └── dashboard/index.html         # 인터랙티브 대시보드
├── tests/                           # pytest (직선거리·통계 검증)
├── requirements.txt
└── LICENSE
```

## 🚀 Quick Start

```bash
git clone https://github.com/DongsooJung/smart-city-gis.git
cd smart-city-gis
pip install -r requirements.txt
pytest tests/ -v                     # 검증
python scripts/build_dashboard.py    # 대시보드 생성
```

## 📄 License

MIT License

## 👤 Author

**Dongsoo Jung** — Ph.D. Candidate, Seoul National University
Smart City Engineering · Civil & Environmental Engineering
