"""
접근성 분석

isochrone (등시선) + 2SFCA (2-Step Floating Catchment Area) +
gravity 모형 + 15분 도시 지수 통합 인터페이스.

거리 기준은 두 가지를 지원한다.
- 직선거리(Euclidean, EPSG:5186 기준): 기본값. 격자·POI 계산이 빠르지만
  보행불가 지형·장벽을 무시하는 근사.
- 네트워크 거리(도로망 최단경로): `distance_method="network"` 또는 네트워크가
  주어지면 자동 사용. 실제 도로망 제약을 반영한다.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.spatial.distance import cdist

logger = logging.getLogger(__name__)

# 한국 표준 투영좌표계 (중부원점 TM) — 거리(m) 계산용
METRIC_CRS = 5186
WGS84 = 4326

# 거리 계산 방식
DistanceMethod = Literal["auto", "straight", "network"]

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
    """거리 감쇠 함수 (catchment 내 가중치).

    catchment 반경(d0) 밖은 종류와 무관하게 가중치 0이다. 네트워크 거리에서
    도달 불가·cutoff 초과는 `np.inf`로 표현되므로, 감쇠 계산은 반경 내부만
    대상으로 수행해 무한대 연산을 피한다.
    """
    dist = np.asarray(dist, dtype=float)
    inside = dist <= d0
    out = np.zeros(dist.shape, dtype=float)
    if kind == "linear":
        out[inside] = np.clip(1.0 - dist[inside] / d0, 0.0, 1.0)
    elif kind == "gaussian":
        sigma = d0 / 2.0
        out[inside] = np.exp(-(dist[inside] ** 2) / (2.0 * sigma ** 2))
    else:
        # 기본: 임계 catchment (이내=1, 초과=0)
        out[inside] = 1.0
    return out


def _graph_node_coords(network) -> tuple[list, np.ndarray]:
    """네트워크 노드 id 리스트와 (N,2) 미터좌표 배열."""
    nodes, lons, lats = [], [], []
    for n, data in network.nodes(data=True):
        if "x" in data and "y" in data:
            nodes.append(n)
            lons.append(data["x"])
            lats.append(data["y"])
    if not nodes:
        raise ValueError("네트워크 노드에 x·y(경위도) 속성이 없습니다.")
    pts = gpd.GeoSeries.from_xy(lons, lats, crs=WGS84).to_crs(METRIC_CRS)
    coords = np.column_stack([pts.x.values, pts.y.values])
    return nodes, coords


class NetworkDistanceCalculator:
    """도로망 그래프 기반 점 쌍 최단거리 계산기.

    격자 셀·POI처럼 도로망에 직접 속하지 않는 점을 가장 가까운 그래프 노드에
    스내핑(snap)한 뒤, 간선 `length`(미터)를 가중치로 다익스트라를 수행한다.
    catchment 반경 밖은 계산하지 않아(cutoff) 큰 격자에서도 비용이 선형으로
    증가하도록 한다.

    Example:
        >>> calc = NetworkDistanceCalculator(osmnx_graph)
        >>> matrix = calc.distance_matrix(origins_xy, destinations_xy, cutoff_m=1125)
    """

    def __init__(self, network):
        self.network = network
        self.nodes, self.coords = _graph_node_coords(network)
        self._node_of = {n: i for i, n in enumerate(self.nodes)}
        self._coord_of = {
            n: (self.coords[i, 0], self.coords[i, 1]) for i, n in enumerate(self.nodes)
        }
        self._tree = cKDTree(self.coords)

    # ------------------------------------------------------------------
    # 가중치 · 스내핑
    # ------------------------------------------------------------------
    def edge_weight(self, u, v, data) -> float:
        """간선 가중치(미터). osmnx `length` 우선, 없으면 노드 직선거리."""
        length = data.get("length")
        if length is None:
            (x1, y1), (x2, y2) = self._coord_of[u], self._coord_of[v]
            length = float(np.hypot(x2 - x1, y2 - y1))
        return float(length)

    def snap(self, points_xy: np.ndarray) -> np.ndarray:
        """각 점을 최근접 네트워크 노드로 매핑한 노드 라벨 배열."""
        if len(points_xy) == 0:
            return np.array([], dtype=object)
        _, idx = self._tree.query(np.asarray(points_xy, dtype=float), k=1)
        return np.array([self.nodes[int(i)] for i in np.atleast_1d(idx)], dtype=object)

    # ------------------------------------------------------------------
    # 거리 행렬
    # ------------------------------------------------------------------
    def distance_matrix(
        self,
        origins_xy: np.ndarray,
        destinations_xy: np.ndarray,
        cutoff_m: float | None = None,
    ) -> np.ndarray:
        """수요→공급 네트워크 최단거리 행렬(미터).

        Args:
            origins_xy: (N,2) 미터좌표
            destinations_xy: (M,2) 미터좌표
            cutoff_m: 계산 상한(m). 초과·도달 불가는 `np.inf`.

        Returns:
            (N, M) float ndarray
        """
        import networkx as nx

        n_o, n_d = len(origins_xy), len(destinations_xy)
        out = np.full((n_o, n_d), np.inf, dtype=float)
        if n_o == 0 or n_d == 0:
            return out

        origin_nodes = self.snap(origins_xy)
        dest_nodes = self.snap(destinations_xy)

        # 여러 공급지가 같은 노드로 스내핑될 수 있어 노드별로 묶는다.
        dest_cols: dict = {}
        for col, node in enumerate(dest_nodes):
            dest_cols.setdefault(node, []).append(col)

        cutoff = None if cutoff_m is None else float(cutoff_m)
        for row, origin in enumerate(origin_nodes):
            lengths = nx.single_source_dijkstra_path_length(
                self.network, origin, cutoff=cutoff, weight=self.edge_weight
            )
            if not lengths:
                continue
            for node, cols in dest_cols.items():
                dist = lengths.get(node)
                if dist is not None:
                    out[row, cols] = dist
        return out

    def reachable_matrix(
        self,
        origins_xy: np.ndarray,
        destinations_xy: np.ndarray,
        cutoff_m: float,
    ) -> np.ndarray:
        """각 출발점에서 `cutoff_m` 이내로 도달 가능한 도착점 boolean 행렬.

        15분 도시처럼 "도달 여부"만 필요한 경우에 거리 행렬보다 가볍다.

        Returns:
            (N, M) bool ndarray
        """
        import networkx as nx

        n_o, n_d = len(origins_xy), len(destinations_xy)
        out = np.zeros((n_o, n_d), dtype=bool)
        if n_o == 0 or n_d == 0:
            return out

        origin_nodes = self.snap(origins_xy)
        dest_nodes = self.snap(destinations_xy)
        dest_set = set(dest_nodes.tolist())

        for row, origin in enumerate(origin_nodes):
            lengths = nx.single_source_dijkstra_path_length(
                self.network, origin, cutoff=float(cutoff_m), weight=self.edge_weight
            )
            if not lengths:
                continue
            reach = dest_set.intersection(lengths.keys())
            if not reach:
                continue
            out[row] = np.isin(dest_nodes, list(reach))
        return out

    def nearest_by_category(
        self,
        origins_xy: np.ndarray,
        destinations_xy: np.ndarray,
        categories: Sequence[str],
        cutoff_m: float,
    ) -> tuple[list[str], np.ndarray, np.ndarray]:
        """카테고리별 최소 네트워크 거리와 POI 개수.

        보행성 지수처럼 "각 셀이 각 카테고리에서 가장 가까운 POI까지의 거리"만
        필요한 경우에 쓴다. 전체 (셀 × POI) 거리 행렬을 만들지 않아
        메모리가 셀 × 카테고리 크기로 유지된다.

        Returns:
            (categories, min_dist, counts) —
            min_dist는 (n_origins, n_categories) 최소 거리(m, 미도달은 inf),
            counts는 같은 모양의 POI 개수.
        """
        import networkx as nx

        n_o, n_d = len(origins_xy), len(destinations_xy)
        cat_labels = list(dict.fromkeys(categories))
        cat_index = {c: i for i, c in enumerate(cat_labels)}
        min_dist = np.full((n_o, len(cat_labels)), np.inf, dtype=float)
        counts = np.zeros((n_o, len(cat_labels)), dtype=int)
        if n_o == 0 or n_d == 0:
            return cat_labels, min_dist, counts

        origin_nodes = self.snap(origins_xy)
        dest_nodes = self.snap(destinations_xy)

        dest_by_node: dict = {}
        for j, node in enumerate(dest_nodes):
            dest_by_node.setdefault(node, []).append(j)

        for row, origin in enumerate(origin_nodes):
            lengths = nx.single_source_dijkstra_path_length(
                self.network, origin, cutoff=float(cutoff_m), weight=self.edge_weight
            )
            if not lengths:
                continue
            for node, dist in lengths.items():
                js = dest_by_node.get(node)
                if not js:
                    continue
                for j in js:
                    col = cat_index[categories[j]]
                    min_dist[row, col] = min(min_dist[row, col], dist)
                    counts[row, col] += 1
        return cat_labels, min_dist, counts

    def isolated_origins(
        self,
        origins_xy: np.ndarray,
        destinations_xy: np.ndarray,
    ) -> np.ndarray:
        """도로망 단절로 시설에 도달할 수 없는 출발점 표시.

        출발점을 스내핑한 노드가 속한 연결 컴포넌트에 도착점(시설) 노드가
        하나도 없으면 `True`다. 이런 출발점은 거리와 상관없이 어떤 시설에도
        경로가 없으므로, 거리 기반 점수(보행성·15분 도시)는 "접근이 없다"가
        아니라 "산출 불가"로 다루어야 한다.

        Args:
            origins_xy: (N,2) 미터좌표
            destinations_xy: (M,2) 미터좌표

        Returns:
            (N,) bool ndarray — 단절로 산출할 수 없는 출발점
        """
        import networkx as nx

        n_o = len(origins_xy)
        if n_o == 0 or len(destinations_xy) == 0:
            return np.zeros(n_o, dtype=bool)

        origin_nodes = self.snap(origins_xy)
        dest_nodes = set(self.snap(destinations_xy).tolist())

        comp_of: dict = {}
        for idx, comp in enumerate(nx.connected_components(self.network)):
            for node in comp:
                comp_of[node] = idx
        comps_with_dest = {comp_of[n] for n in dest_nodes if n in comp_of}
        return np.array(
            [comp_of.get(n, -1) not in comps_with_dest for n in origin_nodes],
            dtype=bool,
        )


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
        self._calculator: NetworkDistanceCalculator | None = None

    # ------------------------------------------------------------------
    # 거리 계산 방식
    # ------------------------------------------------------------------
    def _resolve_distance_method(self, distance_method: str) -> str:
        """`auto`를 실제 방식('straight'/'network')으로 확정한다."""
        if distance_method not in ("auto", "straight", "network"):
            raise ValueError(
                f"distance_method는 'auto'|'straight'|'network' 중 하나여야 합니다: {distance_method!r}"
            )
        if distance_method == "auto":
            return "network" if self.network is not None else "straight"
        if distance_method == "network" and self.network is None:
            raise ValueError("distance_method='network'에는 network 그래프가 필요합니다.")
        return distance_method

    def distance_calculator(self) -> NetworkDistanceCalculator:
        """(캐시된) 네트워크 거리 계산기."""
        if self.network is None:
            raise ValueError("network가 필요합니다 (networkx/osmnx 그래프).")
        if self._calculator is None:
            self._calculator = NetworkDistanceCalculator(self.network)
        return self._calculator

    def network_distance_matrix(
        self,
        origins: gpd.GeoDataFrame,
        destinations: gpd.GeoDataFrame,
        cutoff_m: float | None = None,
    ) -> np.ndarray:
        """
        두 점 집합 사이의 네트워크 최단거리 행렬(미터).

        격자 셀·POI를 가장 가까운 도로망 노드에 스내핑한 뒤, 간선 `length`를
        가중치로 최단경로를 구한다. 도달 불가 또는 `cutoff_m` 초과는 `np.inf`.

        Args:
            origins: 출발점 GeoDataFrame
            destinations: 도착점 GeoDataFrame
            cutoff_m: 계산 상한(m). None이면 전체 그래프에서 계산.

        Returns:
            (len(origins), len(destinations)) float ndarray
        """
        return self.distance_calculator().distance_matrix(
            _metric_coords(origins), _metric_coords(destinations), cutoff_m=cutoff_m
        )

    # ------------------------------------------------------------------
    # Isochrone (등시선)
    # ------------------------------------------------------------------
    def _node_metric_coords(self) -> tuple[list, np.ndarray]:
        """네트워크 노드 id 리스트와 (N,2) 미터좌표 배열."""
        if self.network is None:
            raise ValueError("network가 필요합니다 (networkx/osmnx 그래프).")
        return _graph_node_coords(self.network)

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
        trip_times: Sequence[int] = (5, 10, 15),
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
        distance_method: DistanceMethod = "auto",
    ) -> pd.Series:
        """
        2-Step Floating Catchment Area (Luo & Wang 2003).

        의료시설 접근성 분석에 표준. 수요-공급 비율을 가중평균.
        거리 기준:
        - `"straight"`: 직선거리(m)를 도보속도로 분 단위로 환산해 catchment 적용.
          빠르지만 강·철도·통제단지 같은 보행 제약을 무시하는 근사.
        - `"network"`: 도로망 최단거리(m) 사용. catchment 반경은 동일하게
          `travel_speed × catchment_minutes`로 두고, 반경 밖·도달 불가는
          가중치 0으로 처리한다.
        - `"auto"`: network가 있으면 네트워크 거리, 없으면 직선거리.

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
        method = self._resolve_distance_method(distance_method)
        if method == "network":
            dist = self.network_distance_matrix(demand_points, supply_points, cutoff_m=d0)
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
    essential_categories: dict | None = None,
    distance_method: DistanceMethod = "auto",
) -> pd.Series:
    """
    15분 도시 지수 (Moreno 2021).

    각 셀 중심에서 6대 생활 카테고리(상업·먹거리·교육·의료·여가·이동)에
    `minutes`분 이내 도보 도달 가능 여부를 세어 0~6점으로 환산한다.

    거리 기준:
    - `distance_method="straight"`: 직선거리(m)를 도보속도로 환산해 임계 적용.
      빠르지만 보행 제약을 무시하는 근사.
    - `distance_method="network"`: 도로망 최단거리(m)로 판정. `network`가
      주어지면 `"auto"`가 이 방식을 선택한다.
    - `distance_method="auto"`: network가 있으면 네트워크 거리, 없으면 직선거리.

    Args:
        grid: 분석 격자
        amenities: ['category','geometry'] POI
        network: (선택) 도로망 그래프. `distance_method="auto"`에서 네트워크 거리로 전환된다.
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

    if distance_method not in ("auto", "straight", "network"):
        raise ValueError(
            f"distance_method는 'auto'|'straight'|'network' 중 하나여야 합니다: {distance_method!r}"
        )
    if distance_method == "network" and network is None:
        raise ValueError("distance_method='network'에는 network 그래프가 필요합니다.")
    method = "network" if (distance_method == "auto" and network is not None) else distance_method
    if method == "straight":
        method = "straight"

    cell_xy = _metric_coords(grid)
    threshold = (travel_speed * 1000.0 / 60.0) * minutes  # m

    if len(amenities) == 0 or len(grid) == 0:
        return pd.Series(np.zeros(len(grid)), index=grid.index, name="score_15min")

    amen_xy = _metric_coords(amenities)
    cats = amenities["category"].to_numpy()

    reach = None
    if method == "network":
        reach = NetworkDistanceCalculator(network).reachable_matrix(
            cell_xy, amen_xy, threshold
        )

    reachable = np.zeros(len(grid), dtype=float)
    for cat_list in groups.values():
        mask = np.isin(cats, cat_list)
        if not mask.any():
            continue
        sub = amen_xy[mask]
        if reach is not None:
            reachable += reach[:, mask].any(axis=1).astype(float)
        else:
            dmin = cdist(cell_xy, sub).min(axis=1)
            reachable += (dmin <= threshold).astype(float)

    score = reachable / n_groups * 6.0
    return pd.Series(score, index=grid.index, name="score_15min")
