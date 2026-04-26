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
