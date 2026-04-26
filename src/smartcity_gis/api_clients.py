"""
공공데이터 API 클라이언트

NSDI / V-World / KOSIS / 도로명주소 API 통합 래퍼.
"""
from __future__ import annotations

import os
import logging
from typing import Optional

import pandas as pd
import geopandas as gpd
import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()


class NSDIClient:
    """국가공간정보포털 OpenAPI 클라이언트.

    제공 데이터:
        - 행정경계 (시도/시군구/읍면동)
        - 도로망
        - 건물 통합 정보
        - 토지이용 현황
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("NSDI_API_KEY")
        if not self.api_key:
            raise ValueError("NSDI_API_KEY 미설정")
        self.base_url = "https://api.vworld.kr/req/data"

    def fetch_admin_boundary(
        self,
        level: str = "sgg",
        sido_code: Optional[str] = None,
    ) -> gpd.GeoDataFrame:
        """
        행정경계 GeoDataFrame 반환.

        Args:
            level: 'sido' | 'sgg' | 'emd'
            sido_code: 특정 시도만 (예: '11' = 서울)
        """
        raise NotImplementedError(
            "TODO: requests.get(NSDI endpoint) → GeoJSON → gpd.read_file()"
        )

    def fetch_buildings(
        self,
        bbox: tuple[float, float, float, float],
    ) -> gpd.GeoDataFrame:
        """건물 통합정보를 GeoDataFrame으로 반환."""
        raise NotImplementedError("TODO: bbox 내 건물 폴리곤 + 용도/높이/건축연도")


class VWorldClient:
    """V-World 2D/3D 지도 데이터 API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("VWORLD_API_KEY")

    def search_address(self, query: str) -> dict:
        """주소 검색 → 좌표 + 행정코드 반환."""
        raise NotImplementedError("TODO: V-World 지오코더 API")


class KosisClient:
    """KOSIS 통계청 API 클라이언트.

    제공 데이터:
        - 인구 (시군구 단위)
        - 가구
        - 사업체
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("KOSIS_API_KEY")

    def fetch_population_by_sgg(self, year: int) -> pd.DataFrame:
        """시군구별 인구 통계."""
        raise NotImplementedError("TODO: KOSIS OpenAPI 호출 + 정규화")


class OSMClient:
    """OSMnx 래퍼 — OpenStreetMap 도로망/POI."""

    @staticmethod
    def fetch_road_network(place: str, network_type: str = "walk"):
        """
        Args:
            place: '서울특별시 강남구' 등
            network_type: 'walk' | 'bike' | 'drive' | 'all'
        """
        raise NotImplementedError(
            "TODO: import osmnx as ox; ox.graph_from_place(place, network_type)"
        )

    @staticmethod
    def fetch_amenities(
        place: str,
        tags: dict = None,
    ) -> gpd.GeoDataFrame:
        """편의시설 POI 추출 (학교/병원/카페 등)."""
        raise NotImplementedError(
            "TODO: ox.features_from_place(place, tags={'amenity': True})"
        )
