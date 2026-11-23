# 🏗 Architecture & Methodology

> Smart City GIS Analytics

---

## 📐 프로젝트 구조

```
smart-city-gis/
├── src/smartcity_gis/
│   ├── __init__.py
│   ├── api_clients.py      # NSDI/V-World/KOSIS/OSM 통합 클라이언트
│   ├── walkability.py      # Walk Score 한국 적응판
│   ├── accessibility.py    # Isochrone, 2SFCA, 15-Min City
│   └── visualization.py    # (TODO) 인터랙티브 지도
├── notebooks/
│   └── 01_walkability_gangnam.ipynb
├── data/
└── docs/
```

---

## 📊 핵심 지표

### 1. Walkability Score

Walk Score (USA) 한국 적응판:

$$\text{Walkability}_i = \min\left(100, \sum_{j \in \text{POI}} w_j \cdot f(d_{ij})\right)$$

- $w_j$: POI 카테고리별 가중치 (groceries 3.0, cafe 0.5 등)
- $f(d)$: 거리 감쇠 함수 (exponential, 5분 = 1.0, 20분 = 0.0)

### 2. 2SFCA — 2-Step Floating Catchment Area

**Step 1**: 각 공급지 j에 대해 수요-공급비율
$$R_j = \frac{S_j}{\sum_k P_k \cdot W(d_{kj})}$$

**Step 2**: 각 수요지 i의 접근성
$$A_i = \sum_j R_j \cdot W(d_{ij})$$

**용도**: 의료시설 형평성 분석 표준.

### 3. 15-Minute City Score

6대 카테고리(주거·일·교육·의료·여가·상업)에 15분 이내 도보 도달 가능 여부.

$$\text{Score}_i = \frac{\#\{c \in C : \exists a \in c, \text{walk}(i, a) \leq 15\}}{|C|} \times 6$$

(Moreno 2021, "The 15-Minute City")

### 4. 거리 기준 — 직선거리 vs 네트워크 거리

위 수식의 $d_{ij}$는 두 가지 방식으로 계산된다.

**직선거리(straight, 기본)** — 두 점을 EPSG:5186로 투영해 유클리드 거리.
빠르지만 강·철도·고속도로 장벽과 통제된 단지를 무시하는 근사.

**네트워크 거리(network)** — 점을 최근접 도로망 노드에 스내핑하고, 간선 `length`(m)를
가중치로 다익스트라 최단경로를 구한다.

$$d_{ij}^{\text{net}} = \min_{P:\,o_i \to s_j} \sum_{e \in P} \ell_e$$

- catchment 반경 $d_0 = v \times t$ (기본 보행속도 4.5km/h) 밖의 쌍은 가중치 0
- 도달 불가(연결 요소 분리) 쌍은 $\infty$로 처리해 가중치 0
- 경로 탐색이 $d_0$에서 중단되므로 계산량은 격자 크기에 선형으로 증가

구현: `AccessibilityAnalyzer.two_sfca(..., distance_method=...)`,
`AccessibilityAnalyzer.network_distance_matrix(...)`,
`fifteen_min_city_score(..., network=...)`,
`compute_walkability(..., distance_method=...)`.
방법론·검증 절차는 [`network_distance.md`](network_distance.md).

### 5. 도로망 단절(연결 요소 분리) 처리

도로망은 실제로 여러 연결 컴포넌트로 나뉜다. 시설이 하나도 없는 조각에 붙은 셀은
거리가 얼마인지와 무관하게 어떤 시설에도 경로가 없으므로, 거리 점수가 0이 된다.

$$\text{isolated}_i = \big[\,\text{comp}(s(o_i)) \cap \mathcal{D} = \varnothing\,\big]$$

여기서 $s(\cdot)$는 최근접 노드 스내핑, $\text{comp}(\cdot)$는 연결 컴포넌트,
$\mathcal{D}$는 시설(POI) 노드 집합이다.

- 판정 기준은 거리와 무관한 **위상적 구조**다. 1600m 안에 시설이 없지만 같은
  연결 요소에 시설이 있는 셀은 "산출 불가"가 아니라 낮은 점수다.
- `NetworkDistanceCalculator.isolated_origins()`가 이 마스크를 계산한다.
- `compute_walkability(..., distance_method="network")`는 `_network_isolated`
  컬럼을 함께 반환한다. 점수는 0으로 남지만 집계에서는 제외해야 한다.
- 강남 대시보드 실측: 15,574노드 중 15,063노드(96.7%)가 최대 연결 요소에 속하고,
  40개 컴포넌트 중 시설이 없는 조각에 붙은 396개 셀 가운데 16개가 단절 셀이다.
  이 16개는 집계(평균 보행성 43.1, 충족률 93.9%)에서 제외되고 지도에서는 회색
  점선으로 표시된다.

---

## 🌐 API 의존성

| API | 인증 | 무료 한도 | 용도 |
|------|------|----------|------|
| NSDI | API Key | 1,000/일 | 행정경계, 건물 |
| V-World | API Key | 5,000/일 | 지도 타일, 지오코딩 |
| KOSIS | API Key | 무제한 | 통계 |
| OSMnx | 없음 | 무제한 | 도로망, POI |

`.env`에 키 설정 필요.

---

## 📖 참고문헌

1. Moreno, C., et al. (2021). Introducing the "15-minute city". *Smart Cities*, 4(1), 93-111.
2. Luo, W., & Wang, F. (2003). Measures of spatial accessibility to health care. *Environment and Planning B*, 30(6), 865-884.
3. Frank, L. D., et al. (2006). Many pathways from land use to health. *J American Planning Association*, 72(1), 75-87.
4. Boeing, G. (2017). OSMnx: New methods for acquiring, constructing, analyzing, and visualizing complex street networks. *Computers, Environment and Urban Systems*, 65, 126-139.
