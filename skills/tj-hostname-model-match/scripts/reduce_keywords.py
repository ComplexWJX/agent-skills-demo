# -*- coding: utf-8 -*-
"""Reduce hostname CSV rows into keyword groups worth searching."""
import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyword_rules as kr


KEYWORD_HEADER = ["关键字", "规约规则", "行数", "不同主机名数", "主要vendorClass", "vendorClass分布", "样例主机名", "检索建议"]


def open_text(path):
    raw = open(path, "rb")
    sample = raw.read(8192)
    raw.close()
    encoding = "utf-8-sig"
    try:
        sample.decode("utf-8-sig")
    except UnicodeDecodeError:
        encoding = "gb18030"
    return open(path, "r", encoding=encoding, newline=""), encoding


def header_index(header):
    found = {}
    for index, name in enumerate(header):
        if name is None:
            continue
        found[str(name).strip().lower()] = index
    return found


def pick(found, names):
    for name in names:
        if name.lower() in found:
            return found[name.lower()]
    return None


def detect(header):
    found = header_index(header)
    host = pick(found, ("hostname", "host_name"))
    vci = pick(found, ("vendorclassid", "vendclassid", "vendor_class_id"))
    attach = pick(found, ("attach_type",))
    hosttype = pick(found, ("x_cu_hosttype",))
    if "命中型号" in found:
        raise SystemExit("这是结果文件，不是源文件")
    if host is None:
        raise SystemExit("缺少列: hostname")
    if attach is not None and vci is None:
        return "tab_attach_device_info", host, None, attach
    if hosttype is not None and vci is not None:
        return "tr_rms_lan_host", host, vci, hosttype
    raise SystemExit("无法识别表头，需要 attach_type+hostname，或 x_cu_hosttype+hostname+vendorclassid")


def cell(row, index):
    if index is None or index >= len(row):
        return ""
    return row[index]


def iter_rows(path):
    handle, encoding = open_text(path)
    try:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            raise SystemExit("CSV 为空")
        kind, host_i, vci_i, type_i = detect(header)
        yield ("meta", kind, encoding, header, host_i, vci_i, type_i)
        for row in reader:
            yield ("row", row)
    finally:
        handle.close()


def collect_collapsed(path, host_i):
    families = defaultdict(set)
    rows = 0
    handle, _encoding = open_text(path)
    try:
        reader = csv.reader(handle)
        next(reader)
        for row in reader:
            rows += 1
            host = cell(row, host_i)
            if kr.structural(host):
                continue
            matched = kr.NUM_TAIL_RE.fullmatch(kr.norm(host))
            if not matched:
                continue
            prefix = kr.canon(matched.group(1))
            if prefix:
                families[prefix].add(kr.norm(host))
    finally:
        handle.close()
    collapsed = {prefix: len(hosts) for prefix, hosts in families.items() if len(hosts) >= 5}
    return collapsed, rows


def style_header(sheet, widths):
    fill = PatternFill("solid", fgColor="1F4E79")
    font = Font(color="FFFFFF", bold=True)
    for item in sheet[1]:
        item.fill = fill
        item.font = font
        item.alignment = Alignment(vertical="center")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    meta = None
    for item in iter_rows(args.input):
        meta = item
        break
    if not meta:
        raise SystemExit("CSV 为空")
    _tag, kind, encoding, _header, host_i, vci_i, _type_i = meta
    collapsed, row_count = collect_collapsed(args.input, host_i)

    groups = {}
    plain = {}
    early = {}
    seen = 0
    handle, _encoding = open_text(args.input)
    try:
        reader = csv.reader(handle)
        next(reader)
        for row in reader:
            seen += 1
            host = cell(row, host_i)
            vci = kr.norm_vci(cell(row, vci_i), host) if vci_i is not None else "空"
            keyword, rule = kr.assign_keyword(host, collapsed)
            if kr.early_skip(keyword, rule):
                key = (keyword, rule)
                early[key] = early.get(key, 0) + 1
                continue
            if rule != "原文" or kr.raw_keep(keyword):
                group = groups.get((keyword, rule))
                if group is None:
                    group = kr.Group(keyword, rule)
                    groups[(keyword, rule)] = group
                group.add(host, vci)
                continue
            key = (keyword, rule)
            if key in groups:
                groups[key].add(host, vci)
                continue
            if keyword in plain:
                first_host, first_vci = plain.pop(keyword)
                group = kr.Group(keyword, rule)
                group.add(first_host, first_vci)
                group.add(host, vci)
                groups[key] = group
                continue
            plain[keyword] = (host, vci)
            if seen % 200000 == 0:
                print("scanned", seen)
    finally:
        handle.close()

    accounted = sum(group.rows for group in groups.values()) + sum(early.values()) + len(plain)
    if accounted != row_count or seen != row_count:
        raise SystemExit("行数对不上: scanned=%s pass1=%s accounted=%s" % (seen, row_count, accounted))

    ordered = sorted(groups.values(), key=lambda group: (-group.rows, group.keyword, group.rule))
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path = out_path.with_name(out_path.stem.replace("-关键字规约", "") + "-待检索.csv")

    book = Workbook()
    sheet = book.active
    sheet.title = "关键字"
    sheet.append(KEYWORD_HEADER)
    with queue_path.open("w", encoding="utf-8-sig", newline="") as queue_file:
        writer = csv.writer(queue_file)
        writer.writerow(KEYWORD_HEADER)
        for group in ordered:
            row = group.as_row()
            sheet.append(row)
            writer.writerow(row)
    style_header(sheet, [36, 22, 10, 16, 22, 42, 70, 12])

    stats = defaultdict(lambda: [0, 0, 0])
    for group in ordered:
        item = stats[group.rule]
        item[0] += 1
        item[1] += group.rows
        item[2] += group.rows
    for (keyword, rule), count in early.items():
        item = stats[rule]
        item[0] += 1
        item[1] += count
    if plain:
        item = stats["原文"]
        item[0] += len(plain)
        item[1] += len(plain)

    summary = book.create_sheet("规则统计")
    summary.append(["规约规则", "关键字组数", "原始行数", "建议检索行数"])
    for rule, item in sorted(stats.items(), key=lambda pair: -pair[1][1]):
        summary.append([rule, item[0], item[1], item[2]])
    summary.append([
        "合计",
        sum(item[0] for item in stats.values()),
        sum(item[1] for item in stats.values()),
        sum(item[2] for item in stats.values()),
    ])
    style_header(summary, [24, 14, 14, 16])

    prefixes = book.create_sheet("前缀决策")
    prefixes.append(["前缀", "不同主机名数"])
    for prefix, count in sorted(collapsed.items(), key=lambda pair: (-pair[1], pair[0])):
        prefixes.append([prefix, count])
    style_header(prefixes, [36, 16])

    info = book.create_sheet("文件信息")
    info.append(["项", "值"])
    info.append(["来源文件", str(Path(args.input).resolve())])
    info.append(["文件类型", kind])
    info.append(["编码", encoding])
    info.append(["原始行数", row_count])
    info.append(["检索组数", len(ordered)])
    info.append(["跳过组数", sum(item[0] for item in stats.values()) - len(ordered)])
    info.append(["待检索", str(queue_path.resolve())])
    style_header(info, [16, 80])

    book.save(out_path)
    print("kind", kind)
    print("rows", row_count)
    print("search_groups", len(ordered))
    print("skipped_single", len(plain))
    print("OUT", out_path)
    print("QUEUE", queue_path)


if __name__ == "__main__":
    main()
