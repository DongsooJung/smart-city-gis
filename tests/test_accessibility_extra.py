"""isochrone · 15분 도시 · create_fishnet 신규 기능 단위 테스트.

모두 순수 networkx / 직선거리 기반으로 osmnx 없이 검증한다.
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

from smartcity_gis.geometry import create_fishnet
from smartcity_gis.accessibility import (
    AccessibilityAnalyzer,
    fifteen_min_city_score,
    ESSENTIAL_CATEGORIES,
)


# ----------------------------------------------------------------------
# create_fishnet
# ----------------------------------------------------------------------
class TestCreateFishnet:
    def _boundary(self):
        # 강남 근방 1km 사각 경계 (경위도)
        return gpd.GeoDataFrame(
            {"geometry": [box(127.04, 37.49, 127.05, 37.50)]}, crs="EPSG:4326"
        )

    def test_returns_cells(self):
        grid = create_fishnet(self._boundary(), cell_size=200)
        assert len(grid) > 0
        assert "cell_id" in grid.columns
        assert grid.crs.to_epsg() == 4326  # 원본 CRS 유지

    def test_cell_size_affects_count(self):
        coarse = create_fishnet(self._boundary(), cell_size=500)
        fine = create_fishnet(self._boundary(), cell_size=100)
        assert len(fine) > len(coarse)

    def test_requires_crs(self):
        bad = gpd.GeoDataFrame({"geometry": [box(0, 0, 1, 1)]})
        with pytest.raises(ValueError):
            create_fishnet(bad)

    def test_rejects_nonpositive_size(self):
        with pytest.raises(ValueError):
            create_fishnet(self._boundary(), cell_size=0)


# ----------------------------------------------------------------------
# fifteen_min_city_score
# ----------------------------------------------------------------------
class TestFifteenMinCity:
    def _grid(self):
        cells = [box(i * 100, 0, (i + 1) * 100, 100) for i in range(3)]
        return gpd.GeoDataFrame({"geometry": cells}, crs="EPSG:5186")

    def test_score_range_0_6(self):
        grid = self._grid()
        amenities = gpd.GeoDataFrame(
            {"category": ["grocery", "hospital", "park"]},
            geometry=[Point(50, 50), Point(150, 50), Point(250, 50)],
            crs="EPSG:5186",
        )
        s = fifteen_min_city_score(grid, amenities)
        assert s.between(0, 6).all()
        assert len(s) == len(grid)

    def test_all_six_categories_full_score(self):
        # 모든 그룹의 대표 POI를 셀 바로 위에 배치 → 6점
        cats = ["grocery", "restaurant", "school", "hospital", "park", "subway"]
        pts = [Point(50, 50)] * len(cats)
        amenities = gpd.GeoDataFrame({"category": cats}, geometry=pts, crs="EPSG:5186")
        grid = gpd.GeoDataFrame({"geometry": [box(0, 0, 100, 100)]}, crs="EPSG:5186")
        s = fifteen_min_city_score(grid, amenities, minutes=15)
        assert s.iloc[0] == pytest.approx(6.0)

    def test_far_amenities_zero(self):
        grid = gpd.GeoDataFrame({"geometry": [box(0, 0, 100, 100)]}, crs="EPSG:5186")
        # 15분(≈1125m) 밖에 배치
        amenities = gpd.GeoDataFrame(
            {"category": ["grocery"]}, geometry=[Point(50000, 50000)], crs="EPSG:5186"
        )
        s = fifteen_min_city_score(grid, amenities)
        assert s.iloc[0] == 0.0

    def test_empty_amenities_zero(self):
        grid = self._grid()
        amenities = gpd.GeoDataFrame({"category": []}, geometry=[], crs="EPSG:5186")
        s = fifteen_min_city_score(grid, amenities)
        assert (s == 0).all()

    def test_missing_category_raises(self):
        grid = self._grid()
        bad = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs="EPSG:5186")
        with pytest.raises(ValueError):
            fifteen_min_city_score(grid, bad)

    def test_six_default_groups(self):
        assert len(ESSENTIAL_CATEGORIES) == 6


# ----------------------------------------------------------------------
# get_isochrone (순수 networkx 그리드 그래프)
# ----------------------------------------------------------------------
def _grid_graph(n=6, step_deg=0.002, lon0=127.05, lat0=37.50):
    """n×n 격자 그래프. 노드에 경위도 x·y 부여, 인접 노드 연결."""
    G = nx.Graph()
    idx = {}
    for i in range(n):
        for j in range(n):
            nid = i * n + j
            idx[(i, j)] = nid
            G.add_node(nid, x=lon0 + j * step_deg, y=lat0 + i * step_deg)
    for i in range(n):
        for j in range(n):
            if j + 1 < n:
                G.add_edge(idx[(i, j)], idx[(i, j + 1)])
            if i + 1 < n:
                G.add_edge(idx[(i, j)], idx[(i + 1, j)])
    return G, idx


class TestIsochrone:
    def test_requires_network(self):
        a = AccessibilityAnalyzer(network=None)
        with pytest.raises(ValueError):
            a.get_isochrone((127.05, 37.50))

    def test_returns_polygons_per_time(self):
        G, _ = _grid_graph()
        a = AccessibilityAnalyzer(G)
        res = a.get_isochrone((127.055, 37.505), trip_times=[5, 10, 15])
        assert len(res.isochrones) == 3
        assert set(res.isochrones["minutes"]) == {5, 10, 15}
        assert res.isochrones.geometry.is_valid.all()

    def test_larger_time_larger_area(self):
        G, _ = _grid_graph()
        a = AccessibilityAnalyzer(G)
        res = a.get_isochrone((127.055, 37.505), trip_times=[5, 20])
        areas = res.isochrones.to_crs(5186).set_index("minutes").geometry.area
        assert areas.loc[20] >= areas.loc[5]

    def test_output_is_wgs84(self):
        G, _ = _grid_graph()
        a = AccessibilityAnalyzer(G)
        res = a.get_isochrone((127.055, 37.505), trip_times=[10])
        assert res.isochrones.crs.to_epsg() == 4326
