# 🗺 CRS Reference — 좌표계 참조

> Smart City GIS Analytics — 한국 공간분석 좌표계 가이드

## 왜 좌표계가 중요한가

경위도(EPSG:4326)는 **각도** 단위라 거리·면적을 직접 계산하면 왜곡된다.
본 라이브러리는 모든 거리·면적 계산을 **EPSG:5186(중부원점 TM)** 으로 투영해 수행한다.
관련 상수는 각 모듈의 `METRIC_CRS = 5186`.

## 주요 좌표계

| EPSG | 이름 | 단위 | 용도 |
|------|------|------|------|
| **4326** | WGS84 경위도 | degree | GPS, 웹지도, 데이터 교환(GeoJSON) |
| **5186** | Korea 2000 / Central Belt 2010 | m | **거리·면적 분석(본 라이브러리 표준)** |
| 5179 | Korea 2000 / Unified CS (UTM-K) | m | 국토지리정보원 표준, 전국 단일원점 |
| 5181 | Korea 2000 / Central Belt | m | 구 중부원점 |
| 3857 | Web Mercator | m | 타일 지도 배경(contextily/Folium) |

## 변환 규칙

```python
# 경위도 → 미터 (거리 계산 전)
gdf_m = gdf.to_crs(5186)

# 미터 → 경위도 (지도 시각화/GeoJSON 출력 전)
gdf_wgs = gdf_m.to_crs(4326)
```

## 원점 참고
- **5186 중부원점**: 경도 127°E, 위도 38°N, X가산 200,000m, Y가산 600,000m.
- 서울·경기·강원 중부권 분석에 왜곡이 가장 작다.
- 전국 단위(제주 포함) 통합 분석은 5179(UTM-K) 권장.

## 주의사항
1. CRS가 `None`인 GeoDataFrame은 미터로 **가정**하고 경고를 남긴다(`_to_metric`).
2. osmnx 그래프 노드 좌표는 관례상 EPSG:4326(경위도)이다.
3. GeoJSON 표준 CRS는 4326이므로 파일 입출력 경계에서 변환을 명시하라.
