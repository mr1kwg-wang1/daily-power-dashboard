"""
daily_data.json 무결성 검증 스크립트
사용법:
  python scripts/validate_daily_data.py          # 직접 실행 (오류 있으면 종료코드 1)
  python scripts/validate_daily_data.py --hook   # Claude Code 훅에서 호출 (stdin으로 훅 입력 JSON 수신)

검사 항목
  [오류] JSON 형식, 필수 필드, 날짜 중복/형식, 요일 불일치, 설비군 누락,
        설비군 합계 ≠ 설비 합계, total_usage_main4/total_usage_incl_crusher 합계 불일치,
        대형 음수 사용량(NEG_ERROR_KWH 미만, KNOWN_ISSUES 제외),
        커밋된 버전(HEAD) 대비 날짜 삭제 또는 현장메모(note) 유실/변경
  [경고] 소형 음수 사용량, KNOWN_ISSUES에 등록된 기존 미해결 이상치
"""
import sys, json, datetime, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "daily_data.json"

REQUIRED_DAY_KEYS = ["date", "weekday", "groups", "total_usage_main4", "total_cost"]
REQUIRED_GROUPS = ["QR", "R", "Co", "K", "C"]
MAIN4 = ["R", "Co", "K", "C"]
NEG_ERROR_KWH = -1000  # 이보다 작은 음수 사용량은 추출 오류로 간주 (3Co 대기전력 -47kWh 수준은 경고만)

# 이미 알고 있는 미해결 이상치 — 원본 재추출로 정정되면 여기서 삭제할 것
KNOWN_ISSUES = {
    ("2026-07-26", "5R"): "5R 사용량 -997,415kWh (원본 재추출 필요, CLAUDE.md 최우선 순위)",
}
WEEKDAYS = "월화수목금토일"


def load_head_version():
    try:
        out = subprocess.run(["git", "show", "HEAD:daily_data.json"], cwd=ROOT,
                             capture_output=True, check=True)
        return json.loads(out.stdout.decode("utf-8"))
    except Exception:
        return None


def validate(data, head=None):
    errors, warnings = [], []
    days = data.get("days") if isinstance(data, dict) else None
    if not isinstance(days, list):
        return ["최상위에 days 배열이 없습니다"], warnings

    seen = set()
    prev = ""
    small_neg = {}
    for i, day in enumerate(days):
        date = day.get("date", f"#{i}")
        missing = [k for k in REQUIRED_DAY_KEYS if k not in day]
        if missing:
            errors.append(f"{date}: 필수 필드 누락 {missing}")
            continue
        try:
            wd = WEEKDAYS[datetime.date.fromisoformat(date).weekday()]
        except ValueError:
            errors.append(f"{date}: 날짜 형식 오류 (YYYY-MM-DD 이어야 함)")
            continue
        if date in seen:
            errors.append(f"{date}: 날짜 중복")
        seen.add(date)
        if date < prev:
            errors.append(f"{date}: 날짜 정렬 순서 오류 (앞 날짜 {prev})")
        prev = date
        if day["weekday"] != wd:
            errors.append(f"{date}: 요일 불일치 (기록 {day['weekday']}, 실제 {wd})")

        groups = day["groups"]
        for g in REQUIRED_GROUPS:
            if g not in groups:
                errors.append(f"{date}: 설비군 {g} 누락")
        for g, gv in groups.items():
            equips = gv.get("설비", {})
            tol = max(len(equips), 1)  # 설비별 반올림 오차 허용
            for field in ("사용량", "생산량"):
                s = sum(e.get(field, 0) or 0 for e in equips.values())
                if equips and abs(s - (gv.get(field) or 0)) > tol:
                    errors.append(f"{date} {g}: {field} 합계 불일치 (설비 합 {s:,.0f} ≠ 설비군 {gv.get(field):,.0f})")
            for name, e in equips.items():
                u = e.get("사용량") or 0
                if u >= 0:
                    continue
                if (date, name) in KNOWN_ISSUES:
                    warnings.append(f"{date} {name}: [기존 미해결] {KNOWN_ISSUES[(date, name)]}")
                elif u < NEG_ERROR_KWH:
                    errors.append(f"{date} {name}: 사용량 {u:,.0f}kWh — 대형 음수, 원본 추출 오류 의심")
                else:
                    small_neg.setdefault(name, []).append(date)

        if all(g in groups for g in MAIN4):
            m4 = sum(groups[g].get("사용량") or 0 for g in MAIN4)
            if abs(m4 - day["total_usage_main4"]) > 2:
                errors.append(f"{date}: total_usage_main4 {day['total_usage_main4']:,.0f} ≠ R+Co+K+C {m4:,.0f}")
            if "total_usage_incl_crusher" in day and "QR" in groups:
                t = m4 + (groups["QR"].get("사용량") or 0)
                if abs(t - day["total_usage_incl_crusher"]) > 2:
                    errors.append(f"{date}: total_usage_incl_crusher {day['total_usage_incl_crusher']:,.0f} ≠ 5개군 합 {t:,.0f}")

    for name, dates in small_neg.items():
        warnings.append(f"{name}: 소형 음수 사용량 {len(dates)}일 ({dates[0]}~{dates[-1]}) — 대기전력 계측 편차로 추정")

    if head and isinstance(head.get("days"), list):
        cur = {d.get("date"): d for d in days}
        for hd in head["days"]:
            hdate = hd.get("date")
            if hdate not in cur:
                errors.append(f"{hdate}: 커밋된 버전에 있던 날짜가 삭제됨")
            elif hd.get("note") and cur[hdate].get("note") != hd["note"]:
                errors.append(f"{hdate}: 현장메모(note)가 유실/변경됨 — 의도한 수정이 아니면 복원할 것")

    return errors, warnings


def run():
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"JSON 형식 오류: {e}"], []
    return validate(data, load_head_version())


def hook_is_relevant(payload):
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input", {}) or {}
    if tool in ("Write", "Edit", "MultiEdit"):
        return str(inp.get("file_path", "")).replace("\\", "/").endswith("daily_data.json")
    if tool in ("Bash", "PowerShell"):
        cmd = inp.get("command", "")
        if payload.get("hook_event_name") == "PreToolUse":
            # 커밋/푸시 직전에는 daily_data.json이 바뀐 경우에만 검사
            if "git commit" not in cmd and "git push" not in cmd:
                return False
            diff = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "daily_data.json"], cwd=ROOT)
            ahead = subprocess.run(["git", "diff", "--quiet", "@{u}", "HEAD", "--", "daily_data.json"],
                                   cwd=ROOT, capture_output=True)
            return diff.returncode != 0 or ahead.returncode == 1
        return "parse_daily_report" in cmd or "daily_data.json" in cmd
    return False


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    if "--hook" in sys.argv:
        try:
            payload = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
        except Exception:
            payload = {}
        if not hook_is_relevant(payload):
            sys.exit(0)
        errors, _ = run()
        if errors:
            print("daily_data.json 검증 실패 — 아래 오류를 해결한 뒤 진행하세요:", file=sys.stderr)
            for e in errors:
                print(f"  ✗ {e}", file=sys.stderr)
            sys.exit(2)  # 종료코드 2: Claude에게 오류 내용을 전달(PreToolUse면 실행 차단)
        sys.exit(0)

    errors, warnings = run()
    for w in warnings:
        print(f"  ⚠ {w}")
    for e in errors:
        print(f"  ✗ {e}")
    if errors:
        print(f"[실패] 오류 {len(errors)}건, 경고 {len(warnings)}건")
        sys.exit(1)
    print(f"[OK] daily_data.json 검증 통과 (경고 {len(warnings)}건)")


if __name__ == "__main__":
    main()
