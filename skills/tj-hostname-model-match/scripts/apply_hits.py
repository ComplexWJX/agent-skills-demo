# -*- coding: utf-8 -*-
"""Append new models to the catalog and write xxxx_hostname_match.csv."""
import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyword_rules as kr


def sheet_values(path, title):
    book = load_workbook(path, read_only=True, data_only=True)
    if title not in book.sheetnames:
        book.close()
        raise SystemExit("缺少工作表: " + title)
    sheet = book[title]
    rows = list(sheet.iter_rows(values_only=True))
    book.close()
    return rows


def header_index(header):
    return {str(name).strip(): index for index, name in enumerate(header) if name is not None}


def load_collapsed(path):
    rows = sheet_values(path, "前缀决策")
    collapsed = set()
    if not rows:
        return collapsed
    for row in rows[1:]:
        prefix = kr.norm(row[0] if row else "")
        if prefix:
            collapsed.add(prefix)
    return collapsed


def load_keywords(path):
    rows = sheet_values(path, "关键字")
    if not rows:
        return []
    header = header_index(rows[0])
    found = []
    for row in rows[1:]:
        keyword = kr.norm(row[header["关键字"]] if header["关键字"] < len(row) else "")
        rule = kr.norm(row[header["规约规则"]] if header["规约规则"] < len(row) else "")
        if keyword:
            found.append((keyword, rule))
    return found


def load_catalog_rows(path):
    book = load_workbook(path, read_only=True, data_only=True)
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
    return rows


def load_hits(path):
    if not Path(path).exists():
        return []
    rows = sheet_values(path, "检索结果")
    if not rows:
        return []
    header = header_index(rows[0])
    for name in ("关键字", "规约规则", "结论", "厂商", "类别", "型号", "来源", "属性JSON"):
        if name not in header:
            raise SystemExit("检索结果缺少列: " + name)
    hits = []
    for row in rows[1:]:
        def take(name):
            index = header[name]
            if index >= len(row) or row[index] is None:
                return ""
            return str(row[index]).strip()

        conclusion = take("结论")
        if conclusion not in kr.CONCLUSIONS:
            raise SystemExit("结论不合法: " + conclusion)
        item = {
            "keyword": take("关键字"),
            "rule": take("规约规则"),
            "conclusion": conclusion,
            "vendor": take("厂商"),
            "category": take("类别"),
            "model": take("型号"),
            "release": take("发布时间") if "发布时间" in header else "",
            "source": take("来源"),
            "attr": take("属性JSON"),
        }
        if not item["keyword"]:
            continue
        hits.append(item)
    return hits


def open_text(path):
    raw = open(path, "rb")
    sample = raw.read(8192)
    raw.close()
    encoding = "utf-8-sig"
    try:
        sample.decode("utf-8-sig")
    except UnicodeDecodeError:
        encoding = "gb18030"
    return open(path, "r", encoding=encoding, newline="")


def detect_columns(header):
    found = {str(name).strip().lower(): index for index, name in enumerate(header)}
    if "命中型号" in found:
        raise SystemExit("这是结果文件，不是源文件")
    host = None
    for name in ("hostname", "host_name"):
        if name in found:
            host = found[name]
    if host is None:
        raise SystemExit("缺少列: hostname")
    return host


def resolve_hits(existing, hits):
    resolved = {}
    added = []
    skipped = []
    blocked = []
    for hit in hits:
        key = (hit["keyword"], hit["rule"])
        if hit["conclusion"] != "有型号":
            continue
        if not hit["model"] or not hit["source"]:
            raise SystemExit("有型号但型号或来源为空: " + hit["keyword"])
        kr.check_source(hit["source"])
        status, row = kr.classify_hit(existing, hit["vendor"], hit["model"])
        if status == "ambiguous":
            names = " | ".join(item["model"] for item in row[:8])
            blocked.append((hit["keyword"], names))
            continue
        if status == "match":
            hit["model"] = row["model"]
            hit["vendor"] = row["vendor"]
            hit["category"] = row["category"]
            skipped.append(hit["model"])
            resolved[key] = hit["model"]
            continue
        attr = kr.normalize_attr(hit["category"], hit["attr"])
        if not attr:
            raise SystemExit("新型号缺少属性JSON: " + hit["model"])
        hit["attr"] = attr
        if not hit["vendor"] or not hit["category"]:
            raise SystemExit("新型号缺少厂商或类别: " + hit["model"])
        added.append(hit)
        existing.append({
            "vendor": hit["vendor"],
            "category": hit["category"],
            "model": hit["model"],
            "source": hit["source"],
        })
        resolved[key] = hit["model"]
    return resolved, added, skipped, blocked


def count_or_write(path, host_index, collapsed, resolved, destination):
    filled = 0
    empty = 0
    source = open_text(path)
    target = None
    writer = None
    temp = None
    try:
        reader = csv.reader(source)
        header = next(reader)
        if destination is not None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp = destination.with_suffix(destination.suffix + ".partial")
            target = open(temp, "w", encoding="utf-8-sig", newline="")
            writer = csv.writer(target, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
            writer.writerow(list(header) + ["命中型号"])
        for row in reader:
            host = row[host_index] if host_index < len(row) else ""
            keyword, rule = kr.assign_keyword(host, collapsed)
            model = resolved.get((keyword, rule), "")
            if not model:
                empty += 1
                continue
            filled += 1
            if writer is not None:
                width = len(header)
                copied = list(row[:width])
                if len(copied) < width:
                    copied.extend([""] * (width - len(copied)))
                writer.writerow(copied + [model])
    finally:
        source.close()
        if target is not None:
            target.close()
    if temp is not None and destination is not None:
        temp.replace(destination)
    return filled, empty


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--hits", required=True)
    parser.add_argument("--match-output", default="")
    parser.add_argument("--checkpoint", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()

    keywords = load_keywords(args.mapping)
    hits = load_hits(args.hits)
    done = {(hit["keyword"], hit["rule"]) for hit in hits}
    unsearched = [key for key in keywords if key not in done]
    if unsearched and not args.allow_partial and (args.checkpoint or not args.dry_run):
        raise SystemExit("还有 %d 个关键字没有检索结果" % len(unsearched))

    collapsed = load_collapsed(args.mapping)
    existing = load_catalog_rows(args.catalog)
    resolved, added, skipped, blocked = resolve_hits(existing, hits)
    if blocked:
        for keyword, names in blocked:
            print("CONFLICT", keyword, names)
        raise SystemExit("型号与清单中的多条相近，请改准后再写入")

    source = open_text(args.input)
    try:
        header = next(csv.reader(source))
    finally:
        source.close()
    host_index = detect_columns(header)
    destination = Path(args.match_output) if args.match_output else kr.match_output_path(args.input)
    filled, empty = count_or_write(
        args.input,
        host_index,
        collapsed,
        resolved,
        None if args.dry_run else destination,
    )

    print("added", len(added))
    print("skipped", len(skipped))
    print("match_filled", filled)
    print("match_empty", empty)
    print("unsearched", len(unsearched))
    for hit in added:
        print("NEW", hit["model"])
    if args.dry_run:
        print("dry-run")
        return

    today = date.today().isoformat()
    book = load_workbook(args.catalog, keep_links=False)
    for name in ("型号清单", "型号属性"):
        if name not in book.sheetnames:
            raise SystemExit("底座缺少工作表: " + name)
    list_sheet = book["型号清单"]
    attr_sheet = book["型号属性"]
    for hit in added:
        list_sheet.append([
            hit["vendor"], hit["category"], hit["model"],
            hit["release"] or None, hit["source"], today,
        ])
        attr_sheet.append([
            hit["vendor"], hit["category"], hit["model"],
            hit["attr"], hit["source"], today,
        ])
    if args.checkpoint:
        if "断点记录" not in book.sheetnames:
            raise SystemExit("底座缺少工作表: 断点记录")
        categories = sorted({hit["category"] for hit in added if hit["category"]})
        category = categories[0] if len(categories) == 1 else "（混合）"
        book["断点记录"].append([
            "厂商",
            category or "（混合）",
            "（全）",
            "型号+属性",
            args.input,
            "done",
            len(added),
            "型号清单新增 %d；命中型号 %d 行；%s" % (len(added), filled, destination),
            today,
            "hostname补录 %s；已在清单中未改 %d" % (args.input, len(skipped)),
        ])
    try:
        book.save(args.catalog)
        print("saved_catalog")
    except PermissionError:
        alt = str(Path(args.catalog).with_suffix("")) + ".待写入.xlsx"
        book.save(alt)
        print("catalog_locked")
        print(alt)
    index = Path("output") / "catalog-index.json"
    if index.exists():
        index.unlink()
    print("saved_match")
    print(destination)


if __name__ == "__main__":
    main()
