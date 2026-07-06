# Data Directory

Sources: MOLIT, KOSIS, NSDI, V-World API, Kakao Local API, OpenDART API

## Files

| File | Description |
|------|-------------|
| `kospi_top100.csv` | 시가총액 상위권 KOSPI 상장기업 시드 목록 (종목코드·기업명). OpenDART 재무 수집용. |

## Subdirectories

- `raw/` — 원본 다운로드 (gitignore)
- `interim/` — 중간 처리 결과 (gitignore)
- `processed/` — 분석용 최종 데이터 (gitignore)
  - `opendart_topN_{year}q{q}.csv` — `scripts/fetch_opendart_top100.py` 출력

## OpenDART 재무 데이터

상장기업 매출액·영업이익 수집:

```bash
export OPENDART_API_KEY="발급받은_API_KEY"   # https://opendart.fss.or.kr
python scripts/fetch_opendart_top100.py --year 2026 --quarter 1 --top 100
```

- 분기보고서는 분기 종료 후 약 45일 뒤 제출된다 (1분기 → 5월 중순 이후 조회 가능).
- 연결재무제표(CFS)를 우선 사용하고 없으면 개별재무제표(OFS)로 대체한다.
- 손익계산서 계정은 분기 누적(3·6·9개월) 금액이다.
