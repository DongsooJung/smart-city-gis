"""
공간 격자·지오메트리 유틸리티

`create_fishnet` — 경계 폴리곤을 덮는 정사각 격자(fishnet) 생성.
분석 단위 그리드를 만드는 표준 진입점이다.
"""
from __future__ import annotations

import logging

import numpy as np
import geopandas as gpd
from shapely.geometry import box

logger = logging.getLogger(__name__)

# 한국 표준 투영좌표계 (중부원점 TM) — 거리(m) 계산용
METRIC_CRS = 5186


def create_fishnet(
    boundary: gpd.GeoDataFrame,
    cell_size: float = 100.0,
    clip: bool = True,
    metric_crs: int = METRIC_CRS,
) -> gpd.GeoDataFrame:
    """
    경계를 덮는 정사각 격자(fishnet) 생성.

    거리 단위(m) 격자를 만들기 위해 내부적으로 `metric_crs`(기본 5186)로 투영해
    격자를 생성한 뒤, 입력 경계의 원래 CRS로 되돌려 반환한다.

    Args:
        boundary: 격자를 씌울 경계 폴리곤(들). CRS 필수.
        cell_size: 셀 한 변 길이(m). 기본 100m.
        clip: True면 경계와 교차하는 셀만 유지(경계로 clip).
        metric_crs: 격자 생성용 투영 좌표계(EPSG).

    Returns:
        ['cell_id', 'geometry'] 격자 GeoDataFrame (입력 경계와 동일 CRS).
    """
    if boundary.crs is None:
        raise ValueError("boundary에 CRS가 필요합니다.")
    if cell_size <= 0:
        raise ValueError("cell_size는 0보다 커야 합니다.")

    original_crs = boundary.crs
    b = boundary.to_crs(metric_crs)
    minx, miny, maxx, maxy = b.total_bounds

    xs = np.arange(minx, maxx + cell_size, cell_size)
    ys = np.arange(miny, maxy + cell_size, cell_size)

    cells = [
        box(x, y, x + cell_size, y + cell_size)
        for x in xs[:-1]
        for y in ys[:-1]
    ]
    grid = gpd.GeoDataFrame({"geometry": cells}, crs=metric_crs)

    if clip:
        union = b.geometry.union_all() if hasattr(b.geometry, "union_all") else b.geometry.unary_union
        mask = grid.intersects(union)
        grid = grid.loc[mask].reset_index(drop=True)

    grid.insert(0, "cell_id", range(len(grid)))
    grid = grid.to_crs(original_crs)
    logger.info("fishnet 생성: %d 셀 (%.0fm)", len(grid), cell_size)
    return grid
