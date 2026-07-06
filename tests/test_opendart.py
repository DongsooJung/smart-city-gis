"""OpenDartClient 단위 테스트.

네트워크 없이 파싱·요약·정렬 로직을 검증한다. HTTP 계층은 monkeypatch로 대체.
"""
import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from smartcity_gis.api_clients import OpenDartClient, REPRT_CODE_BY_QUARTER


# ----------------------------------------------------------------------
# corpCode.xml 파싱
# ----------------------------------------------------------------------
CORP_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<result>
  <list><corp_code>00126380</corp_code><corp_name>\xec\x82\xbc\xec\x84\xb1\xec\xa0\x84\xec\x9e\x90</corp_name><stock_code>005930</stock_code><modify_date>20240401</modify_date></list>
  <list><corp_code>00164779</corp_code><corp_name>SK\xed\x95\x98\xec\x9d\xb4\xeb\x8b\x89\xec\x8a\xa4</corp_name><stock_code>000660</stock_code><modify_date>20240401</modify_date></list>
  <list><corp_code>00999999</corp_code><corp_name>\xeb\xb9\x84\xec\x83\x81\xec\x9e\xa5\xea\xb8\xb0\xec\x97\x85</corp_name><stock_code> </stock_code><modify_date>20240401</modify_date></list>
</result>"""


def _zip_of(xml: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", xml)
    return buf.getvalue()


class TestParseCorpCodes:
    def test_parses_all_rows(self):
        df = OpenDartClient._parse_corp_codes(CORP_XML)
        assert list(df.columns) == ["corp_code", "corp_name", "stock_code", "modify_date"]
        assert len(df) == 3
        assert df.loc[0, "corp_code"] == "00126380"
        assert df.loc[0, "stock_code"] == "005930"

    def test_blank_stock_code_stripped(self):
        df = OpenDartClient._parse_corp_codes(CORP_XML)
        assert df.loc[2, "stock_code"] == ""


# ----------------------------------------------------------------------
# _parse_amount
# ----------------------------------------------------------------------
class TestParseAmount:
    @pytest.mark.parametrize("raw,expected", [
        ("1,234,567", 1234567),
        ("-5,000", -5000),
        ("(1,234)", -1234),
        ("", None),
        ("-", None),
        (None, None),
        ("42", 42),
    ])
    def test_various(self, raw, expected):
        assert OpenDartClient._parse_amount(raw) == expected


# ----------------------------------------------------------------------
# _summarize — 재무제표 우선순위 + 계정 추출
# ----------------------------------------------------------------------
def _row(corp_code, stock_code, account_nm, amount, fs_div="CFS"):
    return {
        "corp_code": corp_code, "stock_code": stock_code, "corp_name": "테스트",
        "account_nm": account_nm, "thstrm_amount": amount, "fs_div": fs_div,
        "reprt_code": "11013", "bsns_year": "2026",
    }


class TestSummarize:
    def test_extracts_revenue_and_operating_income(self):
        raw = pd.DataFrame([
            _row("A", "005930", "매출액", "1,000"),
            _row("A", "005930", "영업이익", "200"),
            _row("A", "005930", "당기순이익", "150"),
        ])
        out = OpenDartClient._summarize(raw, ("CFS", "OFS"))
        assert len(out) == 1
        assert out[0]["revenue"] == 1000
        assert out[0]["operating_income"] == 200
        assert out[0]["fs_div"] == "CFS"

    def test_prefers_cfs_over_ofs(self):
        raw = pd.DataFrame([
            _row("A", "005930", "매출액", "999", fs_div="OFS"),
            _row("A", "005930", "매출액", "1,000", fs_div="CFS"),
        ])
        out = OpenDartClient._summarize(raw, ("CFS", "OFS"))
        assert out[0]["fs_div"] == "CFS"
        assert out[0]["revenue"] == 1000

    def test_falls_back_to_ofs(self):
        raw = pd.DataFrame([_row("A", "005930", "매출액", "500", fs_div="OFS")])
        out = OpenDartClient._summarize(raw, ("CFS", "OFS"))
        assert out[0]["fs_div"] == "OFS"
        assert out[0]["revenue"] == 500

    def test_financial_company_uses_operating_revenue(self):
        # 지주/금융사는 '매출액' 대신 '영업수익'
        raw = pd.DataFrame([
            _row("B", "105560", "영업수익", "3,000"),
            _row("B", "105560", "영업이익", "800"),
        ])
        out = OpenDartClient._summarize(raw, ("CFS", "OFS"))
        assert out[0]["revenue"] == 3000

    def test_missing_operating_income_is_none(self):
        raw = pd.DataFrame([_row("A", "005930", "매출액", "1,000")])
        out = OpenDartClient._summarize(raw, ("CFS", "OFS"))
        assert out[0]["operating_income"] is None

    def test_empty_returns_empty_list(self):
        assert OpenDartClient._summarize(pd.DataFrame(), ("CFS", "OFS")) == []


# ----------------------------------------------------------------------
# 초기화 / 검증
# ----------------------------------------------------------------------
class TestInit:
    def test_requires_key(self, monkeypatch):
        monkeypatch.delenv("OPENDART_API_KEY", raising=False)
        with pytest.raises(ValueError):
            OpenDartClient()

    def test_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENDART_API_KEY", "envkey")
        assert OpenDartClient().api_key == "envkey"

    def test_invalid_quarter_raises(self):
        client = OpenDartClient(api_key="k")
        with pytest.raises(ValueError):
            client.get_financials_by_stock(["005930"], year=2026, quarter=5)


# ----------------------------------------------------------------------
# get_corp_codes — HTTP monkeypatch (ZIP)
# ----------------------------------------------------------------------
class _FakeResp:
    def __init__(self, content=b"", payload=None):
        self.content = content
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class TestGetCorpCodes:
    def test_downloads_and_filters_listed(self, monkeypatch):
        client = OpenDartClient(api_key="k")
        monkeypatch.setattr(
            client._session, "get",
            lambda *a, **k: _FakeResp(content=_zip_of(CORP_XML)),
        )
        listed = client.get_corp_codes(listed_only=True)
        assert len(listed) == 2  # 비상장 1건 제외
        assert set(listed["stock_code"]) == {"005930", "000660"}

    def test_error_xml_raises(self, monkeypatch):
        client = OpenDartClient(api_key="k")
        monkeypatch.setattr(
            client._session, "get",
            lambda *a, **k: _FakeResp(content=b"<result><status>010</status></result>"),
        )
        with pytest.raises(RuntimeError):
            client.get_corp_codes()


# ----------------------------------------------------------------------
# get_financials_by_stock — end-to-end (monkeypatch 두 엔드포인트)
# ----------------------------------------------------------------------
class TestGetFinancialsByStock:
    def test_end_to_end(self, monkeypatch):
        client = OpenDartClient(api_key="k")

        multi_payload = {
            "status": "000", "message": "정상",
            "list": [
                _row("00126380", "005930", "매출액", "1,000,000"),
                _row("00126380", "005930", "영업이익", "100,000"),
                _row("00164779", "000660", "매출액", "500,000"),
                _row("00164779", "000660", "영업이익", "80,000"),
            ],
        }

        def fake_get(url, **kwargs):
            if url.endswith("corpCode.xml"):
                return _FakeResp(content=_zip_of(CORP_XML))
            return _FakeResp(payload=multi_payload)

        monkeypatch.setattr(client._session, "get", fake_get)

        df = client.get_financials_by_stock(["005930", "000660"], year=2026, quarter=1)
        assert len(df) == 2
        sec = df[df["stock_code"] == "005930"].iloc[0]
        assert sec["revenue"] == 1_000_000
        assert sec["operating_income"] == 100_000
        assert sec["reprt_code"] == "11013"

    def test_no_data_status_returns_empty(self, monkeypatch):
        client = OpenDartClient(api_key="k")

        def fake_get(url, **kwargs):
            if url.endswith("corpCode.xml"):
                return _FakeResp(content=_zip_of(CORP_XML))
            return _FakeResp(payload={"status": "013", "message": "데이터 없음"})

        monkeypatch.setattr(client._session, "get", fake_get)
        df = client.get_financials_by_stock(["005930"], year=2026, quarter=1)
        assert df.empty


def test_reprt_code_mapping():
    assert REPRT_CODE_BY_QUARTER == {1: "11013", 2: "11012", 3: "11014", 4: "11011"}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
