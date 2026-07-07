# OpenDART 대시보드 (web/)

상장기업 상위 100개의 **매출액·영업이익**을 시각화하는 자체완결 정적 대시보드.

## 파일

| 파일 | 설명 |
|------|------|
| `index.html` | 대시보드 (KPI · 상위 15개 그룹 막대 · 전체 순위표, 라이트/다크). 자체완결. |
| `data.json` | (선택) 실데이터. 있으면 자동 우선 사용, 없으면 내장 샘플로 폴백. |

## 실데이터 넣기

OpenDART API 접근이 가능한 환경에서:

```bash
export OPENDART_API_KEY="발급받은_API_KEY"   # https://opendart.fss.or.kr
python scripts/build_dashboard_data.py --year 2026 --quarter 1 --top 100
# → web/data.json 생성. index.html이 자동으로 이 파일을 읽어 실측 렌더링(샘플 배너 사라짐).
```

> `index.html`은 로드 시 `./data.json`을 우선 조회하고, 없거나 실패하면 내장 샘플로 폴백한다.
> 따라서 `data.json`만 채우면 코드 수정 없이 실데이터로 바뀐다.

## 로컬 미리보기

```bash
python -m http.server -d web 8000   # http://localhost:8000
```

`file://`로 바로 열면 브라우저 CORS로 `data.json` fetch가 막혀 항상 샘플이 뜨므로,
실데이터 확인은 위처럼 HTTP 서버로 열 것.

## 배포 (Vercel)

저장소 루트 `vercel.json`이 `web/`를 정적 서빙하도록 설정돼 있다.

- **Git 연동**: Vercel에서 저장소 Import → 푸시 시 자동 배포
- **CLI**: `npx vercel deploy`  (프로덕션: `--prod`)

## 주의

- 분기보고서는 분기 종료 후 약 45일 뒤 제출된다(1분기 → 5월 중순 이후 조회 가능).
- 손익계산서 계정은 분기 누적(3·6·9개월) 금액이다.
- 표시 수치는 `data.json`이 없으면 **샘플(비실측)**이며, 상단 배너로 명시된다.
