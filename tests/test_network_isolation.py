"""도로망 단절(고립) 셀 처리 단위 테스트.

선택 도로망은 실제로 여러 연결 컴포넌트로 나뉜다. 시설이 하나도 없는
조각(fragment)에 붙은 셀은 어떤 시설에도 경로가 없으므로 거리 기반 점수를
산출할 수 없다. 이때 0점을 "접근 불가 지역"으로 집계하면 데이터 결함이
지표처럼 보이므로, 단절 여부를 플래그로 분리해 검증한다.
"""
import sys
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from smartcity_gis.accessibility import (
    NetworkDistanceCalculator,
    _metric_coords,
)
from smartcity_gis.walkability import compute_walkability


def _two_component_graph():
    """주요 연결 요소(M1–M2)와 시설이 없는 단절 조각(F1–F2).

    F1은 M1에서 직선거리로 약 111m지만 도로망으로는 연결되지 않는다.
    따라서 직선거리 기준으로는 "도달 가능"으로 보이지만, 네트워크 거리에서는
    거리 산출이 불가능한 결함 셀로 판정되어야 한다.
    """
    G = nx.Graph()
    G.add_node("M1", x=127.000, y=37.500)
    G.add_node("M2", x=127.001, y=37.500)
    G.add_edge("M1", "M2", length=100.0)
    G.add_node("F1", x=127.000, y=37.501)
    G.add_node("F2", x=127.0001, y=37.501)
    G.add_edge("F1", "F2", length=100.0)
    return G


def _points(coords, **columns):
    """(lon, lat) 리스트 → EPSG:4326 GeoDataFrame."""
    return gpd.GeoDataFrame(
        columns,
        geometry=[Point(lon, lat) for lon, lat in coords],
        crs="EPSG:4326",
    )


class TestIsolatedOrigins:
    def test_fragment_without_destination_is_isolated(self):
        G = _two_component_graph()
        calc = NetworkDistanceCalculator(G)
        origins = _points([(127.000, 37.500), (127.000, 37.501)])
        dests = _points([(127.000, 37.500)])

        mask = calc.isolated_origins(_metric_coords(origins), _metric_coords(dests))

        assert mask.dtype == bool
        assert mask.tolist() == [False, True]

    def test_same_component_is_not_isolated(self):
        """단절 여부는 거리와 무관하게 컴포넌트 구조로만 판정된다."""
        G = _two_component_graph()
        calc = NetworkDistanceCalculator(G)
        origins = _points([(127.000, 37.500)])
        dests = _points([(127.001, 37.500)])

        mask = calc.isolated_origins(_metric_coords(origins), _metric_coords(dests))

        assert mask.tolist() == [False]

    def test_empty_inputs_return_empty_mask(self):
        calc = NetworkDistanceCalculator(_two_component_graph())
        assert calc.isolated_origins(np.empty((0, 2)), _metric_coords(_points([(127.0, 37.5)]))).size == 0
        assert calc.isolated_origins(_metric_coords(_points([(127.0, 37.5)])), np.empty((0, 2))).tolist() == [False]


class TestWalkabilityIsolationFlag:
    def _grid(self):
        return _points([(127.000, 37.500), (127.000, 37.501)], cell_id=[0, 1])

    def _amenities(self):
        return _points([(127.000, 37.500)], category=["grocery"])

    def test_network_mode_adds_isolation_column(self):
        G = _two_component_graph()
        out = compute_walkability(self._grid(), self._amenities(), network=G)

        assert "_network_isolated" in out.columns
        assert out["_network_isolated"].tolist() == [False, True]

    def test_isolated_cell_scores_zero_but_connected_cell_does_not(self):
        G = _two_component_graph()
        out = compute_walkability(self._grid(), self._amenities(), network=G)

        assert out["walkability_score"].iloc[0] > 0.0
        assert out["walkability_score"].iloc[1] == 0.0

    def test_straight_mode_has_no_isolation_column(self):
        """직선거리에는 도로망 단절 개념이 없으므로 플래그를 만들지 않는다.

        단절 조각의 셀도 직선거리로는 M1의 시설(111m)에 "도달"하므로 점수가
        나오고, 그것이 네트워크 기준과 달라지는 이유를 보여 준다.
        """
        out = compute_walkability(self._grid(), self._amenities(), distance_method="straight")

        assert "_network_isolated" not in out.columns
        assert (out["walkability_score"] > 0.0).all()

    def test_auto_mode_uses_network_and_sets_flag(self):
        G = _two_component_graph()
        out = compute_walkability(self._grid(), self._amenities(), network=G)

        assert "_network_isolated" in out.columns
        assert out["_network_isolated"].sum() == 1
