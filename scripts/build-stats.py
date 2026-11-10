#!/usr/bin/env python3
"""Regenerate data/stats.json from data/news.json (Oct 2026 onward)."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEWS_PATH = ROOT / "data" / "news.json"
STATS_PATH = ROOT / "data" / "stats.json"
DATA_START = "2026-10-01"

DISTRICTS = [
    "沙田",
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

HAZARD_RULES: list[tuple[str, list[str]]] = [
    ("火警／火災", ["火", "焚化", "起火"]),
    ("吊船／懸吊", ["吊船", "吊臂", "懸吊", "gondola"]),
    ("車輛／交通界面", ["貨車", "夾斗", "輾", "泥頭車", "修路", "道路", "行車"]),
    ("機械受傷", ["機器", "打包機", "切斷", "割傷"]),
    ("墮下／失平衡", ["墮", "失足", "跌"]),
    ("墜物／尖物", ["鐵枝", "插傷"]),
    ("翻側／受困", ["翻側", "受困", "車底"]),
]


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


def infer_hazard(title: str, summary: str) -> str:
    text = title + (summary or "")
    for label, keywords in HAZARD_RULES:
        for kw in keywords:
            if kw.lower() in text.lower() or kw in text:
                return label
    return "其他"


def normalize_severity(severity: str | None) -> str:
    if severity == "fatal":
        return "fatal"
    return "non_fatal"


def main() -> None:
    with NEWS_PATH.open(encoding="utf-8") as f:
        news = json.load(f)

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
                "_hazard": infer_hazard(item.get("title", ""), item.get("summary", "")),
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
    hazard_counter = Counter(i["_hazard"] for i in items_in_range)

    def counter_to_list(counter: Counter) -> list[dict]:
        return [
            {"label": label, "count": count}
            for label, count in counter.most_common()
        ]

    payload = {
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "dataStart": DATA_START,
        "dataStartLabel": "2026年10月",
        "source": "data/news.json",
        "disclaimer": "下列數字僅反映本網站公開報導收錄之個案，並非勞工處或政府官方工業意外統計。",
        "totals": {
            "all": len(items_in_range),
            "fatal": fatal,
            "non_fatal": non_fatal,
        },
        "byMonth": by_month,
        "byRegion": counter_to_list(region_counter),
        "byHazard": counter_to_list(hazard_counter),
        "itemCount": len(items_in_range),
    }

    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATS_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote {STATS_PATH} ({payload['totals']['all']} items)")


if __name__ == "__main__":
    main()
