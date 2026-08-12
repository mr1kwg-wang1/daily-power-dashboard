"""
성신양회 단양공장 전력일보 자동 파싱 스크립트
사용법: python parse_daily_report.py <전력일보_YYYY_MM_DD.csv>
같은 폴더의 daily_data.json 에 해당 일자 데이터를 추가/갱신한다.
"""
import sys, csv, re, json, datetime
from pathlib import Path

COLS = {
    "설비": 0, "생산량": 1, "사용량": 2,
    "원단위_목표_part": 3, "원단위_실적_part": 4,
    "원단위_목표_cem": 5, "원단위_실적_cem": 6,
    "비용_경부하": 7, "비용_중간부하": 8, "비용_최대부하": 9,
    "비용_사용요금계": 10, "비용_기본요금": 11, "비용_기타": 12, "비용_합계": 13,
    "원가_사용요금": 14, "원가_기본요금": 15, "원가_합계": 16,
}

GROUPS = {
    "QR": {"label": "Q/R (원료수급)", "members": ["기존 Q/R", "신설 Q/R"]},
    "R":  {"label": "R (원료분쇄)",   "members": ["1R","2R","3R","4R","5R","6R","7R","8R"]},
    "Co": {"label": "Co (석탄분쇄)",  "members": ["1Co","2Co","3Co","4Co","5Co","6Co"]},
    "K":  {"label": "K (소성)",       "members": ["1K","2K","3K","5K","6K"]},
    "C":  {"label": "C (시멘트분쇄)", "members": ["1C","2C","3C","4C","5C","6C","7C","8C","9C","10C","11C","12C","13C"]},
}
EXTRA_ITEMS = ["출하", "기타", "폐열", "판매사업"]

# 계획보수 일정 (출처: 2026년 생산 및 출하 계획(안) (260709).pdf)
# 이 기간 + 재가동 후 유예일수 동안은 목표초과설비 판정에서 제외하고 "보수상태" 배지만 표시한다.
MAINTENANCE_SCHEDULE = [
    {"설비": "5K", "시작": "2026-06-15", "종료": "2026-07-26", "메모": "5K 하계보수(계획보수 및 가동대기)"},
    {"설비": "3K", "시작": "2026-07-13", "종료": "2026-07-22", "메모": "3K 계획보수"},
    {"설비": "6K", "시작": "2026-07-28", "종료": "2026-09-04", "메모": "6K 하계보수"},
]
RESTART_GRACE_DAYS = 2  # 재가동/정지 직후 원단위가 안정화되기까지의 유예일수
REVIEW_THRESHOLD_PCT = 20  # 목표대비율이 이 값(%) 이상이면 "검토필요" 표시

def maintenance_status(equip, date_str, today_prod, recent_prod):
    """설비의 보수상태를 판정한다.
    1) 계획보수 일정표(MAINTENANCE_SCHEDULE)에 포함된 기간(+재가동 유예일)이면 우선 적용.
    2) 계획에 없더라도, 오늘 생산량이 있으면서 최근 RESTART_GRACE_DAYS일 내에는 생산량이 0이었던 경우
       (계획보다 실제 정지가 길어져 막 재가동한 경우를 대비한 동적 감지). 원래부터 계속 생산량이
       0인 유휴설비(예: 1K, 2K)는 "재가동"이 아니므로 today_prod > 0 조건으로 제외한다.
    """
    for sched in MAINTENANCE_SCHEDULE:
        if sched["설비"] != equip:
            continue
        start, end = sched["시작"], sched["종료"]
        if start <= date_str <= end:
            return "정비중"
        grace_end = (datetime.date.fromisoformat(end) + datetime.timedelta(days=RESTART_GRACE_DAYS)).isoformat()
        if end < date_str <= grace_end:
            return "재가동유예"
    if today_prod > 0 and recent_prod and any(v == 0 for v in recent_prod):
        return "재가동유예"
    return None

def to_float(s):
    s = (s or "").strip()
    if s in ("", "-"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0

def parse_file(path: Path, prior_days=None):
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    m = re.search(r"(\d{4})_(\d{2})_(\d{2})", path.stem)
    if not m:
        raise ValueError(f"파일명에서 날짜를 찾을 수 없습니다: {path.name}")
    date_str = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    weekday_kr = ["월","화","수","목","금","토","일"][datetime.date.fromisoformat(date_str).weekday()]

    # 재가동 유예 판정용: 이 날짜 이전 RESTART_GRACE_DAYS일간의 설비별 생산량 이력
    prior_days = sorted([d for d in (prior_days or []) if d["date"] < date_str], key=lambda d: d["date"])
    recent_prior = prior_days[-RESTART_GRACE_DAYS:] if RESTART_GRACE_DAYS else []
    def recent_prod_history(equip_name, group_key):
        vals = []
        for d in recent_prior:
            e = d.get("groups", {}).get(group_key, {}).get("설비", {}).get(equip_name)
            if e is not None:
                vals.append(e.get("생산량", 0))
        return vals

    equip = {}
    for r in rows[4:]:
        if not r or not r[0].strip():
            continue
        name = r[0].strip()
        if name == "합계":
            continue
        vals = {k: to_float(r[idx]) if idx < len(r) else 0.0 for k, idx in COLS.items() if k != "설비"}
        equip[name] = vals

    groups_out = {}
    target_usage_all = 0.0  # Crusher(QR) 포함 전체 목표사용량 (목표대비 비교용, 텔레그램 알림 등에서 사용)
    for gkey, ginfo in GROUPS.items():
        members = ginfo["members"]
        prod = sum(equip.get(m, {}).get("생산량", 0) for m in members)
        usage = sum(equip.get(m, {}).get("사용량", 0) for m in members)
        cost = sum(equip.get(m, {}).get("비용_합계", 0) for m in members)
        target_usage_g = sum(equip.get(m, {}).get("생산량", 0) * equip.get(m, {}).get("원단위_목표_part", 0) for m in members)
        target_usage_all += target_usage_g

        equip_detail = {}
        gap_candidates = []
        for m in members:
            if m not in equip:
                continue
            e = equip[m]
            상태 = maintenance_status(m, date_str, e.get("생산량", 0), recent_prod_history(m, gkey))
            entry = {
                "사용량": round(e.get("사용량", 0), 0),
                "생산량": round(e.get("생산량", 0), 0),
                "목표_원단위": round(e.get("원단위_목표_part", 0), 2) if e.get("원단위_목표_part") else None,
                "실적_원단위": round(e.get("원단위_실적_part", 0), 2) if e.get("생산량", 0) > 0 else None,
                "보수상태": 상태,
            }
            equip_detail[m] = entry
            # 보수중/재가동유예 설비는 원단위가 예열·권상 부하로 왜곡되므로 목표초과 판정에서 제외
            if 상태 is None and entry["목표_원단위"] and entry["실적_원단위"] and entry["생산량"] > 0:
                gap = entry["실적_원단위"] - entry["목표_원단위"]
                gap_pct = gap / entry["목표_원단위"] * 100
                gap_candidates.append((m, gap, gap_pct))

        gap_candidates.sort(key=lambda x: -x[2])
        # 목표를 실제로 초과한 설비만 후보로 남긴다 (미달 설비를 초과로 오분류하는 버그 수정)
        over_candidates = [c for c in gap_candidates if c[2] > 0]

        groups_out[gkey] = {
            "label": ginfo["label"],
            "생산량": round(prod, 0),
            "사용량": round(usage, 0),
            "원단위": round(usage / prod, 2) if prod else None,
            "목표_원단위": round(target_usage_g / prod, 2) if prod else None,
            "전력비용": round(cost, 0),
            "설비": equip_detail,
            "최대목표초과설비": {"설비": over_candidates[0][0], "목표대비차이": round(over_candidates[0][1],2), "목표대비율": round(over_candidates[0][2],1), "검토필요": over_candidates[0][2] >= REVIEW_THRESHOLD_PCT} if over_candidates else None,
            "목표초과설비목록": [{"설비": c[0], "목표대비차이": round(c[1],2), "목표대비율": round(c[2],1), "검토필요": c[2] >= REVIEW_THRESHOLD_PCT} for c in over_candidates],
        }

    extra = {name: round(equip.get(name, {}).get("사용량", 0), 0) for name in EXTRA_ITEMS if name in equip}

    main_groups_usage = sum(groups_out[g]["사용량"] for g in ["R", "Co", "K", "C"])
    # Crusher(QR) 포함 5개군 합계 - 목표대비 비교용 (텔레그램 알림 등에서 사용)
    usage_incl_crusher = main_groups_usage + groups_out.get("QR", {}).get("사용량", 0)
    # 전체 설비(그룹 멤버 + 출하/기타/폐열/판매사업) 비용 합계 - 아래 TOU/요금유형 집계와 동일 범위로 통일
    total_cost = sum(equip.get(m, {}).get("비용_합계", 0) for m in equip if m != "합계")

    # 요일별 TOU(시간대별 요금) 구조 - 경부하/중간부하/최대부하 비중
    total_light = sum(equip.get(m, {}).get("비용_경부하", 0) for m in equip if m != "합계")
    total_mid = sum(equip.get(m, {}).get("비용_중간부하", 0) for m in equip if m != "합계")
    total_peak = sum(equip.get(m, {}).get("비용_최대부하", 0) for m in equip if m != "합계")
    total_base_fee = sum(equip.get(m, {}).get("비용_기본요금", 0) for m in equip if m != "합계")
    total_usage_fee = sum(equip.get(m, {}).get("비용_사용요금계", 0) for m in equip if m != "합계")
    tou_total = total_light + total_mid + total_peak
    tou = {
        "경부하_비중": round(total_light/tou_total*100, 1) if tou_total else None,
        "중간부하_비중": round(total_mid/tou_total*100, 1) if tou_total else None,
        "최대부하_비중": round(total_peak/tou_total*100, 1) if tou_total else None,
    }
    fee_type = {
        "기본요금_비중": round(total_base_fee/total_cost*100, 1) if total_cost else None,
        "사용요금_비중": round(total_usage_fee/total_cost*100, 1) if total_cost else None,
    }

    cement_prod = groups_out["C"]["생산량"]
    cost_per_ton = round(total_cost / cement_prod, 0) if cement_prod else None
    avg_price_per_kwh = round(total_cost / main_groups_usage, 1) if main_groups_usage else None
    day_type = "토요일" if weekday_kr == "토" else ("일요일" if weekday_kr == "일" else "평일")

    return {
        "date": date_str,
        "weekday": weekday_kr,
        "day_type": day_type,
        "source": "file",
        "file_name": path.name,
        "groups": groups_out,
        "extra": extra,
        "total_usage_main4": round(main_groups_usage, 0),
        "total_usage_incl_crusher": round(usage_incl_crusher, 0),
        "total_target_usage_incl_crusher": round(target_usage_all, 0),
        "total_cost": round(total_cost, 0),
        "tou": tou,
        "fee_type": fee_type,
        "cost_per_ton_cement": cost_per_ton,
        "avg_price_per_kwh": avg_price_per_kwh,
    }

def main():
    if len(sys.argv) < 2:
        print("사용법: python parse_daily_report.py <전력일보_YYYY_MM_DD.csv>")
        sys.exit(1)

    src = Path(sys.argv[1])

    data_path = Path(__file__).parent / "daily_data.json"
    if data_path.exists():
        data = json.loads(data_path.read_text(encoding="utf-8"))
    else:
        data = {"days": []}

    entry = parse_file(src, prior_days=data["days"])

    existing = next((d for d in data["days"] if d["date"] == entry["date"]), None)
    if existing and existing.get("note"):
        entry["note"] = existing["note"]

    data["days"] = [d for d in data["days"] if d["date"] != entry["date"]]
    data["days"].append(entry)
    data["days"].sort(key=lambda d: d["date"])

    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] {entry['date']} 데이터를 daily_data.json 에 반영했습니다. (총 {len(data['days'])}일 누적)")

if __name__ == "__main__":
    main()
