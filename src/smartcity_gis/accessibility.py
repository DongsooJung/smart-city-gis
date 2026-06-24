"""
접근성 분석

isochrone (등시선) + 2SFCA (2-Step Floating Catchment Area) +
gravity 모형 통합 인터페이스.
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
        >>> network = OSMClient.fetch_road_network("강남구", "walk")
        >>> a = AccessibilityAnalyzer(network)
        >>> iso = a.get_isochrone((127.05, 37.50), trip_times=[5, 10, 15])
        >>> a.plot_isochrones(iso)
    """

    def __init__(self, network):
        """
        Args:
            network: osmnx graph or networkx graph
        """
        self.network = network

    def get_isochrone(
        self,
        origin: tuple[float, float],
        trip_times: list[int] = [5, 10, 15],
        travel_speed: float = 4.5,  # km/h, 보행 평균
    ) -> IsochroneResult:
        """
        단일 출발점에서 등시선 폴리곤 생성.

        Args:
            origin: (lon, lat)
            trip_times: 분 단위 등시선 리스트
            travel_speed: 평균 이동속도 (km/h)
        """
        raise NotImplementedError(
            "TODO: import osmnx as ox; "
            "center_node = ox.nearest_nodes(G, lon, lat); "
            "for time in trip_times: "
            "  subgraph = ox.truncate.truncate_graph_dist(G, center_node, ...); "
            "  ConvexHull from subgraph nodes"
        )

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

        거리는 직선거리(m)를 도보속도로 분 단위로 환산해 catchment를 적용한다
        (네트워크 거리는 osmnx 그래프가 있을 때 향후 확장).

        Args:
            demand_points: 'population' 컬럼 포함 수요 지점
            supply_points: 'capacity' 컬럼 포함 공급 시설
            catchment_minutes: catchment 임계 (분)
            decay: 'threshold' | 'linear' | 'gaussian'
            travel_speed: 평균 이동속도 (km/h)

        Returns:
            demand_points 인덱스에 정렬된 접근성 점수 Series
        """
        if demand_col not in demand_points.columns:
            raise ValueError(f"demand_points에 '{demand_col}' 컬럼이 필요합니다.")
        if supply_col not in supply_points.columns:
            raise ValueError(f"supply_points에 '{supply_col}' 컬럼이 필요합니다.")

        D = _metric_coords(demand_points)            # (n_demand, 2)
        S = _metric_coords(supply_points)            # (n_supply, 2)
        pop = demand_points[demand_col].to_numpy(dtype=float)
        cap = supply_points[supply_col].to_numpy(dtype=float)

        # catchment 반경(m) = 속도(m/분) × 분
        d0 = (travel_speed * 1000.0 / 60.0) * catchment_minutes

        # 거리행렬 (n_demand × n_supply)
        dist = cdist(D, S)
        w = _decay(dist, d0, decay)                  # 가중치 행렬

        # Step 1: 각 공급 j의 공급-수요 비율 R_j
        weighted_demand = (w * pop[:, None]).sum(axis=0)   # (n_supply,)
        with np.errstate(divide="ignore", invalid="ignore"):
            R = np.where(weighted_demand > 0, cap / weighted_demand, 0.0)

        # Step 2: 각 수요 i의 접근성 A_i = Σ_j R_j × w_ij
        A = (w * R[None, :]).sum(axis=1)             # (n_demand,)

        return pd.Series(A, index=demand_points.index, name="accessibility_2sfca")

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

        β는 거리 마찰 계수 (보통 1~2). 거리는 직선거리(m).

        Args:
            origin_points: 출발 지점
            destinations: 'capacity'(매력도) 컬럼 포함 목적지
            beta: 거리 마찰 계수
            min_dist: 0거리 분모 방지용 최소거리(m)

        Returns:
            origin_points 인덱스에 정렬된 접근성 점수 Series
        """
        if attraction_col not in destinations.columns:
            raise ValueError(f"destinations에 '{attraction_col}' 컬럼이 필요합니다.")

        O = _metric_coords(origin_points)
        Dst = _metric_coords(destinations)
        attraction = destinations[attraction_col].to_numpy(dtype=float)

        dist = cdist(O, Dst)
        dist = np.maximum(dist, min_dist)            # 분모 0 방지
        A = (attraction[None, :] / dist ** beta).sum(axis=1)

        return pd.Series(A, index=origin_points.index, name="accessibility_gravity")


def fifteen_min_city_score(
    grid: gpd.GeoDataFrame,
    amenities: gpd.GeoDataFrame,
    network,
    essential_categories: list[str] = None,
) -> pd.Series:
    """
    15분 도시 지수 (Moreno 2021).

    각 셀 중심에서 6대 카테고리(주거·일·교육·의료·여가·상업)에
    15분 이내 도보 도달 가능 여부를 0~6점으로.

    Returns:
        grid 각 셀의 0~6 점수
    """
    raise NotImplementedError(
        "TODO: for each category: 15분 isochrone; "
        "if amenity in isochrone: +1; final = sum / len(categories) × 6"
    )
