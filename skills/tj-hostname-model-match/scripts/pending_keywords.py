# -*- coding: utf-8 -*-
"""Print the next unfinished search keywords."""
import argparse
import sys
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyword_rules as kr


def sheet_rows(path, title):
    if not path.exists():
        return []
    book = load_workbook(path, read_only=True, data_only=True)
    if title not in book.sheetnames:
        book.close()
        if title == "检索结果":
            return []
        raise SystemExit("缺少工作表: " + title)
    sheet = book[title]
    rows = list(sheet.iter_rows(values_only=True))
    book.close()
    return rows


def index_of(header):
    return {str(name).strip(): index for index, name in enumerate(header) if name is not None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--hits", required=True)
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args()

    mapping = Path(args.mapping)
    keywords = sheet_rows(mapping, "关键字")
    if not keywords:
        raise SystemExit("规约文件没有关键字")
    header = index_of(keywords[0])
    for name in ("关键字", "规约规则"):
        if name not in header:
            raise SystemExit("关键字页缺少列: " + name)

    done = set()
    hits = sheet_rows(Path(args.hits), "检索结果")
    if hits:
        hit_header = index_of(hits[0])
        if "关键字" in hit_header and "规约规则" in hit_header:
            for row in hits[1:]:
                keyword = kr.norm(row[hit_header["关键字"]] if hit_header["关键字"] < len(row) else "")
                rule = kr.norm(row[hit_header["规约规则"]] if hit_header["规约规则"] < len(row) else "")
                if keyword:
                    done.add((keyword, rule))

    pending = []
    for row in keywords[1:]:
        keyword = kr.norm(row[header["关键字"]] if header["关键字"] < len(row) else "")
        rule = kr.norm(row[header["规约规则"]] if header["规约规则"] < len(row) else "")
        if not keyword or (keyword, rule) in done:
            continue
        pending.append(row)
    shown = pending[: max(args.limit, 0)]
    columns = ["关键字", "规约规则", "行数", "主要vendorClass", "vendorClass分布", "样例主机名"]
    print("\t".join(columns))
    for row in shown:
        values = []
        for name in columns:
            if name not in header or header[name] >= len(row) or row[header[name]] is None:
                values.append("")
            else:
                values.append(str(row[header[name]]).replace("\t", " "))
        print("\t".join(values))
    print("shown", len(shown))
    print("remaining", len(pending))


if __name__ == "__main__":
    main()
