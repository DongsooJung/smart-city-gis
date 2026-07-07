#!/usr/bin/env python3
"""
OpenDART 상위 100개 상장기업 매출액·영업이익 수집

시가총액 대형주 시드 목록(data/kospi_top100.csv)에 대해 OpenDART OpenAPI로
지정 연도·분기의 매출액과 영업이익을 조회하고, 매출액 기준으로 상위 N개를
정렬해 출력·저장한다.

사용 예:
    export OPENDART_API_KEY="발급받은_API_KEY"
    python scripts/fetch_opendart_top100.py --year 2026 --quarter 1

    # 또는 키를 인자로 직접 전달
    python scripts/fetch_opendart_top100.py --year 2026 --quarter 1 \
        --api-key 878cc74d... --top 100

주의:
    - 분기보고서(1분기=11013)는 분기 종료 후 약 45일 뒤 제출된다.
      2026년 1분기 데이터는 2026년 5월 중순 이후 조회 가능.
    - 손익계산서 계정은 분기 누적(3·6·9개월) 금액이다.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# src 레이아웃 대응 (설치 없이 실행 가능하도록)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from smartcity_gis.api_clients import OpenDartClient  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("opendart_top100")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEED = REPO_ROOT / "data" / "kospi_top100.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "processed"

EOK = 100_000_000  # 1억 (원 → 억원 환산)


def load_seed(path: Path) -> pd.DataFrame:
    """시드 CSV 로드 (주석 '#' 행 무시, 종목코드 6자리 zero-pad)."""
    df = pd.read_csv(path, dtype=str, comment="#")
    df["stock_code"] = df["stock_code"].str.strip().str.zfill(6)
    df["corp_name"] = df["corp_name"].str.strip()
    return df


def build_top_dataframe(client, seed, year: int, quarter: int, top: int) -> pd.DataFrame:
    """시드 종목 → 매출액 기준 상위 N개 재무 요약 DataFrame(순위·억원 파생 포함).

    OpenDartClient를 통해 조회하며, CLI와 대시보드 데이터 생성기가 함께 사용한다.
    조회 결과가 없으면 빈 DataFrame을 반환한다.
    """
    fin = client.get_financials_by_stock(
        seed["stock_code"].tolist(), year=year, quarter=quarter
    )
    if fin.empty:
        return fin

    # 표시용 기업명은 시드(큐레이션한 한글명) 우선, 없으면 API 응답값 사용
    seed_names = seed.set_index("stock_code")["corp_name"]
    curated = fin["stock_code"].map(seed_names).fillna("").str.strip()
    fin["corp_name"] = curated.where(curated != "", fin["corp_name"])

    fin = fin[fin["revenue"].notna()].copy()
    fin = fin.sort_values("revenue", ascending=False, na_position="last")
    fin = fin.head(top).reset_index(drop=True)
    fin.insert(0, "rank", fin.index + 1)

    # 억원 단위 파생 컬럼
    fin["revenue_eok"] = (fin["revenue"] / EOK).round(0)
    fin["operating_income_eok"] = (fin["operating_income"] / EOK).round(0)
    fin["operating_margin_pct"] = (
        fin["operating_income"] / fin["revenue"] * 100
    ).round(1)
    return fin


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--year", type=int, default=2026, help="사업연도 (기본 2026)")
    p.add_argument("--quarter", type=int, default=1, choices=[1, 2, 3, 4], help="분기 (기본 1)")
    p.add_argument("--top", type=int, default=100, help="상위 N개 (기본 100)")
    p.add_argument("--seed", type=Path, default=DEFAULT_SEED, help="시드 종목 목록 CSV")
    p.add_argument("--api-key", default=None, help="OpenDART API Key (미지정 시 OPENDART_API_KEY 환경변수)")
    p.add_argument("--out", type=Path, default=None, help="결과 CSV 경로")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    seed = load_seed(args.seed)
    logger.info("시드 기업 %d개 로드: %s", len(seed), args.seed)

    client = OpenDartClient(api_key=args.api_key)
    fin = build_top_dataframe(client, seed, args.year, args.quarter, args.top)
    if fin.empty:
        logger.error(
            "조회 결과가 없습니다. %d년 %d분기 보고서가 아직 제출되지 않았을 수 있습니다.",
            args.year, args.quarter,
        )
        return 1

    # 콘솔 출력
    _print_table(fin, args.year, args.quarter)

    # 저장
    out = args.out or (DEFAULT_OUT_DIR / f"opendart_top{args.top}_{args.year}q{args.quarter}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "rank", "corp_name", "stock_code", "corp_code", "fs_div",
        "revenue", "operating_income", "revenue_eok",
        "operating_income_eok", "operating_margin_pct",
        "reprt_code", "bsns_year",
    ]
    fin[cols].to_csv(out, index=False, encoding="utf-8-sig")
    logger.info("저장 완료: %s (%d개 기업)", out, len(fin))
    return 0


def _print_table(fin: pd.DataFrame, year: int, quarter: int) -> None:
    print(f"\n=== OpenDART {year}년 {quarter}분기 · 매출액 상위 {len(fin)}개 기업 (단위: 억원) ===")
    print(f"{'순위':>4} {'기업명':<18} {'종목코드':<8} {'매출액':>14} {'영업이익':>14} {'영업이익률':>8}")
    print("-" * 74)
    for _, r in fin.iterrows():
        oi = "N/A" if pd.isna(r["operating_income_eok"]) else f"{r['operating_income_eok']:>14,.0f}"
        margin = "N/A" if pd.isna(r["operating_margin_pct"]) else f"{r['operating_margin_pct']:>7.1f}%"
        print(
            f"{int(r['rank']):>4} {str(r['corp_name'])[:18]:<18} {r['stock_code']:<8} "
            f"{r['revenue_eok']:>14,.0f} {oi} {margin}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
