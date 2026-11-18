"""OpenDART 클라이언트 단위 테스트 — 네트워크 없이 파싱/집계 로직 검증.

실제 API 호출은 requests.Session 을 목(mock)으로 대체한다.
"""
import io
import sys
import zipfile
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

# opendart 모듈만 직접 로드한다. 패키지 __init__ 은 geopandas 등 무거운
# 지리공간 의존성을 임포트하므로 우회한다 (opendart 자체는 불필요).
_SPEC = importlib.util.spec_from_file_location(
    "smartcity_gis_opendart",
    Path(__file__).parent.parent / "src" / "smartcity_gis" / "opendart.py",
)
opendart = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(opendart)

OpenDartClient = opendart.OpenDartClient
OpenDartApiError = opendart.OpenDartApiError
REPRT_CODE = opendart.REPRT_CODE
_parse_amount = opendart._parse_amount
_match_revenue = opendart._match_revenue
_match_operating_profit = opendart._match_operating_profit
_pick_amount = opendart._pick_amount
_safe_ratio = opendart._safe_ratio
collect_financials = opendart.collect_financials
load_seed_stock_codes = opendart.load_seed_stock_codes


# ----------------------------------------------------------------------
# 금액 파싱
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1,234,567", 1234567),
        ("-1,234", -1234),
        ("(5,000)", -5000),   # 회계식 음수
        ("", None),
        ("-", None),
        (None, None),
        ("42", 42),
    ],
)
def test_parse_amount(raw, expected):
    assert _parse_amount(raw) == expected


def test_account_matchers():
    assert _match_revenue("매출액")
    assert _match_revenue("수익(매출액)")
    assert not _match_revenue("매출원가")
    assert _match_operating_profit("영업이익")
    assert _match_operating_profit("영업이익(손실)")
    assert not _match_operating_profit("영업외수익")


def test_pick_amount_prefers_income_statement():
    df = pd.DataFrame(
        [
            {"sj_div": "BS", "account_nm": "매출액", "thstrm_amount": "999"},   # 오분류(무시돼야)
            {"sj_div": "IS", "account_nm": "매출액", "thstrm_amount": "1,000,000"},
            {"sj_div": "IS", "account_nm": "영업이익", "thstrm_amount": "-2,000"},
        ]
    )
    assert _pick_amount(df, _match_revenue) == 1_000_000
    assert _pick_amount(df, _match_operating_profit) == -2_000


def test_safe_ratio_handles_zero_and_nan():
    numer = pd.Series([200.0, 50.0, None])
    denom = pd.Series([1000.0, 0.0, 500.0])
    out = _safe_ratio(numer, denom)
    assert out.iloc[0] == 20.0
    assert pd.isna(out.iloc[1])   # 0 나눗셈
    assert pd.isna(out.iloc[2])   # 결측 분자


def test_reprt_code_mapping():
    assert REPRT_CODE[1] == "11013"  # 1분기
    assert REPRT_CODE[4] == "11011"  # 사업보고서


# ----------------------------------------------------------------------
# 시드 CSV
# ----------------------------------------------------------------------
def test_load_seed_stock_codes():
    df = load_seed_stock_codes()
    assert {"name", "stock_code"} <= set(df.columns)
    assert (df["stock_code"].str.len() == 6).all()          # 6자리 zero-pad
    assert "005930" in set(df["stock_code"])                # 삼성전자


# ----------------------------------------------------------------------
# 목(mock) 기반 통합 흐름
# ----------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, json_data=None, content=None):
        self._json = json_data
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


def _corpcode_zip_bytes():
    xml = (
        "<result>"
        "<list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name>"
        "<stock_code>005930</stock_code><modify_date>20260101</modify_date></list>"
        "<list><corp_code>00164779</corp_code><corp_name>SK하이닉스</corp_name>"
        "<stock_code>000660</stock_code><modify_date>20260101</modify_date></list>"
        "</result>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", xml.encode("utf-8"))
    return buf.getvalue()


class _FakeSession:
    """corpCode.xml 과 fnlttSinglAcnt.json 응답을 흉내낸다."""

    def get(self, url, params=None, timeout=None):
        if url.endswith("corpCode.xml"):
            return _FakeResponse(content=_corpcode_zip_bytes())
        if url.endswith("fnlttSinglAcnt.json"):
            corp = params["corp_code"]
            if params["fs_div"] != "CFS":
                return _FakeResponse(json_data={"status": "013", "message": "no data", "list": []})
            revenue = "71,000,000,000,000" if corp == "00126380" else "12,000,000,000,000"
            op = "6,000,000,000,000" if corp == "00126380" else "-1,000,000,000,000"
            return _FakeResponse(
                json_data={
                    "status": "000",
                    "message": "정상",
                    "list": [
                        {"rcept_no": "20260515000001", "sj_div": "IS",
                         "account_nm": "매출액", "thstrm_amount": revenue},
                        {"rcept_no": "20260515000001", "sj_div": "IS",
                         "account_nm": "영업이익", "thstrm_amount": op},
                    ],
                }
            )
        raise AssertionError(f"unexpected url {url}")


def _client():
    return OpenDartClient(api_key="test-key", session=_FakeSession(), pause=0)


def test_resolve_stock_codes_skips_unknown(caplog):
    client = _client()
    resolved = client.resolve_stock_codes(["005930", "999999"])
    assert list(resolved["corp_code"]) == ["00126380"]
    assert "999999" in caplog.text


def test_collect_financials_end_to_end():
    client = _client()
    df = collect_financials(client, year=2026, quarter=1, stock_codes=["005930", "000660"])
    # 매출 내림차순 → 삼성전자 먼저
    assert list(df["corp_name"]) == ["삼성전자", "SK하이닉스"]
    assert df.iloc[0]["revenue"] == 71_000_000_000_000
    assert df.iloc[0]["operating_profit"] == 6_000_000_000_000
    assert df.iloc[0]["fs_div"] == "CFS"
    # 영업이익률 = 6/71*100 ≈ 8.45
    assert df.iloc[0]["operating_margin"] == pytest.approx(8.45, abs=0.05)
    assert df.iloc[1]["operating_profit"] == -1_000_000_000_000


def test_api_error_raised_on_bad_status():
    class _ErrSession:
        def get(self, url, params=None, timeout=None):
            return _FakeResponse(json_data={"status": "020", "message": "요청 제한 초과"})

    client = OpenDartClient(api_key="k", session=_ErrSession(), pause=0)
    with pytest.raises(OpenDartApiError):
        client.fetch_major_accounts("00126380", 2026, "11013")
