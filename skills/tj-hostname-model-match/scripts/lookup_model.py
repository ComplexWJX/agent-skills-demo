# -*- coding: utf-8 -*-
"""Check whether a model is already in 型号清单 without loading the workbook into context."""
import argparse
import json
import sys
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyword_rules as kr


def cache_path():
    return Path("output") / "catalog-index.json"


def load_index(catalog):
    catalog = Path(catalog).resolve()
    cache = cache_path()
    stamp = catalog.stat().st_mtime
    if cache.exists():
        try:
            saved = json.loads(cache.read_text(encoding="utf-8"))
            if saved.get("catalog") == str(catalog) and saved.get("mtime") == stamp:
                return saved["rows"]
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    book = load_workbook(catalog, read_only=True, data_only=True)
    if "型号清单" not in book.sheetnames:
        book.close()
        raise SystemExit("底座缺少工作表: 型号清单")
    sheet = book["型号清单"]
    rows = []
    for row in sheet.iter_rows(min_row=2, max_col=5, values_only=True):
        model = kr.norm(row[2] if len(row) > 2 else "")
        if not model:
            continue
        rows.append({
            "vendor": kr.norm(row[0]),
            "category": kr.norm(row[1]),
            "model": model,
            "source": kr.norm(row[4] if len(row) > 4 else ""),
        })
    book.close()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({
        "catalog": str(catalog),
        "mtime": stamp,
        "rows": rows,
    }, ensure_ascii=False), encoding="utf-8")
    return rows


def emit(status, row, keyword):
    print(status)
    if row:
        print("厂商\t" + row["vendor"])
        print("类别\t" + row["category"])
        print("型号\t" + row["model"])
        print("来源\t" + row["source"])
        print("属性键\t" + ",".join(kr.keys_for(row["category"])))
        if keyword:
            print("同名\t" + ("是" if kr.same_loose(keyword, row["model"]) else "否"))
        return
    print("属性键\t" + ",".join(kr.DEFAULT_KEYS))
    if keyword:
        print("同名\t否")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--vendor", default="")
    parser.add_argument("--keyword", default="")
    args = parser.parse_args()

    status, row = kr.classify_hit(load_index(args.catalog), args.vendor, args.model)
    if status == "ambiguous":
        print("AMBIGUOUS")
        for item in row[:10]:
            print("%s\t%s\t%s" % (item["vendor"], item["category"], item["model"]))
        print("count", len(row))
        return
    if status == "match":
        emit("MATCH", row, args.keyword)
        return
    emit("NEW", None, args.keyword)


if __name__ == "__main__":
    main()
