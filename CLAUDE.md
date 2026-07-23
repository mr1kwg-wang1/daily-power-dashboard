# CLAUDE.md

## 프로젝트 개요
성신양회 단양공장 전력일보 대시보드. R·Co·K·C 4개 설비군 기준
일별 전력 데이터를 시각화하는 GitHub Pages 사이트.

## 핵심 파일
- parse_daily_report.py: 일보 CSV/엑셀을 파싱해 daily_data.json 생성
- daily_data.json: 파싱 결과, 이 파일이 갱신되면 index.html이 자동으로 반영.
  각 설비군(groups.{QR,R,Co,K,C})에는 `최대목표초과설비`(그 날 목표를 가장 크게 초과한 설비 1개, 없으면 null)와
  `목표초과설비목록`(그 날 실제로 목표를 초과한 모든 설비 목록)이 포함됨. 일자별 `note` 필드에 실무자 현장메모 기록 가능
  (같은 날짜로 재파싱해도 기존 note는 보존됨).
- index.html: 원단위·사용량·전력비용 추이, 변동 원인 분석, 설비별 변동성 상위,
  만성 목표초과 설비(최근 7일 3회 이상), 콜밀(Co/M) 상세 분석 등을 시각화하는 대시보드
- .github/workflows/telegram-notify.yml: daily_data.json push 시
  @wanggi_dashboard_bot이 "단양공장전력관리" 텔레그램 그룹으로 알림 발송

## 워크플로우
1. 원본 CSV/엑셀 업로드
2. parse_daily_report.py로 파싱 → daily_data.json 갱신
3. commit & push → GitHub Actions가 대시보드 갱신 + 텔레그램 알림 자동 발송

## 관련 저장소
- power-dashboard (월보용, 별도 저장소): R/M·COM·K/L·C/M 4개 공정 기준

## 주의사항
- 회사 폐쇄망 SCADA 환경이라 자동 연동 불가 → 수동 반자동 업데이트
- GitHub Actions YAML 들여쓰기 오류 이력 있음 → git config core.autocrlf false 확인
- (2026-07-23 수정) parse_daily_report.py의 최대목표초과설비 계산 로직에 버그 있었음:
  목표 대비 실적 gap_pct가 가장 큰 설비 1개를 조건 없이 뽑다 보니, 그룹 내 유일 가동 설비가
  목표 미달인데도 "초과설비"로 오분류되고(예: 6K, 7R), 동시에 그룹 내 여러 설비가 함께 초과한 날은
  1위가 아닌 설비의 초과 이력이 누락되는(과소 집계, 예: 7C) 문제가 있었음.
  gap_pct > 0 필터를 추가하고 그룹의 모든 초과 설비를 담는 목표초과설비목록 필드를 신설해 수정함.
  기존 daily_data.json 20일치도 이 로직으로 재계산해 반영함(커밋 3de7f5b).
