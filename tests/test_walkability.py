"""Smart City GIS — walkability / accessibility 단위 테스트.

osmnx가 필요한 isochrone·15분도시 함수는 제외하고, 직선거리·통계 기반으로
구현된 핵심 알고리즘을 검증한다.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, box
import pytest
import networkx as nx

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from smartcity_gis.walkability import (
    compute_walkability,
    diversity_index,
    intersection_density,
    population_density,
    _decay_weight,
    POI_WEIGHTS,
)
from smartcity_gis.accessibility import AccessibilityAnalyzer


# ----------------------------------------------------------------------
# Fixtures — 합성 데이터 (투영좌표계 EPSG:5186, 단위 m)
# ----------------------------------------------------------------------
def make_grid(nx_cells=3, ny_cells=3, size=100.0):
    """size m 정사각형 셀로 구성된 nx×ny 격자."""
    cells = []
    for i in range(nx_cells):
        for j in range(ny_cells):
            cells.append(box(i * size, j * size, (i + 1) * size, (j + 1) * size))
    return gpd.GeoDataFrame({"geometry": cells}, crs="EPSG:5186")


@pytest.fixture
def sample_grid():
    return make_grid(3, 3, 100.0)


# ----------------------------------------------------------------------
# diversity_index
# ----------------------------------------------------------------------
class TestDiversityIndex:
    def test_empty_returns_zero(self):
        assert diversity_index(pd.Series([], dtype=object)) == 0.0

    def test_single_category_returns_zero(self):
        assert diversity_index(pd.Series(["cafe", "cafe", "cafe"])) == 0.0

    def test_even_distribution_returns_one(self):
        # 두 카테고리 균등 → 정규화 엔트로피 = 1
        result = diversity_index(pd.Series(["cafe", "park"]))
        assert result == pytest.approx(1.0)

    def test_uneven_between_zero_and_one(self):
        result = diversity_index(pd.Series(["cafe", "cafe", "cafe", "park"]))
        assert 0.0 < result < 1.0

    def test_more_even_is_higher(self):
        even = diversity_index(pd.Series(["a", "b", "c", "a", "b", "c"]))
        skewed = diversity_index(pd.Series(["a", "a", "a", "a", "b", "c"]))
        assert even > skewed


# ----------------------------------------------------------------------
# _decay_weight
# ----------------------------------------------------------------------
class TestDecayWeight:
    def test_zero_distance_is_one(self):
        for kind in ("linear", "exponential", "gaussian"):
            assert _decay_weight(np.array([0.0]), 400, kind)[0] == pytest.approx(1.0)

    def test_monotonic_decreasing(self):
        d = np.array([0, 100, 200, 400, 800], dtype=float)
        for kind in ("linear", "exponential", "gaussian"):
            w = _decay_weight(d, 400, kind)
            assert np.all(np.diff(w) <= 1e-12), f"{kind} not monotonic"

    def test_linear_clipped_at_zero(self):
        # 거리 > d0 면 0
        assert _decay_weight(np.array([800.0]), 400, "linear")[0] == 0.0


# ----------------------------------------------------------------------
# compute_walkability
# ----------------------------------------------------------------------
class TestWalkability:
    def test_score_in_0_100_range(self, sample_grid):
        amenities = gpd.GeoDataFrame(
            {"category": ["grocery", "cafe", "subway"]},
            geometry=[Point(150, 150), Point(160, 140), Point(250, 250)],
            crs="EPSG:5186",
        )
        out = compute_walkability(sample_grid, amenities)
        assert "walkability_score" in out.columns
        assert out["walkability_score"].between(0, 100).all()

    def test_high_score_in_dense_amenity_area(self, sample_grid):
        # 중앙 셀(150,150) 주변에 POI 밀집
        cats = ["grocery", "restaurant", "cafe", "subway", "school", "park"]
        pts = [Point(150 + dx, 150 + dy) for dx, dy in
               [(0, 0), (5, 5), (-5, 5), (5, -5), (-5, -5), (0, 10)]]
        amenities = gpd.GeoDataFrame({"category": cats}, geometry=pts, crs="EPSG:5186")
        out = compute_walkability(sample_grid, amenities)

        # 중앙 셀의 점수가 가장 높아야 함
        centroids = sample_grid.geometry.centroid
        center_mask = (centroids.x.between(100, 200) & centroids.y.between(100, 200))
        center_score = out.loc[center_mask, "walkability_score"].iloc[0]
        assert center_score == out["walkability_score"].max()
        assert center_score > 0

    def test_no_amenities_zero_score(self, sample_grid):
        amenities = gpd.GeoDataFrame(
            {"category": []}, geometry=[], crs="EPSG:5186"
        )
        out = compute_walkability(sample_grid, amenities)
        assert (out["walkability_score"] == 0).all()

    def test_missing_category_raises(self, sample_grid):
        bad = gpd.GeoDataFrame(geometry=[Point(150, 150)], crs="EPSG:5186")
        with pytest.raises(ValueError):
            compute_walkability(sample_grid, bad)

    def test_empty_grid(self):
        empty = gpd.GeoDataFrame({"geometry": []}, crs="EPSG:5186")
        amenities = gpd.GeoDataFrame(
            {"category": ["cafe"]}, geometry=[Point(0, 0)], crs="EPSG:5186"
        )
        out = compute_walkability(empty, amenities)
        assert len(out) == 0


# ----------------------------------------------------------------------
# population_density
# ----------------------------------------------------------------------
class TestPopulationDensity:
    def test_density_per_km2(self, sample_grid):
        # 100m 셀 = 0.01 km². 중앙 셀에 인구 100명 → 10,000 인/km²
        pop = gpd.GeoDataFrame(
            {"population": [100]}, geometry=[Point(150, 150)], crs="EPSG:5186"
        )
        density = population_density(sample_grid, pop)
        centroids = sample_grid.geometry.centroid
        center_mask = (centroids.x.between(100, 200) & centroids.y.between(100, 200))
        center_val = density[center_mask].iloc[0]
        assert center_val == pytest.approx(10000.0, rel=1e-6)

    def test_empty_cells_zero(self, sample_grid):
        pop = gpd.GeoDataFrame(
            {"population": [50]}, geometry=[Point(150, 150)], crs="EPSG:5186"
        )
        density = population_density(sample_grid, pop)
        # 9개 셀 중 1개만 값 있음
        assert (density > 0).sum() == 1

    def test_missing_population_col_raises(self, sample_grid):
        bad = gpd.GeoDataFrame(geometry=[Point(150, 150)], crs="EPSG:5186")
        with pytest.raises(ValueError):
            population_density(sample_grid, bad)


# ----------------------------------------------------------------------
# intersection_density
# ----------------------------------------------------------------------
class TestIntersectionDensity:
    def test_counts_high_degree_nodes(self):
        # 경위도 좌표를 가진 그래프; 한 노드가 차수 3
        G = nx.Graph()
        # 강남구 근방 좌표
        G.add_node(0, x=127.05, y=37.50)
        G.add_node(1, x=127.0501, y=37.5001)
        G.add_node(2, x=127.0499, y=37.5001)
        G.add_node(3, x=127.05, y=37.4999)
        G.add_edges_from([(0, 1), (0, 2), (0, 3)])  # 노드0 = 차수 3 교차로

        # 해당 좌표를 포함하는 격자 (경위도 → 5186 변환은 함수 내부 처리)
        cell = gpd.GeoDataFrame(
            {"geometry": [box(127.045, 37.495, 127.055, 37.505)]},
            crs="EPSG:4326",
        )
        density = intersection_density(G, cell)
        assert len(density) == 1
        assert density.iloc[0] > 0  # 교차로 1개 포함

    def test_no_intersections_returns_zero(self):
        G = nx.Graph()
        G.add_node(0, x=127.05, y=37.50)
        G.add_node(1, x=127.0501, y=37.5001)
        G.add_edge(0, 1)  # 차수 1·1 → 교차로 없음
        cell = gpd.GeoDataFrame(
            {"geometry": [box(127.045, 37.495, 127.055, 37.505)]},
            crs="EPSG:4326",
        )
        density = intersection_density(G, cell)
        assert (density == 0).all()


# ----------------------------------------------------------------------
# AccessibilityAnalyzer — 2SFCA / gravity
# ----------------------------------------------------------------------
class TestTwoSFCA:
    def test_2sfca_conservation(self):
        """2SFCA: Σ(A_i × P_i) = Σ(S_j)  (수요로 가중한 접근성 총합 = 총공급)."""
        demand = gpd.GeoDataFrame(
            {"population": [100, 200, 50]},
            geometry=[Point(0, 0), Point(500, 0), Point(0, 500)],
            crs="EPSG:5186",
        )
        supply = gpd.GeoDataFrame(
            {"capacity": [30, 20]},
            geometry=[Point(100, 100), Point(400, 400)],
            crs="EPSG:5186",
        )
        a = AccessibilityAnalyzer(network=None)
        # 충분히 큰 catchment로 모든 수요-공급 연결
        A = a.two_sfca(demand, supply, catchment_minutes=120, decay="threshold")

        total_supply = supply["capacity"].sum()
        weighted_access = (A.to_numpy() * demand["population"].to_numpy()).sum()
        assert weighted_access == pytest.approx(total_supply, rel=1e-6)

    def test_2sfca_closer_demand_higher_access(self):
        demand = gpd.GeoDataFrame(
            {"population": [100, 100]},
            geometry=[Point(100, 0), Point(5000, 0)],  # 하나는 가깝고 하나는 멂
            crs="EPSG:5186",
        )
        supply = gpd.GeoDataFrame(
            {"capacity": [50]}, geometry=[Point(0, 0)], crs="EPSG:5186"
        )
        a = AccessibilityAnalyzer(network=None)
        A = a.two_sfca(demand, supply, catchment_minutes=30, decay="gaussian")
        assert A.iloc[0] > A.iloc[1]

    def test_2sfca_missing_col_raises(self):
        demand = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs="EPSG:5186")
        supply = gpd.GeoDataFrame(
            {"capacity": [10]}, geometry=[Point(0, 0)], crs="EPSG:5186"
        )
        a = AccessibilityAnalyzer(network=None)
        with pytest.raises(ValueError):
            a.two_sfca(demand, supply)


class TestGravityModel:
    def test_gravity_closer_is_higher(self):
        origins = gpd.GeoDataFrame(
            geometry=[Point(100, 0), Point(1000, 0)], crs="EPSG:5186"
        )
        dest = gpd.GeoDataFrame(
            {"capacity": [100]}, geometry=[Point(0, 0)], crs="EPSG:5186"
        )
        a = AccessibilityAnalyzer(network=None)
        A = a.gravity_model(origins, dest, beta=1.0)
        assert A.iloc[0] > A.iloc[1]

    def test_gravity_more_attraction_higher(self):
        origins = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs="EPSG:5186")
        small = gpd.GeoDataFrame(
            {"capacity": [10]}, geometry=[Point(100, 0)], crs="EPSG:5186"
        )
        big = gpd.GeoDataFrame(
            {"capacity": [1000]}, geometry=[Point(100, 0)], crs="EPSG:5186"
        )
        a = AccessibilityAnalyzer(network=None)
        assert a.gravity_model(origins, big).iloc[0] > a.gravity_model(origins, small).iloc[0]


# osmnx 의존 기능은 설치 시에만 검증
class TestOsmnxDependent:
    def test_isochrone_skipped(self):
        pytest.importorskip("osmnx")
        pytest.skip("osmnx 설치 환경에서 별도 검증 필요")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
