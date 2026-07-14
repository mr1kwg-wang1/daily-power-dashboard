"""
성신양회 단양공장 전력일보 자동 파싱 스크립트
사용법: python parse_daily_report.py <전력일보_YYYY_MM_DD.csv>
같은 폴더의 daily_data.json 에 해당 일자 데이터를 추가/갱신한다.
"""
import sys, csv, re, json
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
        groups_out[gkey] = {
            "label": ginfo["label"],
            "생산량": round(prod, 0),
            "사용량": round(usage, 0),
            "원단위": round(usage / prod, 2) if prod else None,
            "전력비용": round(cost, 0),
            "설비": {m: {"사용량": round(equip.get(m, {}).get("사용량", 0), 0),
                        "생산량": round(equip.get(m, {}).get("생산량", 0), 0)}
                     for m in members if m in equip},
        }

    extra = {name: round(equip.get(name, {}).get("사용량", 0), 0) for name in EXTRA_ITEMS if name in equip}

    main_groups_usage = sum(groups_out[g]["사용량"] for g in ["R", "Co", "K", "C"])
    total_cost = sum(groups_out[g]["전력비용"] for g in GROUPS) 

    return {
        "date": date_str,
        "source": "file",
        "file_name": path.name,
        "groups": groups_out,
        "extra": extra,
        "total_usage_main4": round(main_groups_usage, 0),
        "total_cost": round(total_cost, 0),
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
