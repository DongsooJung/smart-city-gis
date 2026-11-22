"""네트워크 거리 기반 접근성(2SFCA·15분 도시) 단위 테스트.

모두 순수 networkx 그래프로 검증한다(osmnx·pandana 불필요).

검증 설계의 핵심: `A`와 `B`는 직선거리로 약 177m 떨어져 있지만 도로망으로는
중간 노드 `C`를 거쳐 2,000m를 돌아가야 한다. 따라서
- 직선거리에서는 도달 가능하지만 네트워크 거리에서는 도달 불가인 구간과
- 네트워크 거리에서는 도달 가능하지만 직선거리에서는 도달 불가인 구간
이 모두 존재해, 두 방식이 실제로 다른 결과를 내는지 관찰할 수 있다.
"""
import sys
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pytest
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from smartcity_gis.accessibility import (
    AccessibilityAnalyzer,
    _decay,
    fifteen_min_city_score,
)

# 도보 4.5km/h, 15분 → 1,125m
WALK_15MIN_M = 4.5 * 1000.0 / 60.0 * 15


def _detour_graph():
    """A --(1000m)-- C --(1000m)-- B. A-B 직선거리는 약 177m."""
    G = nx.Graph()
    G.add_node("A", x=127.000, y=37.500)
    G.add_node("C", x=127.001, y=37.520)
    G.add_node("B", x=127.002, y=37.500)
    G.add_edge("A", "C", length=1000.0)
    G.add_edge("C", "B", length=1000.0)
    return G


def _point_gdf(coords, **columns):
    """(lon, lat) 리스트 → EPSG:4326 GeoDataFrame."""
    return gpd.GeoDataFrame(
        columns,
        geometry=[Point(lon, lat) for lon, lat in coords],
        crs="EPSG:4326",
    )


class TestNetworkDistanceMatrix:
    def test_matrix_uses_network_length(self):
        G = _detour_graph()
        a = AccessibilityAnalyzer(G)
        origins = _point_gdf([(127.000, 37.500)], name=["A"])
        dests = _point_gdf([(127.002, 37.500), (127.001, 37.520)], name=["B", "C"])
        m = a.network_distance_matrix(origins, dests)
        assert m[0, 0] == pytest.approx(2000.0)   # A → C → B
        assert m[0, 1] == pytest.approx(1000.0)   # A → C

    def test_cutoff_marks_far_pairs_infinite(self):
        G = _detour_graph()
        a = AccessibilityAnalyzer(G)
        origins = _point_gdf([(127.000, 37.500)])
        dests = _point_gdf([(127.002, 37.500)])
        m = a.network_distance_matrix(origins, dests, cutoff_m=1000.0)
        assert np_isinf(m[0, 0])

    def test_disconnected_component_is_infinite(self):
        G = _detour_graph()
        G.add_node("D", x=127.010, y=37.510)   # 연결되지 않은 노드
        a = AccessibilityAnalyzer(G)
        origins = _point_gdf([(127.000, 37.500)])
        dests = _point_gdf([(127.010, 37.510)])
        m = a.network_distance_matrix(origins, dests)
        assert np_isinf(m[0, 0])

    def test_requires_network(self):
        a = AccessibilityAnalyzer(network=None)
        with pytest.raises(ValueError):
            a.network_distance_matrix(_point_gdf([(127.0, 37.5)]), _point_gdf([(127.0, 37.5)]))


def np_isinf(value: float) -> bool:
    """numpy inf 판정 헬퍼."""
    import numpy as np

    return bool(np.isinf(value))


class TestTwoSFCANetworkDistance:
    def _demand(self, coords, pop):
        return _point_gdf(coords, population=pop)

    def _supply(self, coords, cap):
        return _point_gdf(coords, capacity=cap)

    def test_straight_reachable_but_network_not(self):
        """직선거리로는 15분 안, 도로망으로는 2,000m — 네트워크는 도달 불가."""
        G = _detour_graph()
        a = AccessibilityAnalyzer(G)
        demand = self._demand([(127.000, 37.500)], [1000.0])   # A
        supply = self._supply([(127.002, 37.500)], [500.0])    # B

        straight = a.two_sfca(demand, supply, catchment_minutes=15,
                              distance_method="straight")
        network = a.two_sfca(demand, supply, catchment_minutes=15,
                             distance_method="network")

        # 단일 수요-공급 쌍이면 A = C/P (가중치가 0이 아니면)
        assert straight.iloc[0] == pytest.approx(500.0 / 1000.0)
        # 네트워크에서는 반경 밖 → 가중치 0 → 접근성 0
        assert network.iloc[0] == 0.0

    def test_network_reachable_but_straight_not(self):
        """A→C는 도로망 1,000m지만 직선거리로는 2,200m — 네트워크만 도달 가능."""
        G = _detour_graph()
        a = AccessibilityAnalyzer(G)
        demand = self._demand([(127.000, 37.500)], [1000.0])   # A
        supply = self._supply([(127.001, 37.520)], [500.0])    # C

        straight = a.two_sfca(demand, supply, catchment_minutes=15,
                              distance_method="straight")
        network = a.two_sfca(demand, supply, catchment_minutes=15,
                             distance_method="network")

        assert straight.iloc[0] == 0.0
        assert network.iloc[0] == pytest.approx(500.0 / 1000.0)

    def test_auto_uses_network_when_available(self):
        G = _detour_graph()
        a = AccessibilityAnalyzer(G)
        demand = self._demand([(127.000, 37.500)], [1000.0])
        supply = self._supply([(127.002, 37.500)], [500.0])

        auto = a.two_sfca(demand, supply, catchment_minutes=15)
        explicit = a.two_sfca(demand, supply, catchment_minutes=15,
                              distance_method="network")
        assert auto.equals(explicit)

    def test_auto_falls_back_to_straight_without_network(self):
        a = AccessibilityAnalyzer(network=None)
        demand = self._demand([(127.000, 37.500)], [1000.0])
        supply = self._supply([(127.002, 37.500)], [500.0])

        auto = a.two_sfca(demand, supply, catchment_minutes=15)
        straight = a.two_sfca(demand, supply, catchment_minutes=15,
                              distance_method="straight")
        assert auto.equals(straight)

    def test_network_method_without_graph_raises(self):
        a = AccessibilityAnalyzer(network=None)
        demand = self._demand([(127.000, 37.500)], [1000.0])
        supply = self._supply([(127.002, 37.500)], [500.0])
        with pytest.raises(ValueError):
            a.two_sfca(demand, supply, distance_method="network")

    def test_invalid_method_raises(self):
        a = AccessibilityAnalyzer(_detour_graph())
        demand = self._demand([(127.000, 37.500)], [1000.0])
        supply = self._supply([(127.002, 37.500)], [500.0])
        with pytest.raises(ValueError):
            a.two_sfca(demand, supply, distance_method="telepathy")

    def test_conservation_law(self):
        """2SFCA 보존법칙: 공급시설이 흡수하는 수요량은 공급량과 같아야 한다."""
        G = _detour_graph()
        a = AccessibilityAnalyzer(G)
        demand = self._demand([(127.000, 37.500), (127.001, 37.520)], [1000.0, 2000.0])
        supply = self._supply([(127.002, 37.500)], [500.0])

        d0 = WALK_15MIN_M
        m = a.network_distance_matrix(demand, supply, cutoff_m=d0)
        w = _decay(m, d0, "gaussian")
        pop = demand["population"].to_numpy(dtype=float)
        cap = supply["capacity"].to_numpy(dtype=float)

        weighted_demand = (w * pop[:, None]).sum(axis=0)
        R = cap[0] / weighted_demand[0]
        captured = float((pop * w[:, 0] * R).sum())

        assert captured == pytest.approx(cap[0], rel=1e-9)

    def test_decay_weights_match_public_matrix(self):
        """공개 거리 행렬로 계산한 가중치와 점수 계산이 일치해야 한다."""
        G = _detour_graph()
        a = AccessibilityAnalyzer(G)
        demand = self._demand([(127.000, 37.500)], [1000.0])
        supply = self._supply([(127.001, 37.520)], [500.0])   # C: 도로망 1,000m

        d0 = WALK_15MIN_M
        m = a.network_distance_matrix(demand, supply, cutoff_m=d0)
        w = _decay(m, d0, "gaussian")
        assert w[0, 0] > 0.0
        expected = float(w[0, 0] * (500.0 / (1000.0 * w[0, 0])))
        got = a.two_sfca(demand, supply, catchment_minutes=15,
                         distance_method="network").iloc[0]
        assert got == pytest.approx(expected)


class TestFifteenMinCityNetworkDistance:
    def _amenities(self, coords, cats):
        return _point_gdf(coords, category=cats)

    def test_network_blocks_straight_reachable_amenity(self):
        """B는 직선거리로 15분 안이지만 도로망으로는 2,000m → 네트워크는 0점."""
        G = _detour_graph()
        grid = _point_gdf([(127.000, 37.500)])
        amenities = self._amenities([(127.002, 37.500)], ["grocery"])

        straight = fifteen_min_city_score(grid, amenities, network=None)
        network = fifteen_min_city_score(grid, amenities, network=G)

        assert straight.iloc[0] > 0.0
        assert network.iloc[0] == 0.0

    def test_network_reaches_amenity_straight_cannot(self):
        """C는 직선거리 2,200m지만 도로망 1,000m → 네트워크만 도달."""
        G = _detour_graph()
        grid = _point_gdf([(127.000, 37.500)])
        amenities = self._amenities([(127.001, 37.520)], ["grocery"])

        straight = fifteen_min_city_score(grid, amenities, network=None)
        network = fifteen_min_city_score(grid, amenities, network=G)

        assert straight.iloc[0] == 0.0
        assert network.iloc[0] == pytest.approx(1.0)   # 6그룹 중 1그룹 도달

    def test_network_method_without_graph_raises(self):
        grid = _point_gdf([(127.000, 37.500)])
        amenities = self._amenities([(127.002, 37.500)], ["grocery"])
        with pytest.raises(ValueError):
            fifteen_min_city_score(grid, amenities, distance_method="network")

    def test_score_range_preserved_with_network(self):
        G = _detour_graph()
        grid = _point_gdf([(127.000, 37.500), (127.002, 37.500)])
        cats = ["grocery", "restaurant", "school", "hospital", "park", "subway"]
        amenities = self._amenities([(127.000, 37.500)] * len(cats), cats)
        s = fifteen_min_city_score(grid, amenities, network=G)
        assert s.between(0, 6).all()
