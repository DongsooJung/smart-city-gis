"""
Smart City GIS Analytics

스마트시티 정책 시뮬레이션·도시 인프라 분석을 위한 GIS 도구 모음.

주요 분석:
    - Walkability (보행성 지수)
    - Accessibility (접근성: 2SFCA / gravity / isochrone)
    - 15-Minute City (15분 도시 지수)
    - Land Use Mix (토지이용 다양성)

데이터 소스:
    - NSDI (국가공간정보포털): https://www.nsdi.go.kr
    - V-World (브이월드): http://map.vworld.kr
    - KOSIS (통계청): https://kosis.kr
    - OpenStreetMap (osmnx)

사용 예:
    >>> from smartcity_gis import create_fishnet, compute_walkability
    >>> grid = create_fishnet(boundary, cell_size=100)
    >>> walk = compute_walkability(grid, amenities)
    >>> from smartcity_gis import AccessibilityAnalyzer, fifteen_min_city_score
    >>> score = fifteen_min_city_score(grid, amenities)
"""

__version__ = "0.3.0"
__author__ = "Dongsoo Jung"
__email__ = "jds068888@gmail.com"

from smartcity_gis.accessibility import (
    AccessibilityAnalyzer,
    NetworkDistanceCalculator,
    fifteen_min_city_score,
)
from smartcity_gis.api_clients import NSDIClient, VWorldClient
from smartcity_gis.geometry import create_fishnet
from smartcity_gis.walkability import compute_walkability

__all__ = [
    "AccessibilityAnalyzer",
    "NSDIClient",
    "NetworkDistanceCalculator",
    "VWorldClient",
    "compute_walkability",
    "create_fishnet",
    "fifteen_min_city_score",
]
