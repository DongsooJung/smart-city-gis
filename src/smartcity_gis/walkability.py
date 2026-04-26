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


def compute_walkability(
    grid: gpd.GeoDataFrame,
    amenities: gpd.GeoDataFrame,
    network=None,
    decay: str = "exponential",
) -> gpd.GeoDataFrame:
    """
    그리드 셀별 보행성 지수 계산.

    Args:
        grid: 분석 단위 그리드 (100m 격자 권장)
        amenities: POI GeoDataFrame ['category', 'geometry']
        network: osmnx 그래프 (network distance 계산용, None이면 직선거리)
        decay: 'linear' | 'exponential' | 'gaussian'

    Returns:
        grid + ['walkability_score', '_subscore_diversity', ...] 컬럼
    """
    raise NotImplementedError(
        "TODO: 1) 각 셀 중심에서 amenity까지 거리 계산 (network or straight); "
        "2) decay function 적용 (exp(-d/d0)); "
        "3) 카테고리별 weight × decay 합산; "
        "4) POI_WEIGHTS 합으로 정규화 → 0-100 score"
    )


def diversity_index(amenities_in_buffer: pd.Series) -> float:
    """
    Shannon 엔트로피 기반 POI 다양성 지수.

    H = -Σ pᵢ × ln(pᵢ), 정규화: H / ln(n_categories)
    """
    raise NotImplementedError(
        "TODO: counts = amenities.value_counts(); p = counts / counts.sum(); "
        "H = -np.sum(p * np.log(p)); return H / np.log(len(counts))"
    )


def intersection_density(
    network,
    grid: gpd.GeoDataFrame,
) -> pd.Series:
    """그리드 셀당 교차로(분기점) 수 / km²."""
    raise NotImplementedError(
        "TODO: nodes = list(network.nodes); spatial join with grid"
    )


def population_density(
    grid: gpd.GeoDataFrame,
    population: gpd.GeoDataFrame,
) -> pd.Series:
    """그리드 셀당 인구밀도 (인/km²)."""
    raise NotImplementedError("TODO: areal interpolation 또는 centroid join")
