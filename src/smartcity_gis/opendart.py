"""
OpenDART (금융감독원 전자공시시스템) API 클라이언트.

상장기업의 정기보고서 주요 재무계정을 조회한다. 주 사용처는 2026년 1분기
상위 기업의 **매출액 / 영업이익** 수집이다.

OpenDART API 특징:
    - corpCode.xml : 전체 공시대상 회사 고유번호(corp_code) ↔ 종목코드(stock_code) 매핑.
    - fnlttSinglAcnt.json : 단일회사 주요계정 (매출액/영업이익/당기순이익 등).
    - 시가총액 랭킹은 제공하지 않으므로 "상위 100개" 종목 목록은 외부에서 주입한다
      (기본값: data/kospi_top100.csv).

사용 예:
    >>> from smartcity_gis.opendart import OpenDartClient, collect_financials
    >>> client = OpenDartClient(api_key="...")            # 또는 OPENDART_API_KEY 환경변수
    >>> df = collect_financials(client, year=2026, quarter=1)
    >>> df[["corp_name", "revenue", "operating_profit"]].head()

CLI:
    python -m smartcity_gis.opendart --year 2026 --quarter 1 \
        --key $OPENDART_API_KEY --out data/processed/opendart_q1_2026.csv
"""
from __future__ import annotations

import io
import os
import time
import logging
import zipfile
import argparse
from pathlib import Path
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

import pandas as pd
import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

# 정기보고서 코드 (reprt_code)
REPRT_CODE = {
    1: "11013",  # 1분기보고서
    2: "11012",  # 반기보고서 (2분기 누적)
    3: "11014",  # 3분기보고서
    4: "11011",  # 사업보고서 (연간)
}

# 재무제표 구분 (fs_div): 연결(CFS) 우선, 없으면 별도(OFS) 로 폴백.
_FS_DIV_ORDER = ("CFS", "OFS")

# 계정명 매칭 — 회사·표준계정에 따라 표기가 다를 수 있어 후보를 나열한다.
_REVENUE_NAMES = ("매출액", "수익(매출액)", "영업수익")
_OP_PROFIT_PREFIX = "영업이익"  # "영업이익", "영업이익(손실)" 등

_DEFAULT_SEED = Path(__file__).resolve().parents[2] / "data" / "kospi_top100.csv"


class OpenDartApiError(RuntimeError):
    """OpenDART 가 정상(000) 이외의 status 를 반환했을 때."""


class OpenDartClient:
    """OpenDART OpenAPI 클라이언트.

    Args:
        api_key: 인증키. 미지정 시 환경변수 ``OPENDART_API_KEY`` 사용.
        session: 재사용할 requests.Session (선택).
        pause: 연속 호출 사이 대기(초). 과도한 트래픽 방지.
    """

    BASE_URL = "https://opendart.fss.or.kr/api"

    def __init__(
        self,
        api_key: Optional[str] = None,
        session: Optional[requests.Session] = None,
        pause: float = 0.05,
    ):
        self.api_key = api_key or os.getenv("OPENDART_API_KEY")
        if not self.api_key:
            raise ValueError("OPENDART_API_KEY 미설정 (api_key 인자 또는 환경변수 필요)")
        self.session = session or requests.Session()
        self.pause = pause
        self._corp_codes: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------
    # 저수준 요청
    # ------------------------------------------------------------------
    def _get(self, endpoint: str, **params) -> requests.Response:
        params["crtfc_key"] = self.api_key
        resp = self.session.get(f"{self.BASE_URL}/{endpoint}", params=params, timeout=30)
        resp.raise_for_status()
        if self.pause:
            time.sleep(self.pause)
        return resp

    def _get_json(self, endpoint: str, **params) -> dict:
        data = self._get(endpoint, **params).json()
        status = data.get("status")
        # 000: 정상, 013: 조회 데이터 없음 (에러가 아니라 빈 결과로 취급)
        if status not in ("000", "013"):
            raise OpenDartApiError(f"{endpoint}: status={status} {data.get('message')}")
        return data

    # ------------------------------------------------------------------
    # 고유번호(corp_code) 매핑
    # ------------------------------------------------------------------
    def download_corp_codes(self, force: bool = False) -> pd.DataFrame:
        """전체 공시대상 회사 고유번호 목록.

        Returns:
            DataFrame[corp_code, corp_name, stock_code, modify_date].
            stock_code 가 빈 문자열이면 비상장.
        """
        if self._corp_codes is not None and not force:
            return self._corp_codes

        resp = self._get("corpCode.xml")
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            xml_bytes = zf.read(zf.namelist()[0])

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
        df = pd.DataFrame(rows)
        self._corp_codes = df
        logger.info("corpCode 로드: 전체 %d개 (상장 %d개)", len(df), (df["stock_code"] != "").sum())
        return df

    def resolve_stock_codes(self, stock_codes: Iterable[str]) -> pd.DataFrame:
        """종목코드 목록 → corp_code/corp_name 매핑.

        corpCode.xml 을 권위 있는 소스로 사용한다. 매칭되지 않는 종목코드는
        결과에서 제외되고 경고 로그를 남긴다.
        """
        corp = self.download_corp_codes()
        listed = corp[corp["stock_code"] != ""].drop_duplicates("stock_code")
        lookup = listed.set_index("stock_code")

        resolved = []
        for code in stock_codes:
            code = str(code).strip().zfill(6)
            if code in lookup.index:
                row = lookup.loc[code]
                resolved.append(
                    {"corp_code": row["corp_code"], "corp_name": row["corp_name"], "stock_code": code}
                )
            else:
                logger.warning("종목코드 매칭 실패 (건너뜀): %s", code)
        return pd.DataFrame(resolved)

    # ------------------------------------------------------------------
    # 재무 주요계정
    # ------------------------------------------------------------------
    def fetch_major_accounts(
        self, corp_code: str, bsns_year: int, reprt_code: str, fs_div: str = "CFS"
    ) -> pd.DataFrame:
        """단일회사 주요계정 원본 응답(list) → DataFrame.

        조회 데이터가 없으면 빈 DataFrame.
        """
        data = self._get_json(
            "fnlttSinglAcnt.json",
            corp_code=corp_code,
            bsns_year=str(bsns_year),
            reprt_code=reprt_code,
            fs_div=fs_div,
        )
        return pd.DataFrame(data.get("list", []))

    def fetch_revenue_operating_profit(
        self, corp_code: str, year: int, quarter: int
    ) -> dict:
        """한 회사의 (해당 분기) 매출액·영업이익.

        연결(CFS) 우선 조회하고 데이터가 없으면 별도(OFS) 로 폴백한다.

        Returns:
            {'revenue': int|None, 'operating_profit': int|None, 'fs_div': str|None,
             'rcept_no': str|None}
        """
        reprt_code = REPRT_CODE[quarter]
        for fs_div in _FS_DIV_ORDER:
            df = self.fetch_major_accounts(corp_code, year, reprt_code, fs_div=fs_div)
            if df.empty:
                continue
            revenue = _pick_amount(df, _match_revenue)
            op_profit = _pick_amount(df, _match_operating_profit)
            if revenue is not None or op_profit is not None:
                rcept_no = df["rcept_no"].iloc[0] if "rcept_no" in df else None
                return {
                    "revenue": revenue,
                    "operating_profit": op_profit,
                    "fs_div": fs_div,
                    "rcept_no": rcept_no,
                }
        return {"revenue": None, "operating_profit": None, "fs_div": None, "rcept_no": None}


# ----------------------------------------------------------------------
# 계정 파싱 헬퍼
# ----------------------------------------------------------------------
def _parse_amount(value) -> Optional[int]:
    """'1,234,567' 또는 '-1,234' 형태의 금액 문자열 → int (원). 파싱 불가 시 None."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in ("", "-"):
        return None
    neg = False
    if text.startswith("(") and text.endswith(")"):  # 회계식 음수 표기
        neg, text = True, text[1:-1]
    try:
        amount = int(float(text))
    except ValueError:
        return None
    return -amount if neg else amount


def _match_revenue(account_nm: str) -> bool:
    return account_nm.strip() in _REVENUE_NAMES


def _match_operating_profit(account_nm: str) -> bool:
    return account_nm.strip().startswith(_OP_PROFIT_PREFIX)


def _pick_amount(df: pd.DataFrame, matcher) -> Optional[int]:
    """손익계산서(IS/CIS) 행에서 matcher 에 맞는 계정의 당기금액을 반환."""
    if df.empty or "account_nm" not in df:
        return None
    rows = df
    if "sj_div" in df:
        rows = df[df["sj_div"].isin(["IS", "CIS"])]
        if rows.empty:
            rows = df
    for _, row in rows.iterrows():
        if matcher(str(row.get("account_nm", ""))):
            amount = _parse_amount(row.get("thstrm_amount"))
            if amount is not None:
                return amount
    return None


# ----------------------------------------------------------------------
# 상위 종목 재무 수집
# ----------------------------------------------------------------------
def load_seed_stock_codes(path: Optional[Path] = None) -> pd.DataFrame:
    """시드 종목 목록(name, stock_code) CSV 로드. '#' 주석행은 무시."""
    path = Path(path) if path else _DEFAULT_SEED
    df = pd.read_csv(path, comment="#", dtype={"stock_code": str})
    df["stock_code"] = df["stock_code"].str.strip().str.zfill(6)
    return df


def collect_financials(
    client: OpenDartClient,
    year: int,
    quarter: int,
    stock_codes: Optional[Iterable[str]] = None,
    seed_path: Optional[Path] = None,
    limit: Optional[int] = 100,
) -> pd.DataFrame:
    """상위 종목들의 (year, quarter) 매출액·영업이익을 수집한다.

    Args:
        client: 인증된 OpenDartClient.
        year: 사업연도 (예: 2026).
        quarter: 분기 (1~4). 1분기=11013, 반기=11012, 3분기=11014, 사업보고서=11011.
        stock_codes: 종목코드 목록. 미지정 시 seed CSV 사용.
        seed_path: 시드 CSV 경로 (기본 data/kospi_top100.csv).
        limit: 상위 N개만 사용 (기본 100). None 이면 전체.

    Returns:
        DataFrame[corp_name, stock_code, corp_code, revenue, operating_profit,
                  operating_margin, fs_div, rcept_no] — 매출액 내림차순 정렬.
    """
    if stock_codes is None:
        seed = load_seed_stock_codes(seed_path)
        stock_codes = seed["stock_code"].tolist()
    stock_codes = list(stock_codes)
    if limit is not None:
        stock_codes = stock_codes[:limit]

    resolved = client.resolve_stock_codes(stock_codes)
    records = []
    for _, row in resolved.iterrows():
        fin = client.fetch_revenue_operating_profit(row["corp_code"], year, quarter)
        records.append(
            {
                "corp_name": row["corp_name"],
                "stock_code": row["stock_code"],
                "corp_code": row["corp_code"],
                "revenue": fin["revenue"],
                "operating_profit": fin["operating_profit"],
                "fs_div": fin["fs_div"],
                "rcept_no": fin["rcept_no"],
            }
        )
        logger.info(
            "%s: 매출 %s / 영업이익 %s",
            row["corp_name"],
            _fmt(fin["revenue"]),
            _fmt(fin["operating_profit"]),
        )

    df = pd.DataFrame(records)
    if not df.empty:
        df["operating_margin"] = _safe_ratio(df["operating_profit"], df["revenue"])
        df = df.sort_values("revenue", ascending=False, na_position="last").reset_index(drop=True)
    return df


def _safe_ratio(numer: pd.Series, denom: pd.Series) -> pd.Series:
    """영업이익률(%) = 영업이익 / 매출액 * 100. 매출 0/결측 시 NaN."""
    return (numer / denom * 100).where((denom.notna()) & (denom != 0)).round(2)


def _fmt(amount: Optional[int]) -> str:
    return "N/A" if amount is None else f"{amount:,}원"


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="smartcity_gis.opendart",
        description="OpenDART 상위 기업 분기 매출액·영업이익 수집",
    )
    p.add_argument("--year", type=int, default=2026, help="사업연도 (기본 2026)")
    p.add_argument("--quarter", type=int, default=1, choices=[1, 2, 3, 4], help="분기 (기본 1)")
    p.add_argument("--key", default=None, help="OpenDART 인증키 (기본 OPENDART_API_KEY 환경변수)")
    p.add_argument("--seed", default=None, help="시드 종목 CSV 경로 (기본 data/kospi_top100.csv)")
    p.add_argument("--limit", type=int, default=100, help="상위 N개 (기본 100)")
    p.add_argument(
        "--out",
        default="data/processed/opendart_q1_2026.csv",
        help="결과 CSV 저장 경로",
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _build_parser().parse_args(argv)

    client = OpenDartClient(api_key=args.key)
    seed_path = Path(args.seed) if args.seed else None
    df = collect_financials(
        client, year=args.year, quarter=args.quarter, seed_path=seed_path, limit=args.limit
    )

    if df.empty:
        logger.warning("수집된 데이터가 없습니다.")
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8-sig")

    n_ok = df["revenue"].notna().sum()
    print(f"\n{args.year}년 {args.quarter}분기 — {len(df)}개 회사 (매출 확보 {n_ok}개)")
    print(f"저장: {out}\n")
    with pd.option_context("display.max_rows", 20, "display.unicode.east_asian_width", True):
        show = df.head(20).copy()
        for col in ("revenue", "operating_profit"):
            show[col] = show[col].map(lambda v: f"{v:,}" if pd.notna(v) else "N/A")
        print(show[["corp_name", "revenue", "operating_profit", "operating_margin", "fs_div"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
