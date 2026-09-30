# CLAUDE.md

## 프로젝트 개요
성신양회 단양공장 전력일보 대시보드. Crusher(QR)·R·Co·K·C 설비군 기준 일별 전력 데이터를 시각화하는
GitHub Pages 사이트(https://mr1kwg-wang1.github.io/daily-power-dashboard/).
월보용 `power-dashboard`(R/M·COM·K/L·C/M 4개 공정)는 별도 저장소.

## ⚠️ 지금 최우선 순위
**5R 7/26 데이터 오류(-997,415kWh) 미해결.** `total_usage_main4`/`total_cost` 등 전체 총계 정확도에 영향 →
원본 재추출 필요. 다른 기능 작업을 요청받으면 이 점을 가볍게 상기시켜줄 것.
(절감 시나리오 1·2는 공식 단가를 쓰므로 이 오류와 무관)

## 작업 시작 전 필수
- 여러 세션이 동시에 작업함 → `git fetch && git log --oneline HEAD..origin/main`으로 원격이 앞서 있는지
  먼저 확인. 앞서 있으면 pull 후 작업 (과거 25커밋 뒤처진 채 같은 기능을 중복 구현한 사고 있음)
- `git config core.autocrlf false` 유지 (GitHub Actions YAML 들여쓰기 오류 이력)

## 일일 갱신 워크플로우
전력일보 CSV를 받으면 **`daily-update` 스킬**(`.claude/skills/daily-update/SKILL.md`)대로 진행:
원격 확인 → `raw/YYYY-MM/`에 원본 보관 → `python parse_daily_report.py <csv>` → `python scripts/validate_daily_data.py`
→ 요약 보고 → **사용자 확인 후** commit & push.
- push 시 GitHub Actions가 "단양공장전력관리" 텔레그램 그룹에 자동 알림 발송(외부 발송이므로 반드시 확인 후 push)
  - `daily_data.json` 변경 → `telegram-notify.yml`(일보 수치 알림)
  - `index.html` 변경 → `telegram-dashboard-update-notify.yml`(대시보드 업데이트 알림, 커밋 메시지 포함)
- 회사 폐쇄망 SCADA라 자동 연동 불가 → CSV 수동 추출 후 반자동 갱신

## 자동 검증 (훅)
`.claude/settings.json`의 훅이 `scripts/validate_daily_data.py --hook`을 실행:
- `daily_data.json`을 수정하거나 파서를 실행한 직후 → 오류 시 Claude에게 피드백
- `daily_data.json`이 바뀐 상태에서 `git commit`/`git push` 직전 → 오류 시 **차단**
- 검사: JSON 형식, 필수 필드, 날짜 중복·정렬·요일, 설비군 합계 일치, 대형 음수 사용량(< -1,000kWh),
  커밋된 버전 대비 날짜 삭제·현장메모(note) 유실
- 알려진 이상치는 스크립트의 `KNOWN_ISSUES`에 등록(경고로만 표시). 5R 7/26이 정정되면 거기서 삭제할 것.
  3Co의 -47kWh 수준 소형 음수(7/13~27)는 대기전력 편차로 보고 경고만 표시.
- 검증 오류가 나면 데이터를 임의로 고치지 말고 사용자에게 보고.

## 핵심 파일과 데이터 구조
- `parse_daily_report.py`: 일보 CSV → `daily_data.json`. 파일명 날짜는 `YYYY.MM.DD`/`YYYY_MM_DD` 모두 허용,
  LF 줄바꿈으로 저장. 같은 날짜 재파싱 시 기존 `note` 보존. 여러 날짜는 날짜 오름차순으로 파싱(재가동유예 판정이
  직전 `RESTART_GRACE_DAYS`일 이력을 참조).
- `daily_data.json`: `days[]` 배열. 각 설비군 `groups.{QR,R,Co,K,C}`에
  - `원단위`, `목표_원단위`(설비별 목표를 생산량 가중평균), `설비.{이름}.보수상태`(null|"정비중"|"재가동유예")
  - `최대목표초과설비`(1개 또는 null), `목표초과설비목록`(초과한 모든 설비), 각각 `검토필요` bool
  - 최상위 `total_usage_main4`(R+Co+K+C), `total_usage_incl_crusher`/`total_target_usage_incl_crusher`(5개군)
  - 7월 초기 데이터 일부는 `보수상태`/`검토필요` 필드가 없음(해당 로직 도입 전 파싱분). 재파싱하면 채워지고 수치는 동일.
- `index.html`: 원단위·사용량·전력비용 추이, 변동 원인, 설비별 변동성, 만성 목표초과(최근 7일 3회 이상),
  Co/M 상세, 절감 예상 시나리오 1·2.
- `raw/YYYY-MM/`: 원본 CSV·월보·검증보고서 아카이브. `docs/작업이력.md`: 과거 수정 경위 원문.

## 두 곳을 함께 고쳐야 하는 것 (중복 정의)
- **목표초과 판정**: `index.html`의 gapCard는 json의 목표초과 필드를 쓰지 않고 설비별 원본 값으로 상위 5개를
  자체 재계산함 → 판정 로직(`gap_pct > 0`, `보수상태` 제외) 변경 시 파서와 gapCard 둘 다 수정.
- **`REVIEW_THRESHOLD_PCT`**(= 20%p, "검토필요" 기준): 파서와 index.html 양쪽에 정의.
- **`TOU_RATES`**: index.html의 시나리오 1 IIFE와 시나리오 2 IIFE에 각각 정의. 공통 상수화는 미결정.

## 계획보수 판정
- 파서의 `MAINTENANCE_SCHEDULE`(출처: `raw/2026-07/2026년 생산 및 출하 계획(안) (260709).pdf`) 기간 +
  `RESTART_GRACE_DAYS`(2일), 또는 최근 유예일 내 생산량 0 이력 후 재가동 → `보수상태` 표시, 목표초과 판정 제외.
- 새 계획보수 일정이 나오면 `MAINTENANCE_SCHEDULE`에 추가.

## 요금 단가 (절감 예상 시나리오)
- 산업용(을) 고압B 선택3, **2026-10-01 시행 단가**(원래 04-16 시행 예정이었으나 당사 유예신청으로 10-01 적용),
  기본요금 8,190원/kW 별도. 경부하/중간부하/최대부하(원/kWh):
  여름(6~8월) 125.9/173.1/237.5, 봄가을(3~5·9~10월) 125.9/143.2/160.3, 겨울(11~2월) 133.0/173.1/212.4
- 시나리오는 "이 요금으로 앞으로 이전하면 얼마나 절감되나"의 프로젝션 → 표시 데이터 날짜와 무관하게 항상 위 단가 사용
  (날짜별 요금 전환 로직 없음). `TOU_RATES_BEFORE/AFTER` 이원화는 잘못된 전제였으므로 되살리지 말 것.
- `WEEKEND_MIDDAY_DISCOUNT`: 봄·가을철 토·일·공휴일 11~14시 50% 할인, 봄가을철이면 항상 적용.
- 시나리오 1: 최근 평일 경/중/최대 비중 × 단가로 계산 평균단가 산출, 슬라이더만큼 최대부하 → 중간부하 이전 가정(보수적).
- 시나리오 2: 공식 단가 직접 사용(과거 다중회귀 역산 방식은 폐지).
- 미반영: 시간대 구분 변경(3~10월 11~12·13~15시 최대→중간, 18~21시 중간→최대) — 일 단위 평균만 다뤄 시간대 배분 로직 없음.
- `raw/2026-07/절감예상시나리오_검토보고서.docx` 등 기존 문서의 시나리오 설명은 옛 회귀분석 기준이라 현재 로직과 다름.
- 전력월보 "합성계량" 시트 역산 근사치(120.8/173.1/254.4)와 공식 단가의 경부하·최대부하 차이는 원인 미상.

## 텔레그램 알림 형식 (`telegram-notify.yml`)
- Crusher 포함 5개군 원단위를 **목표대비 %**로 표시(전일대비 아님), 상승 🔺 / 하락 ▼
- 그룹 명칭은 index.html `GROUP_LABELS`와 통일: Crusher(원료수급), R/M, K/L, Co/M, C/M
- "전력원단위" 줄 = 5개군 원단위 단순 합(생산 기준이 달라 물리적으로 엄밀하지 않음, 요청에 따른 것)
- "합계(Crusher+R+K+Co+C)" 사용량은 목표대비, 전력비용은 값만(목표 개념 없음)
- 빈 줄은 의도된 구분자 → `lines`에서 빈 문자열을 필터링하지 말 것. 메시지 끝에 빈 줄 1개.

## 표시 원칙
- 원단위 기준(Part/Cement 등)은 설비군별 자체 기준 그대로 → 그룹 간 절대값 비교는 부정확, 추세만 참고.
- 텔레그램은 이상 여부와 무관하게 매 갱신마다 발송.
