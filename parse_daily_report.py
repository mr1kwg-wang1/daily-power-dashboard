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

def to_float(s):
    s = (s or "").strip()
    if s in ("", "-"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0

def parse_file(path: Path):
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    m = re.search(r"(\d{4})_(\d{2})_(\d{2})", path.stem)
    if not m:
        raise ValueError(f"파일명에서 날짜를 찾을 수 없습니다: {path.name}")
    date_str = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    weekday_kr = ["월","화","수","목","금","토","일"][datetime.date.fromisoformat(date_str).weekday()]

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
    for gkey, ginfo in GROUPS.items():
        members = ginfo["members"]
        prod = sum(equip.get(m, {}).get("생산량", 0) for m in members)
        usage = sum(equip.get(m, {}).get("사용량", 0) for m in members)
        cost = sum(equip.get(m, {}).get("비용_합계", 0) for m in members)

        equip_detail = {}
        gap_candidates = []
        for m in members:
            if m not in equip:
                continue
            e = equip[m]
            entry = {
                "사용량": round(e.get("사용량", 0), 0),
                "생산량": round(e.get("생산량", 0), 0),
                "목표_원단위": round(e.get("원단위_목표_part", 0), 2) if e.get("원단위_목표_part") else None,
                "실적_원단위": round(e.get("원단위_실적_part", 0), 2) if e.get("생산량", 0) > 0 else None,
            }
            equip_detail[m] = entry
            if entry["목표_원단위"] and entry["실적_원단위"] and entry["생산량"] > 0:
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
            "전력비용": round(cost, 0),
            "설비": equip_detail,
            "최대목표초과설비": {"설비": over_candidates[0][0], "목표대비차이": round(over_candidates[0][1],2), "목표대비율": round(over_candidates[0][2],1)} if over_candidates else None,
            "목표초과설비목록": [{"설비": c[0], "목표대비차이": round(c[1],2), "목표대비율": round(c[2],1)} for c in over_candidates],
        }

    extra = {name: round(equip.get(name, {}).get("사용량", 0), 0) for name in EXTRA_ITEMS if name in equip}

    main_groups_usage = sum(groups_out[g]["사용량"] for g in ["R", "Co", "K", "C"])
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
    entry = parse_file(src)

    data_path = Path(__file__).parent / "daily_data.json"
    if data_path.exists():
        data = json.loads(data_path.read_text(encoding="utf-8"))
    else:
        data = {"days": []}

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
