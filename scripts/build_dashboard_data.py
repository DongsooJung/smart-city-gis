#!/usr/bin/env python3
"""
OpenDART 대시보드용 data.json 생성

`fetch_opendart_top100.build_top_dataframe`로 실데이터를 조회해
`web/data.json`으로 저장한다. 이 파일이 존재하면 대시보드(web/index.html)는
내장 샘플 대신 실데이터를 렌더링한다.

사용 예:
    export OPENDART_API_KEY="발급받은_API_KEY"
    python scripts/build_dashboard_data.py --year 2026 --quarter 1 --top 100
    # 이후 web/ 을 Vercel에 재배포하면 실데이터 대시보드가 게시됨
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from smartcity_gis.api_clients import OpenDartClient  # noqa: E402
from fetch_opendart_top100 import DEFAULT_SEED, build_top_dataframe, load_seed  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("build_dashboard_data")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "web" / "data.json"


def to_rows(fin) -> list[dict]:
    """DataFrame → 대시보드가 소비하는 경량 dict 목록 (NaN → None)."""
    rows = []
    for _, r in fin.iterrows():
        oi = r["operating_income_eok"]
        margin = r["operating_margin_pct"]
        rows.append(
            {
                "rank": int(r["rank"]),
                "corp_name": str(r["corp_name"]),
                "stock_code": str(r["stock_code"]),
                "fs_div": str(r["fs_div"]),
                "revenue_eok": None if pd_isna(r["revenue_eok"]) else int(r["revenue_eok"]),
                "operating_income_eok": None if pd_isna(oi) else int(oi),
                "operating_margin_pct": None if pd_isna(margin) else float(margin),
            }
        )
    return rows


def pd_isna(v) -> bool:
    return v != v  # NaN != NaN


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--year", type=int, default=2026)
    p.add_argument("--quarter", type=int, default=1, choices=[1, 2, 3, 4])
    p.add_argument("--top", type=int, default=100)
    p.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    p.add_argument("--api-key", default=None)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    seed = load_seed(args.seed)
    client = OpenDartClient(api_key=args.api_key)

    fin = build_top_dataframe(client, seed, args.year, args.quarter, args.top)
    if fin.empty:
        logger.error("조회 결과 없음 — %d년 %d분기 보고서 미제출 가능성.", args.year, args.quarter)
        return 1

    rows = to_rows(fin)
    payload = {
        "meta": {
            "year": args.year,
            "quarter": args.quarter,
            "count": len(rows),
            "source": "OpenDART (금융감독원 전자공시)",
            "sample": False,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "unit": "억원",
        },
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("저장 완료: %s (%d개 기업)", args.out, len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
