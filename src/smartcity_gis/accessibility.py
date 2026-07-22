"""
접근성 분석

isochrone (등시선) + 2SFCA (2-Step Floating Catchment Area) +
gravity 모형 + 15분 도시 지수 통합 인터페이스.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional
from dataclasses import dataclass

import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.spatial.distance import cdist

logger = logging.getLogger(__name__)

# 한국 표준 투영좌표계 (중부원점 TM) — 거리(m) 계산용
METRIC_CRS = 5186
WGS84 = 4326

# 15분 도시 6대 생활 카테고리 (Moreno 2021) → POI category 매핑
ESSENTIAL_CATEGORIES = {
    "commerce": ["grocery", "shopping"],
    "food": ["restaurant", "cafe"],
    "education": ["school", "library"],
    "healthcare": ["hospital"],
    "leisure": ["park"],
    "transit": ["subway", "bus_stop"],
}


def _metric_coords(gdf: gpd.GeoDataFrame) -> np.ndarray:
    """경위도면 미터 투영 후 (N, 2) 대표점 좌표 배열 반환."""
    if gdf.crs is not None and gdf.crs.is_geographic:
        gdf = gdf.to_crs(METRIC_CRS)
    geom = gdf.geometry
    if not set(geom.geom_type.unique()) <= {"Point", "MultiPoint"}:
        geom = geom.centroid
    return np.column_stack([geom.x.values, geom.y.values])


def _decay(dist: np.ndarray, d0: float, kind: str) -> np.ndarray:
    """거리 감쇠 함수 (catchment 내 가중치)."""
    dist = np.asarray(dist, dtype=float)
    if kind == "linear":
        return np.clip(1.0 - dist / d0, 0.0, 1.0)
    if kind == "gaussian":
        sigma = d0 / 2.0
        w = np.exp(-(dist ** 2) / (2.0 * sigma ** 2))
        return np.where(dist <= d0, w, 0.0)
    # 기본: 임계 catchment (이내=1, 초과=0)
    return (dist <= d0).astype(float)


def _lonlat_to_metric(lon: float, lat: float) -> tuple[float, float]:
    """단일 경위도점 → 미터(5186) 좌표."""
    pt = gpd.GeoSeries.from_xy([lon], [lat], crs=WGS84).to_crs(METRIC_CRS)
    return float(pt.x.iloc[0]), float(pt.y.iloc[0])


@dataclass
class IsochroneResult:
    """등시선 분석 결과."""

    origin: tuple[float, float]    # (lon, lat)
    isochrones: gpd.GeoDataFrame   # ['minutes', 'geometry']
    travel_mode: Literal["walk", "bike", "drive", "transit"]


class AccessibilityAnalyzer:
    """
    접근성 분석 통합 클래스.

    Example:
        >>> a = AccessibilityAnalyzer(network)   # networkx / osmnx 그래프
        >>> iso = a.get_isochrone((127.05, 37.50), trip_times=[5, 10, 15])
        >>> iso.isochrones.plot(column='minutes')
    """

    def __init__(self, network=None):
        """
        Args:
            network: osmnx graph 또는 networkx graph (노드에 x·y 속성).
        """
        self.network = network

    # ------------------------------------------------------------------
    # Isochrone (등시선)
    # ------------------------------------------------------------------
    def _node_metric_coords(self) -> tuple[list, np.ndarray]:
        """네트워크 노드 id 리스트와 (N,2) 미터좌표 배열."""
        nodes, lons, lats = [], [], []
        for n, data in self.network.nodes(data=True):
            if "x" in data and "y" in data:
                nodes.append(n)
                lons.append(data["x"])
                lats.append(data["y"])
        if not nodes:
            raise ValueError("네트워크 노드에 x·y(경위도) 속성이 없습니다.")
        pts = gpd.GeoSeries.from_xy(lons, lats, crs=WGS84).to_crs(METRIC_CRS)
        coords = np.column_stack([pts.x.values, pts.y.values])
        return nodes, coords

    def _ensure_travel_time(self, speed_m_per_min: float, coord_of: dict) -> None:
        """엣지에 travel_time(분) 속성을 채운다 (없으면 length/속도)."""
        for u, v, data in self.network.edges(data=True):
            length = data.get("length")
            if length is None:
                (x1, y1), (x2, y2) = coord_of[u], coord_of[v]
                length = float(np.hypot(x2 - x1, y2 - y1))
                data["length"] = length
            data["travel_time"] = length / speed_m_per_min

    def get_isochrone(
        self,
        origin: tuple[float, float],
        trip_times: list[int] = [5, 10, 15],
        travel_speed: float = 4.5,  # km/h, 보행 평균
        travel_mode: str = "walk",
    ) -> IsochroneResult:
        """
        단일 출발점에서 등시선(도달가능 영역) 폴리곤 생성.

        네트워크 그래프에서 출발점 최근접 노드를 찾고, 각 시간 임계마다
        `travel_time` 가중 ego-graph로 도달 노드를 구해 볼록껍질(convex hull)로
        폴리곤화한다. osmnx 그래프뿐 아니라 순수 networkx 그래프에서도 동작한다.

        Args:
            origin: (lon, lat)
            trip_times: 분 단위 등시선 리스트
            travel_speed: 평균 이동속도 (km/h)
            travel_mode: 'walk' | 'bike' | 'drive' | 'transit' (라벨용)

        Returns:
            IsochroneResult — .isochrones는 ['minutes','geometry'] (EPSG:4326),
            큰 시간부터 정렬(작은 등시선이 위에 겹쳐 그려지도록).
        """
        import networkx as nx
        from shapely.geometry import MultiPoint

        if self.network is None:
            raise ValueError("network가 필요합니다 (networkx/osmnx 그래프).")

        speed_m_per_min = travel_speed * 1000.0 / 60.0
        nodes, coords = self._node_metric_coords()
        coord_of = {n: (coords[i, 0], coords[i, 1]) for i, n in enumerate(nodes)}
        self._ensure_travel_time(speed_m_per_min, coord_of)

        # 출발점 최근접 노드
        ox_m, oy_m = _lonlat_to_metric(origin[0], origin[1])
        d = np.hypot(coords[:, 0] - ox_m, coords[:, 1] - oy_m)
        center = nodes[int(np.argmin(d))]

        polys, mins = [], []
        for t in sorted(trip_times, reverse=True):
            sub = nx.ego_graph(
                self.network, center, radius=float(t),
                distance="travel_time", undirected=True,
            )
            reach_xy = [coord_of[n] for n in sub.nodes if n in coord_of]
            if len(reach_xy) >= 3:
                hull = MultiPoint(reach_xy).convex_hull
            elif reach_xy:
                # 노드가 적으면 이동가능 반경으로 버퍼
                cx, cy = coord_of[center]
                hull = MultiPoint(reach_xy).convex_hull.buffer(speed_m_per_min * t)
            else:
                cx, cy = coord_of[center]
                hull = gpd.GeoSeries.from_xy([cx], [cy], crs=METRIC_CRS).iloc[0].buffer(
                    speed_m_per_min * t
                )
            polys.append(hull)
            mins.append(int(t))

        iso = gpd.GeoDataFrame(
            {"minutes": mins, "geometry": polys}, crs=METRIC_CRS
        ).to_crs(WGS84)
        return IsochroneResult(origin=origin, isochrones=iso, travel_mode=travel_mode)

    # ------------------------------------------------------------------
    # 2SFCA
    # ------------------------------------------------------------------
    def two_sfca(
        self,
        demand_points: gpd.GeoDataFrame,    # 인구 (수요)
        supply_points: gpd.GeoDataFrame,    # 시설 (공급)
        catchment_minutes: int = 30,
        decay: str = "gaussian",
        travel_speed: float = 4.5,          # km/h, 도보 평균
        demand_col: str = "population",
        supply_col: str = "capacity",
    ) -> pd.Series:
        """
        2-Step Floating Catchment Area (Luo & Wang 2003).

        의료시설 접근성 분석에 표준. 수요-공급 비율을 가중평균.
        거리는 직선거리(m)를 도보속도로 분 단위로 환산해 catchment를 적용한다.

        Returns:
            demand_points 인덱스에 정렬된 접근성 점수 Series
        """
        if demand_col not in demand_points.columns:
            raise ValueError(f"demand_points에 '{demand_col}' 컬럼이 필요합니다.")
        if supply_col not in supply_points.columns:
            raise ValueError(f"supply_points에 '{supply_col}' 컬럼이 필요합니다.")

        D = _metric_coords(demand_points)
        S = _metric_coords(supply_points)
        pop = demand_points[demand_col].to_numpy(dtype=float)
        cap = supply_points[supply_col].to_numpy(dtype=float)

        d0 = (travel_speed * 1000.0 / 60.0) * catchment_minutes
        dist = cdist(D, S)
        w = _decay(dist, d0, decay)

        weighted_demand = (w * pop[:, None]).sum(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            R = np.where(weighted_demand > 0, cap / weighted_demand, 0.0)

        A = (w * R[None, :]).sum(axis=1)
        return pd.Series(A, index=demand_points.index, name="accessibility_2sfca")

    # ------------------------------------------------------------------
    # Gravity
    # ------------------------------------------------------------------
    def gravity_model(
        self,
        origin_points: gpd.GeoDataFrame,
        destinations: gpd.GeoDataFrame,
        beta: float = 0.5,
        attraction_col: str = "capacity",
        min_dist: float = 1.0,
    ) -> pd.Series:
        """
        Gravity 모형 접근성: A_i = Σ_j (S_j / d_ij^β)

        Returns:
            origin_points 인덱스에 정렬된 접근성 점수 Series
        """
        if attraction_col not in destinations.columns:
            raise ValueError(f"destinations에 '{attraction_col}' 컬럼이 필요합니다.")

        O = _metric_coords(origin_points)
        Dst = _metric_coords(destinations)
        attraction = destinations[attraction_col].to_numpy(dtype=float)

        dist = cdist(O, Dst)
        dist = np.maximum(dist, min_dist)
        A = (attraction[None, :] / dist ** beta).sum(axis=1)
        return pd.Series(A, index=origin_points.index, name="accessibility_gravity")


def fifteen_min_city_score(
    grid: gpd.GeoDataFrame,
    amenities: gpd.GeoDataFrame,
    network=None,
    minutes: int = 15,
    travel_speed: float = 4.5,
    essential_categories: Optional[dict] = None,
) -> pd.Series:
    """
    15분 도시 지수 (Moreno 2021).

    각 셀 중심에서 6대 생활 카테고리(상업·먹거리·교육·의료·여가·이동)에
    `minutes`분 이내 도보 도달 가능 여부를 세어 0~6점으로 환산한다.

    거리는 직선거리(m)를 도보속도로 환산해 임계 적용한다(라이브러리 일관성).
    `network`가 주어지면 향후 네트워크 거리로 정밀화할 확장 지점이다.

    Args:
        grid: 분석 격자
        amenities: ['category','geometry'] POI
        network: (선택) 도로망 그래프. 현재는 직선거리 대체.
        minutes: 도달 임계(분)
        travel_speed: 도보 속도(km/h)
        essential_categories: {그룹명: [category,...]} 매핑 (기본 6대 카테고리)

    Returns:
        grid 인덱스에 정렬된 0~6 점수 Series
    """
    if "category" not in amenities.columns:
        raise ValueError("amenities에 'category' 컬럼이 필요합니다.")

    groups = essential_categories or ESSENTIAL_CATEGORIES
    n_groups = len(groups)

    if network is not None:
        logger.info("network 인자는 현재 직선거리로 대체 처리됩니다.")

    cell_xy = _metric_coords(grid)
    threshold = (travel_speed * 1000.0 / 60.0) * minutes  # m

    if len(amenities) == 0 or len(grid) == 0:
        return pd.Series(np.zeros(len(grid)), index=grid.index, name="score_15min")

    amen_xy = _metric_coords(amenities)
    cats = amenities["category"].to_numpy()

    reachable = np.zeros(len(grid), dtype=float)
    for cat_list in groups.values():
        mask = np.isin(cats, cat_list)
        if not mask.any():
            continue
        sub = amen_xy[mask]
        dmin = cdist(cell_xy, sub).min(axis=1)
        reachable += (dmin <= threshold).astype(float)

    score = reachable / n_groups * 6.0
    return pd.Series(score, index=grid.index, name="score_15min")
