# OpenDART 기업 재무 수집

금융감독원 전자공시시스템(OpenDART) API 로 상장기업의 **분기 매출액·영업이익**을
수집한다. 기본 시나리오는 **2026년 1분기 상위 100개 기업**이다.

## 준비

1. OpenDART 인증키 발급: https://opendart.fss.or.kr → 오픈API → 인증키 신청
2. 환경변수 또는 CLI 인자로 키 전달

```bash
export OPENDART_API_KEY="발급받은_키"
pip install -r requirements.txt
```

## 실행 (CLI)

```bash
# 2026년 1분기 상위 100개 기업 매출액·영업이익 → CSV
python -m smartcity_gis.opendart \
    --year 2026 --quarter 1 \
    --out data/processed/opendart_q1_2026.csv
```

옵션:

| 인자 | 기본값 | 설명 |
|------|--------|------|
| `--year` | `2026` | 사업연도 |
| `--quarter` | `1` | 분기 (1=11013, 2=11012 반기, 3=11014, 4=11011 사업보고서) |
| `--key` | `$OPENDART_API_KEY` | 인증키 |
| `--seed` | `data/kospi_top100.csv` | 대상 종목 목록 (name, stock_code) |
| `--limit` | `100` | 상위 N개 |
| `--out` | `data/processed/opendart_q1_2026.csv` | 결과 CSV 경로 |

## 실행 (파이썬)

```python
from smartcity_gis.opendart import OpenDartClient, collect_financials

client = OpenDartClient()                      # OPENDART_API_KEY 사용
df = collect_financials(client, year=2026, quarter=1)

df[["corp_name", "revenue", "operating_profit", "operating_margin"]].head(10)
```

## 출력 컬럼

| 컬럼 | 설명 |
|------|------|
| `corp_name` | 회사명 (corpCode.xml 기준 권위 있는 이름) |
| `stock_code` | 종목코드 (6자리) |
| `corp_code` | OpenDART 고유번호 (8자리) |
| `revenue` | 매출액 (원) — 해당 분기 |
| `operating_profit` | 영업이익 (원) — 음수 가능 |
| `operating_margin` | 영업이익률 (%) = 영업이익 / 매출액 × 100 |
| `fs_div` | 재무제표 구분: `CFS`(연결) 우선, 없으면 `OFS`(별도) |
| `rcept_no` | 공시 접수번호 |

결과는 매출액 내림차순으로 정렬된다.

## 동작 방식

1. `corpCode.xml`(전체 공시대상 회사) 다운로드 → 종목코드 ↔ `corp_code` 매핑.
   매칭되지 않는 종목코드는 경고 후 건너뛴다 (오데이터 방지).
2. 각 회사에 대해 `fnlttSinglAcnt.json`(단일회사 주요계정) 호출.
   연결(CFS) 재무제표를 우선하고, 없으면 별도(OFS)로 폴백.
3. 손익계산서(IS/CIS) 행에서 `매출액`(또는 `수익(매출액)`, `영업수익`)과
   `영업이익` 계정의 당기금액을 추출.

## "상위 100개" 목록에 관하여

OpenDART API 는 **시가총액 랭킹을 제공하지 않는다.** 따라서 대상 기업 목록은
외부 랭킹에서 주입해야 한다. `data/kospi_top100.csv` 는 대표 대형주를 모아 둔
**편집 가능한 시드**이며, 최신 시가총액 상위 100개로 교체해 사용하면 된다.
(예: KRX 시장정보 또는 증권사 데이터로 `name,stock_code` 갱신)

## 네트워크 주의

`opendart.fss.or.kr` 로의 아웃바운드가 허용된 환경에서 실행해야 한다.
일부 관리형/원격 실행 환경은 이그레스 정책상 이 호스트를 차단할 수 있다.
