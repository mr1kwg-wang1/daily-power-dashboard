# CLAUDE.md

## 프로젝트 개요
성신양회 단양공장 전력일보 대시보드. R·Co·K·C 4개 설비군 기준
일별 전력 데이터를 시각화하는 GitHub Pages 사이트.

## 핵심 파일
- parse_daily_report.py: 일보 CSV/엑셀을 파싱해 daily_data.json 생성
- daily_data.json: 파싱 결과, 이 파일이 갱신되면 index.html이 자동으로 반영
- index.html: 원단위·사용량·전력비용 추이 시각화 대시보드
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
