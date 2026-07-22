# 📚 Data Dictionary

> Smart City GIS Analytics — 입력·출력 데이터 스키마 정의

본 문서는 라이브러리가 소비/생산하는 `GeoDataFrame`·`Series`의 컬럼 계약(contract)을 정의한다.
샘플 데이터는 [`data/sample/`](../data/sample/)에 GeoJSON으로 동봉되어 있으며, 노트북과
테스트가 이를 그대로 사용한다.

---

## 1. 입력 데이터

### 1.1 `grid` — 분석 격자
| 컬럼 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `geometry` | Polygon | ✅ | 100m × 100m 정사각 셀 권장 (`create_fishnet`로 생성) |
| `cell_id` | int/str | ⬜ | 셀 식별자 (없으면 인덱스 사용) |

- **CRS**: 입력은 EPSG:4326 또는 5186 허용. 내부에서 거리계산 시 5186으로 자동 투영.

### 1.2 `amenities` — 편의시설 POI
| 컬럼 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `geometry` | Point | ✅ | 시설 위치 |
| `category` | str | ✅ | POI 카테고리 (아래 표준값) |

표준 `category` 값 및 Walk Score 가중치 (`POI_WEIGHTS`):

| category | 가중치 | category | 가중치 |
|----------|--------|----------|--------|
| `grocery` | 3.0 | `park` | 1.0 |
| `subway` | 2.0 | `library` | 1.0 |
| `school` | 1.0 | `hospital` | 1.0 |
| `restaurant` | 0.75 | `bus_stop` | 1.0 |
| `cafe` | 0.5 | `shopping` | 0.5 |

### 1.3 `demand_points` / `population` — 수요(인구)
| 컬럼 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `geometry` | Point / Polygon | ✅ | 폴리곤은 대표점(centroid)으로 환산 |
| `population` | float | ✅ | 인구수 |

### 1.4 `supply_points` / `destinations` — 공급(시설)
| 컬럼 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `geometry` | Point | ✅ | 시설 위치 |
| `capacity` | float | ✅ | 공급량/매력도 (병상 수, 좌석 등) |

### 1.5 `network` — 도로망 그래프
`networkx.Graph` (또는 osmnx `MultiDiGraph`). 노드는 `x`(경도)·`y`(위도) 속성 필요.
엣지에 `length`(m)가 있으면 사용, 없으면 노드 좌표로 계산.

---

## 2. 출력 데이터

### 2.1 `compute_walkability` → `GeoDataFrame`
| 컬럼 | 타입 | 범위 | 설명 |
|------|------|------|------|
| `walkability_score` | float | 0–100 | 보행성 종합 점수 |
| `_subscore_diversity` | float | 0–1 | Shannon 다양성 부분점수 |

### 2.2 `two_sfca` / `gravity_model` → `Series`
`accessibility_2sfca` / `accessibility_gravity` — 수요지 인덱스에 정렬된 접근성 점수.

### 2.3 `fifteen_min_city_score` → `Series`
셀별 0–6 점 (6대 생활 카테고리 중 15분 도보 도달 개수).

### 2.4 `get_isochrone` → `IsochroneResult`
`.isochrones`: `['minutes','geometry']` (Polygon), `.origin`, `.travel_mode`.

---

## 3. 데이터 출처
| 출처 | 데이터 | 라이선스 |
|------|--------|----------|
| NSDI (국가공간정보포털) | 행정경계·건물·토지이용 | 공공누리 |
| V-World | 지오코딩·지도타일 | API 약관 |
| KOSIS (통계청) | 인구·가구·사업체 | 공공누리 |
| OpenStreetMap (osmnx) | 도로망·POI | ODbL |
