#!/usr/bin/env python3
"""Regenerate data/stats.json from data/news.json (Oct 2026 onward)."""

from __future__ import annotations

import json
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
    "石鼓洲",
    "九龍",
    "新界",
    "港島",
]

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


def accident_type_key(item: dict) -> tuple[str, str] | None:
    at = item.get("accidentType")
    if not isinstance(at, dict):
        return None
    code = at.get("code")
    label = at.get("label")
    if not code or not label:
        return None
    return (str(code).zfill(2), label)


def counter_to_accident_list(counter: Counter[tuple[str, str]]) -> list[dict]:
    rows = []
    for (code, label), count in counter.items():
        rows.append(
            {
                "code": code,
                "label": label,
                "chartLabel": f"{code} {label}",
                "count": count,
            }
        )
    rows.sort(key=lambda r: r["code"])
    return rows


def main() -> None:
    with NEWS_PATH.open(encoding="utf-8") as f:
        news = json.load(f)

    form2_meta = {}
    if FORM2_TYPES_PATH.is_file():
        with FORM2_TYPES_PATH.open(encoding="utf-8") as f:
            form2_meta = json.load(f)

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
    accident_counter: Counter[tuple[str, str]] = Counter()
    unclassified = 0
    for item in items_in_range:
        key = accident_type_key(item)
        if key:
            accident_counter[key] += 1
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
        "byAccidentType": counter_to_accident_list(accident_counter),
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
