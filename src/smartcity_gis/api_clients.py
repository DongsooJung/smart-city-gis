"""
공공데이터 API 클라이언트

NSDI / V-World / KOSIS / 도로명주소 API 통합 래퍼.
"""
from __future__ import annotations

import io
import os
import time
import zipfile
import logging
import xml.etree.ElementTree as ET
from typing import Iterable, Optional

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


# ----------------------------------------------------------------------
# OpenDART (금융감독원 전자공시) — 상장기업 재무 데이터
# ----------------------------------------------------------------------
#
# 스마트시티 분석에서 산업·기업 입지 분석 시 상장기업 재무지표가 필요하다.
# OpenDART OpenAPI로 분기/사업보고서의 매출액·영업이익 등 주요계정을 수집한다.
#
# API 문서: https://opendart.fss.or.kr/guide/main.do
#
# 보고서 코드(reprt_code):
#     11013 = 1분기보고서 · 11012 = 반기보고서
#     11014 = 3분기보고서 · 11011 = 사업보고서(연간)

#: 분기(1~4) → OpenDART 보고서 코드
REPRT_CODE_BY_QUARTER = {1: "11013", 2: "11012", 3: "11014", 4: "11011"}

#: 매출액에 해당하는 계정명 (일반기업 '매출액', 금융/지주 '영업수익')
_REVENUE_ACCOUNTS = ("매출액", "영업수익")
#: 영업이익 계정명
_OPERATING_INCOME_ACCOUNTS = ("영업이익", "영업이익(손실)")


class OpenDartClient:
    """OpenDART 전자공시 OpenAPI 클라이언트.

    제공 데이터:
        - 고유번호(corp_code) ↔ 종목코드(stock_code) 매핑
        - 단일/다중회사 주요계정 (매출액·영업이익·당기순이익 등)

    사용 예:
        >>> dart = OpenDartClient(api_key="...")
        >>> codes = dart.get_corp_codes()                     # 전체 기업 목록
        >>> df = dart.get_financials_by_stock(
        ...     ["005930", "000660"], year=2026, quarter=1)
        >>> df[["corp_name", "revenue", "operating_income"]]
    """

    BASE_URL = "https://opendart.fss.or.kr/api"

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        timeout: int = 30,
        rate_limit_sec: float = 0.0,
    ):
        self.api_key = api_key or os.getenv("OPENDART_API_KEY")
        if not self.api_key:
            raise ValueError("OPENDART_API_KEY 미설정")
        self.timeout = timeout
        self.rate_limit_sec = rate_limit_sec
        self._session = requests.Session()
        self._corp_codes: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------
    # 고유번호(corp_code) 매핑
    # ------------------------------------------------------------------
    def get_corp_codes(self, *, listed_only: bool = False) -> pd.DataFrame:
        """전체 공시대상 기업의 고유번호 목록을 DataFrame으로 반환.

        corpCode.xml API는 ZIP(내부 CORPCODE.xml)을 반환한다.

        Args:
            listed_only: True면 종목코드가 있는 상장기업만 반환.

        Returns:
            columns = [corp_code, corp_name, stock_code, modify_date]
        """
        if self._corp_codes is None:
            resp = self._session.get(
                f"{self.BASE_URL}/corpCode.xml",
                params={"crtfc_key": self.api_key},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            # 인증 오류 등은 ZIP 대신 XML 에러 메시지가 온다.
            if resp.content[:2] != b"PK":
                self._raise_api_error(resp.content.decode("utf-8", "replace"))

            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                xml_bytes = zf.read(zf.namelist()[0])
            self._corp_codes = self._parse_corp_codes(xml_bytes)

        df = self._corp_codes
        if listed_only:
            df = df[df["stock_code"] != ""].reset_index(drop=True)
        return df.copy()

    @staticmethod
    def _parse_corp_codes(xml_bytes: bytes) -> pd.DataFrame:
        root = ET.fromstring(xml_bytes)
        rows = []
        for item in root.iter("list"):
            rows.append(
                {
                    "corp_code": (item.findtext("corp_code") or "").strip(),
                    "corp_name": (item.findtext("corp_name") or "").strip(),
                    "stock_code": (item.findtext("stock_code") or "").strip(),
                    "modify_date": (item.findtext("modify_date") or "").strip(),
                }
            )
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # 주요계정 (매출액·영업이익 등)
    # ------------------------------------------------------------------
    def get_major_accounts(
        self,
        corp_codes: Iterable[str],
        year: int,
        reprt_code: str,
    ) -> pd.DataFrame:
        """다중회사 주요계정 원본(long) DataFrame 반환.

        fnlttMultiAcnt.json — 계정별로 한 행씩(연결 CFS·개별 OFS 각각).

        Args:
            corp_codes: 고유번호 목록 (한 번의 호출로 여러 기업 조회).
            year: 사업연도 (예: 2026).
            reprt_code: 보고서 코드 (REPRT_CODE_BY_QUARTER 참고).
        """
        corp_codes = [c for c in corp_codes if c]
        if not corp_codes:
            return pd.DataFrame()

        params = {
            "crtfc_key": self.api_key,
            "corp_code": ",".join(corp_codes),
            "bsns_year": str(year),
            "reprt_code": reprt_code,
        }
        if self.rate_limit_sec:
            time.sleep(self.rate_limit_sec)
        resp = self._session.get(
            f"{self.BASE_URL}/fnlttMultiAcnt.json",
            params=params,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        payload = resp.json()

        status = payload.get("status")
        if status == "013":  # 조회된 데이터 없음
            logger.warning(
                "OpenDART 데이터 없음 (year=%s, reprt=%s, n=%d)",
                year, reprt_code, len(corp_codes),
            )
            return pd.DataFrame()
        if status != "000":
            self._raise_api_error(payload.get("message", status), status)

        return pd.DataFrame(payload.get("list", []))

    def get_financials_by_stock(
        self,
        stock_codes: Iterable[str],
        year: int,
        quarter: int = 1,
        *,
        batch_size: int = 100,
        fs_preference: tuple[str, ...] = ("CFS", "OFS"),
    ) -> pd.DataFrame:
        """종목코드 목록 → 기업별 매출액·영업이익 요약 DataFrame.

        연결재무제표(CFS)를 우선 사용하고, 없으면 개별재무제표(OFS)로 대체한다.
        분기 손익계산서 계정은 누적(3·6·9개월) 금액이다.

        Args:
            stock_codes: 6자리 종목코드 목록.
            year: 사업연도.
            quarter: 분기 (1~4).
            batch_size: fnlttMultiAcnt 1회 호출당 기업 수.
            fs_preference: 재무제표 구분 우선순위.

        Returns:
            columns = [stock_code, corp_code, corp_name, fs_div,
                       revenue, operating_income, reprt_code, bsns_year]
        """
        if quarter not in REPRT_CODE_BY_QUARTER:
            raise ValueError(f"quarter는 1~4 (입력값: {quarter})")
        reprt_code = REPRT_CODE_BY_QUARTER[quarter]

        stock_codes = [str(s).strip().zfill(6) for s in stock_codes if str(s).strip()]
        corp_map = self._stock_to_corp_map()

        pairs = [(s, corp_map[s]) for s in stock_codes if s in corp_map]
        missing = [s for s in stock_codes if s not in corp_map]
        if missing:
            logger.warning("고유번호 매핑 실패 %d건: %s", len(missing), ", ".join(missing))

        rows = []
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i : i + batch_size]
            raw = self.get_major_accounts(
                [c for _, c in batch], year, reprt_code
            )
            rows.extend(self._summarize(raw, fs_preference))

        result = pd.DataFrame(
            rows,
            columns=[
                "stock_code", "corp_code", "corp_name", "fs_div",
                "revenue", "operating_income", "reprt_code", "bsns_year",
            ],
        )
        return result

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------
    def _stock_to_corp_map(self) -> dict[str, str]:
        listed = self.get_corp_codes(listed_only=True)
        return dict(zip(listed["stock_code"], listed["corp_code"]))

    @classmethod
    def _summarize(
        cls,
        raw: pd.DataFrame,
        fs_preference: tuple[str, ...],
    ) -> list[dict]:
        """long-format 주요계정 → 기업별 1행 요약 (재무제표 우선순위 적용)."""
        if raw.empty:
            return []

        out = []
        for corp_code, grp in raw.groupby("corp_code", sort=False):
            chosen = None
            for fs_div in fs_preference:
                sub = grp[grp["fs_div"] == fs_div]
                if not sub.empty:
                    chosen = (fs_div, sub)
                    break
            if chosen is None:
                fs_div, sub = grp["fs_div"].iloc[0], grp
            else:
                fs_div, sub = chosen

            first = sub.iloc[0]
            out.append(
                {
                    "stock_code": str(first.get("stock_code", "")).strip(),
                    "corp_code": corp_code,
                    "corp_name": first.get("corp_name", ""),
                    "fs_div": fs_div,
                    "revenue": cls._pick_amount(sub, _REVENUE_ACCOUNTS),
                    "operating_income": cls._pick_amount(sub, _OPERATING_INCOME_ACCOUNTS),
                    "reprt_code": first.get("reprt_code", ""),
                    "bsns_year": first.get("bsns_year", ""),
                }
            )
        return out

    @classmethod
    def _pick_amount(cls, sub: pd.DataFrame, account_names: tuple[str, ...]):
        """계정명 후보 중 먼저 매칭되는 당기금액(thstrm_amount)을 정수로 반환."""
        for name in account_names:
            hit = sub[sub["account_nm"] == name]
            if not hit.empty:
                return cls._parse_amount(hit.iloc[0].get("thstrm_amount"))
        return None

    @staticmethod
    def _parse_amount(value) -> Optional[int]:
        """'1,234,567' / '-1,234' / '' → int | None."""
        if value is None:
            return None
        text = str(value).strip().replace(",", "")
        if text in ("", "-"):
            return None
        # 괄호 음수 표기 대응: (1,234) → -1234
        if text.startswith("(") and text.endswith(")"):
            text = "-" + text[1:-1]
        try:
            return int(float(text))
        except ValueError:
            return None

    @staticmethod
    def _raise_api_error(message: str, status: Optional[str] = None):
        prefix = f"OpenDART API 오류[{status}]" if status else "OpenDART API 오류"
        raise RuntimeError(f"{prefix}: {message}")
