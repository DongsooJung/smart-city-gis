"""
Smart City GIS Analytics

스마트시티 정책 시뮬레이션·도시 인프라 분석을 위한 GIS 도구 모음.

주요 분석:
    - Walkability (보행성 지수)
    - Accessibility (접근성: 학교/병원/지하철)
    - Heat Island (도시 열섬)
    - Land Use Mix (토지이용 다양성)
    - 15-Minute City (15분 도시 지수)

데이터 소스:
    - NSDI (국가공간정보포털): https://www.nsdi.go.kr
    - V-World (브이월드): http://map.vworld.kr
    - KOSIS (통계청): https://kosis.kr
    - OpenStreetMap (osmnx)
    - Sentinel-2 (Copernicus): 위성영상

사용 예:
    >>> from smartcity_gis import compute_walkability, AccessibilityAnalyzer
    >>> walkability = compute_walkability(grid, amenities, network)
    >>> analyzer = AccessibilityAnalyzer(network)
    >>> isochrones = analyzer.get_isochrone(point, [5, 10, 15])
"""

__version__ = "0.1.0"
__author__ = "Dongsoo Jung"
__email__ = "jds068888@gmail.com"

from smartcity_gis.walkability import compute_walkability  # noqa: F401
from smartcity_gis.accessibility import AccessibilityAnalyzer  # noqa: F401
from smartcity_gis.api_clients import NSDIClient, VWorldClient  # noqa: F401

__all__ = [
    "compute_walkability",
    "AccessibilityAnalyzer",
    "NSDIClient",
    "VWorldClient",
]
