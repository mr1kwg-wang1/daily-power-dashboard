# 단양공장 전력일보 대시보드 (초안)

전력월보 대시보드(`power-dashboard`)와는 완전히 별개의 프로젝트입니다.
- 월보 대시보드: 월 단위, 4대 공정 합산 트렌드/요금 분석용
- 일보 대시보드(이 저장소): **일 단위**, 설비군(R·Co·K·C)별 이상감지/모니터링용

## 구성
- `index.html` — GitHub Pages로 열리는 대시보드 화면
- `daily_data.json` — 일별 누적 데이터
- `parse_daily_report.py` — 전력일보 CSV → daily_data.json 변환 스크립트
- `.github/workflows/telegram-notify.yml` — daily_data.json 갱신 시 텔레그램 자동 알림

## 최초 설정 (1회만)
1. GitHub 새 저장소 생성 (예: `daily-power-dashboard`)
2. 이 파일들 전부 업로드 (`.github/workflows/telegram-notify.yml` 은 경로 그대로 생성)
3. Settings → Pages → Source: `main` 브랜치, `/(root)` 로 설정 → Pages 활성화
4. Settings → Secrets and variables → Actions 에서 아래 2개 등록:
   - `TELEGRAM_BOT_TOKEN` (기존 power-dashboard와 같은 값 사용 가능)
   - `TELEGRAM_CHAT_ID` (원하는 채팅방 ID — 그룹으로 보내려면 그룹 Chat ID)

## 매일 할 일 (약 1~2분)
1. 그날 `전력일보_YYYY_MM_DD.csv` 확보
2. Claude에게 전달 + "daily_data.json 갱신해줘" 요청
3. 받은 daily_data.json을 GitHub의 daily_data.json 파일에 붙여넣고 Commit
4. 자동 반영: 대시보드 갱신 + 텔레그램 알림 발송 (매번)

## 설계 원칙 (토의 결과 반영)
- 설비는 우선 4개 그룹(R/Co/K/C)으로 집계 — 개별 설비(1R~8R 등)는 세부 데이터로만 보관, 화면엔 그룹 단위로 표시
- 원단위 기준(Part/Cement 등 생산량 기준 차이)은 보정하지 않고 각 설비군 자체 기준 그대로 표시 — 화면에 안내 문구로 명시
- 텔레그램은 매 갱신마다 알림 발송 (이상 감지 시에만 보내는 방식 아님)
- 실무자 수기 메모 필드(`note`) 지원 — 월보 대시보드와 동일한 방식

## 한계
- 개별 설비(41개) 단위 세부 분석은 이번 버전엔 화면에 없음 (추후 필요시 확장 가능)
- 원단위 기준 차이로 인해 그룹 간 절대값 비교는 부정확 — 방향성(추세)만 참고
