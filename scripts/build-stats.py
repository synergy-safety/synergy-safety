#!/usr/bin/env python3
"""Regenerate data/stats.json from data/news.json (Oct 2026 onward)."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEWS_PATH = ROOT / "data" / "news.json"
STATS_PATH = ROOT / "data" / "stats.json"
FORM2_TYPES_PATH = ROOT / "data" / "form2-accident-types.json"
DATA_START = "2026-10-01"

DISTRICTS = [
    "沙田",
    "西灣河",
    "將軍澳",
    "葵涌",
    "上水",
    "西貢",
    "青衣",
    "香港仔",
    "中環",
    "粉嶺",
    "荃灣",
    "石鼓洲",
    "九龍",
    "新界",
    "港島",
]

# 勞工處表格2 Rev.17 第K部官方用字。圖表以代號對照此表，不採用 news.json 內的 label。
OFFICIAL_ACCIDENT_TYPES: list[tuple[str, str]] = [
    ("01", "受困於物件之內或物件之間"),
    ("02", "提舉或搬運物件時受傷"),
    ("03", "滑倒、絆倒或在同一高度跌倒"),
    ("04", "人體從高處墮下"),
    ("05", "與固定或不動的物件碰撞"),
    ("06", "與移動的物件碰撞"),
    ("07", "踏在物件上"),
    ("08", "暴露於有害物質中或接觸有害物質"),
    ("09", "觸電或接觸放出的電流"),
    ("10", "受困於倒塌或翻側的物件"),
    ("11", "遭移動或墮下的物件撞擊"),
    ("12", "遭移動中的車輛撞倒"),
    ("13", "觸及開動中的機器或觸及以機器製造中的物件"),
    ("14", "遇溺"),
    ("15", "火警燒傷"),
    ("16", "爆炸受傷"),
    ("17", "其他（請指明）"),
]
OFFICIAL_LABEL_BY_CODE = dict(OFFICIAL_ACCIDENT_TYPES)

DISCLAIMER = (
    "下列數字及意外類別分佈僅反映本網站依公開報導收錄之個案，"
    "並非勞工處、僱主或傷者呈報之官方統計。"
    "意外類別由本站對照勞工處《僱員補償條例》表格2（Rev.17）第K部「意外類別」歸類，"
    "不代表官方調查或呈報定性。"
)


def parse_date(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def month_label(key: str) -> str:
    y, m = key.split("-")
    return f"{y}年{int(m)}月"


def infer_region(location: str | None, title: str) -> str:
    text = (location or "") + title
    for d in DISTRICTS:
        if d in text:
            if d == "石鼓洲":
                return "離島／石鼓洲"
            return d
    return "其他／未標示"


def normalize_severity(severity: str | None) -> str:
    if severity == "fatal":
        return "fatal"
    return "non_fatal"


def accident_code(item: dict) -> str | None:
    at = item.get("accidentType")
    if not isinstance(at, dict):
        return None
    code = at.get("code")
    if code is None:
        return None
    text = str(code).strip()
    if text.isdigit():
        text = text.zfill(2)
    if text in OFFICIAL_LABEL_BY_CODE:
        return text
    return None


def accident_rows(counter: Counter[str]) -> list[dict]:
    rows = []
    for code, label in OFFICIAL_ACCIDENT_TYPES:
        count = int(counter.get(code, 0))
        rows.append(
            {
                "code": code,
                "label": label,
                "chartLabel": f"{code} {label}",
                "count": count,
            }
        )
    return rows


def warn_if_form2_labels_differ(form2_meta: dict) -> None:
    types = form2_meta.get("types") or []
    by_code: dict[str, object] = {}
    for row in types:
        if isinstance(row, dict) and row.get("code") is not None:
            by_code[str(row["code"]).zfill(2)] = row.get("label")
    for code, label in OFFICIAL_ACCIDENT_TYPES:
        if by_code.get(code) != label:
            print(
                f"warning: form2 label for {code} differs from official wording; stats use official wording",
                file=sys.stderr,
            )


def main() -> None:
    with NEWS_PATH.open(encoding="utf-8") as f:
        news = json.load(f)

    form2_meta = {}
    if FORM2_TYPES_PATH.is_file():
        with FORM2_TYPES_PATH.open(encoding="utf-8") as f:
            form2_meta = json.load(f)
    warn_if_form2_labels_differ(form2_meta)

    start = datetime.fromisoformat(DATA_START + "T00:00:00+08:00")
    items_in_range = []

    for item in news.get("items", []):
        occurred = parse_date(item.get("occurredAt")) or parse_date(item.get("publishedAt"))
        if not occurred or occurred < start:
            continue
        items_in_range.append(
            {
                **item,
                "_occurred": occurred,
                "_severity": normalize_severity(item.get("severity")),
                "_region": infer_region(item.get("location"), item.get("title", "")),
            }
        )

    fatal = sum(1 for i in items_in_range if i["_severity"] == "fatal")
    non_fatal = len(items_in_range) - fatal

    by_month_raw: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "fatal": 0, "non_fatal": 0})
    for item in items_in_range:
        key = month_key(item["_occurred"])
        by_month_raw[key]["total"] += 1
        by_month_raw[key][item["_severity"]] += 1

    by_month = [
        {
            "month": key,
            "label": month_label(key),
            **by_month_raw[key],
        }
        for key in sorted(by_month_raw.keys())
    ]

    region_counter = Counter(i["_region"] for i in items_in_range)
    accident_counter: Counter[str] = Counter()
    unclassified = 0
    for item in items_in_range:
        code = accident_code(item)
        if code:
            accident_counter[code] += 1
        else:
            unclassified += 1

    def region_to_list(counter: Counter) -> list[dict]:
        return [
            {"label": label, "count": count}
            for label, count in counter.most_common()
        ]

    payload = {
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "dataStart": DATA_START,
        "dataStartLabel": "2026年10月",
        "source": "data/news.json",
        "accidentTypeBasis": {
            "form": form2_meta.get("form", "L.D. 27(b)(s)(Rev.17)"),
            "section": "K",
            "sectionTitle": form2_meta.get("sectionTitle", "意外類別"),
            "officialFormPdfZh": (form2_meta.get("officialUrls") or {}).get(
                "formPdfZh",
                "https://www.labour.gov.hk/common/form/ecd/pdf/f2_c.pdf",
            ),
        },
        "disclaimer": DISCLAIMER,
        "totals": {
            "all": len(items_in_range),
            "fatal": fatal,
            "non_fatal": non_fatal,
        },
        "byMonth": by_month,
        "byRegion": region_to_list(region_counter),
        "byAccidentType": accident_rows(accident_counter),
        "unclassifiedAccidentType": unclassified,
        "itemCount": len(items_in_range),
    }

    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATS_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote {STATS_PATH} ({payload['totals']['all']} items)")


if __name__ == "__main__":
    main()
