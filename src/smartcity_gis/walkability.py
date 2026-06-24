"""
보행성 지수 (Walkability Index) 계산

Walk Score (USA) 한국 적응판:
    1. 거리·POI 다양성 (Diversity)
    2. 교차로 밀도 (Connectivity)
    3. 주거밀도 (Density)
    4. POI 접근성 (Accessibility)
    5. 보도 품질 (옵션)

각 100m × 100m 그리드 셀에 0-100 점수 할당.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.spatial import cKDTree

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# POI 카테고리 가중치 (Walk Score 표준)
# ----------------------------------------------------------------------
POI_WEIGHTS = {
    "grocery": 3.0,
    "restaurant": 0.75,
    "cafe": 0.5,
    "shopping": 0.5,
    "school": 1.0,
    "park": 1.0,
    "library": 1.0,
    "hospital": 1.0,
    "subway": 2.0,
    "bus_stop": 1.0,
}

DECAY_DISTANCES = {
    "very_close": 400,    # 5분 도보
    "close": 800,         # 10분 도보
    "medium": 1200,
    "far": 1600,          # 20분 한계
}

# 한국 표준 투영좌표계 (중부원점 TM) — 거리(m) 계산용
METRIC_CRS = 5186


# ----------------------------------------------------------------------
# 내부 헬퍼
# ----------------------------------------------------------------------
def _decay_weight(dist: np.ndarray, d0: float, kind: str) -> np.ndarray:
    """거리 감쇠 가중치 (0~1).

    Args:
        dist: 거리 배열 (m)
        d0: 감쇠 기준거리 (m)
        kind: 'linear' | 'exponential' | 'gaussian'
    """
    dist = np.asarray(dist, dtype=float)
    if kind == "linear":
        return np.clip(1.0 - dist / d0, 0.0, 1.0)
    if kind == "gaussian":
        sigma = d0 / 2.0
        return np.exp(-(dist ** 2) / (2.0 * sigma ** 2))
    # 기본: 지수 감쇠
    return np.exp(-dist / d0)


def _to_metric(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """지리좌표(경위도)면 미터 단위 투영좌표계로 변환."""
    if gdf.crs is None:
        logger.warning("CRS가 없어 좌표를 미터로 간주합니다.")
        return gdf
    if gdf.crs.is_geographic:
        return gdf.to_crs(METRIC_CRS)
    return gdf


def _coords(gdf: gpd.GeoDataFrame, use_centroid: bool = False) -> np.ndarray:
    """GeoDataFrame에서 (N, 2) 좌표 배열 추출."""
    geom = gdf.geometry.centroid if use_centroid else gdf.geometry
    return np.column_stack([geom.x.values, geom.y.values])


# ----------------------------------------------------------------------
# 공개 API
# ----------------------------------------------------------------------
def compute_walkability(
    grid: gpd.GeoDataFrame,
    amenities: gpd.GeoDataFrame,
    network=None,
    decay: str = "exponential",
) -> gpd.GeoDataFrame:
    """
    그리드 셀별 보행성 지수 계산 (직선거리 기반).

    네트워크 거리(`network`)는 osmnx 그래프가 필요하므로, 현재 구현은
    직선거리(Euclidean) 기반이다. 네트워크 인자가 주어지면 향후 확장 지점.

    Args:
        grid: 분석 단위 그리드 (100m 격자 권장)
        amenities: POI GeoDataFrame ['category', 'geometry']
        network: osmnx 그래프 (현재 미사용, 직선거리로 대체)
        decay: 'linear' | 'exponential' | 'gaussian'

    Returns:
        grid 복사본 + ['walkability_score', '_subscore_diversity'] 컬럼
    """
    if "category" not in amenities.columns:
        raise ValueError("amenities에 'category' 컬럼이 필요합니다.")

    result = grid.copy()

    if len(grid) == 0:
        result["walkability_score"] = pd.Series(dtype=float)
        result["_subscore_diversity"] = pd.Series(dtype=float)
        return result

    g = _to_metric(grid)
    a = _to_metric(amenities)

    cell_xy = _coords(g, use_centroid=True)
    amen_xy = _coords(a, use_centroid=False)
    categories = a["category"].to_numpy()

    if network is not None:
        logger.info("network 인자는 현재 직선거리로 대체 처리됩니다.")

    max_d = float(max(DECAY_DISTANCES.values()))
    d0 = float(DECAY_DISTANCES["very_close"])
    max_possible = sum(POI_WEIGHTS.values())

    scores = np.zeros(len(g), dtype=float)
    diversity = np.zeros(len(g), dtype=float)

    if len(amen_xy) == 0:
        result["walkability_score"] = scores
        result["_subscore_diversity"] = diversity
        return result

    tree = cKDTree(amen_xy)
    neighbors = tree.query_ball_point(cell_xy, r=max_d)

    for i, idx_list in enumerate(neighbors):
        if not idx_list:
            continue
        idx = np.asarray(idx_list, dtype=int)
        dists = np.linalg.norm(amen_xy[idx] - cell_xy[i], axis=1)
        decays = _decay_weight(dists, d0, decay)
        cats = categories[idx]

        # 카테고리별로 가장 가까운(최대 기여) POI만 반영 → Walk Score 방식
        cat_contrib: dict[str, float] = {}
        for cat, dec in zip(cats, decays):
            w = POI_WEIGHTS.get(cat, 0.0)
            contrib = w * dec
            if contrib > cat_contrib.get(cat, 0.0):
                cat_contrib[cat] = contrib

        raw = sum(cat_contrib.values())
        scores[i] = min(100.0, raw / max_possible * 100.0)
        diversity[i] = diversity_index(pd.Series(cats))

    result["walkability_score"] = scores
    result["_subscore_diversity"] = diversity
    return result


def diversity_index(amenities_in_buffer: pd.Series) -> float:
    """
    Shannon 엔트로피 기반 POI 다양성 지수 (0~1로 정규화).

    H = -Σ pᵢ × ln(pᵢ), 정규화: H / ln(n_categories)

    Args:
        amenities_in_buffer: 카테고리 라벨 Series

    Returns:
        0(단일 카테고리) ~ 1(완전 균등) 사이 값. 비어있으면 0.
    """
    if amenities_in_buffer is None or len(amenities_in_buffer) == 0:
        return 0.0

    counts = pd.Series(amenities_in_buffer).value_counts()
    n = len(counts)
    if n <= 1:
        return 0.0

    p = counts.to_numpy(dtype=float)
    p = p / p.sum()
    h = -np.sum(p * np.log(p))
    return float(h / np.log(n))


def intersection_density(
    network,
    grid: gpd.GeoDataFrame,
) -> pd.Series:
    """그리드 셀당 교차로(분기점) 밀도 (개/km²).

    network는 노드에 'x', 'y' 속성을 가진 networkx 그래프를 가정한다
    (osmnx 그래프 호환). 차수 ≥ 3인 노드를 교차로로 간주한다.
    노드 좌표는 경위도(EPSG:4326)로 가정한다.

    Returns:
        grid 인덱스에 정렬된 교차로 밀도 Series
    """
    g = _to_metric(grid)

    # 차수 ≥ 3 노드를 교차로로 추출
    inter_x, inter_y = [], []
    for node, deg in network.degree():
        if deg < 3:
            continue
        data = network.nodes[node]
        if "x" in data and "y" in data:
            inter_x.append(data["x"])
            inter_y.append(data["y"])

    density = np.zeros(len(g), dtype=float)
    if not inter_x:
        return pd.Series(density, index=grid.index, name="intersection_density")

    pts = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy(inter_x, inter_y),
        crs="EPSG:4326",
    )
    pts = pts.to_crs(g.crs) if g.crs is not None else pts

    joined = gpd.sjoin(pts, g[["geometry"]], how="inner", predicate="within")
    counts = joined.groupby("index_right").size()

    areas_km2 = g.geometry.area / 1_000_000.0  # m² → km²
    for pos, cell_idx in enumerate(g.index):
        c = counts.get(cell_idx, 0)
        area = areas_km2.iloc[pos]
        density[pos] = c / area if area > 0 else 0.0

    return pd.Series(density, index=grid.index, name="intersection_density")


def population_density(
    grid: gpd.GeoDataFrame,
    population: gpd.GeoDataFrame,
) -> pd.Series:
    """그리드 셀당 인구밀도 (인/km²).

    population은 포인트(중심점) 또는 폴리곤이며 'population' 컬럼을 가진다.
    폴리곤은 대표점(중심점)을 셀에 매핑하는 방식으로 단순·견고하게 배분한다.

    Returns:
        grid 인덱스에 정렬된 인구밀도 Series
    """
    if "population" not in population.columns:
        raise ValueError("population에 'population' 컬럼이 필요합니다.")

    g = _to_metric(grid)
    pop = _to_metric(population)

    # 포인트가 아니면 대표점(중심점)으로 변환
    geom_types = set(pop.geometry.geom_type.unique())
    if not geom_types <= {"Point", "MultiPoint"}:
        pop = pop.copy()
        pop["geometry"] = pop.geometry.centroid

    joined = gpd.sjoin(pop, g[["geometry"]], how="inner", predicate="within")
    summed = joined.groupby("index_right")["population"].sum()

    pop_per_cell = np.zeros(len(g), dtype=float)
    for pos, cell_idx in enumerate(g.index):
        pop_per_cell[pos] = summed.get(cell_idx, 0.0)

    areas_km2 = (g.geometry.area / 1_000_000.0).to_numpy()
    density = np.where(areas_km2 > 0, pop_per_cell / areas_km2, 0.0)
    return pd.Series(density, index=grid.index, name="population_density")
