# -*- coding: utf-8 -*-
"""Append search conclusions to the 型号检索 workbook."""
import argparse
import json
import sys
from pathlib import Path

from openpyxl import Workbook, load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyword_rules as kr


def load_objects(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    data = json.loads(text)
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    raise SystemExit("JSON 必须是对象或数组")


def existing_keys(sheet):
    found = {}
    for index, cell in enumerate(sheet[1], 1):
        if cell.value is not None:
            found[str(cell.value).strip()] = index
    keys = set()
    key_col = found.get("关键字")
    rule_col = found.get("规约规则")
    if not key_col or not rule_col:
        return keys
    for row in sheet.iter_rows(min_row=2, values_only=True):
        keyword = kr.norm(row[key_col - 1] if key_col - 1 < len(row) else "")
        rule = kr.norm(row[rule_col - 1] if rule_col - 1 < len(row) else "")
        if keyword:
            keys.add((keyword, rule))
    return keys


def value_of(item, name):
    if name not in item or item[name] is None:
        return ""
    return str(item[name]).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hits", required=True)
    parser.add_argument("--json", required=True)
    args = parser.parse_args()

    rows = []
    for item in load_objects(args.json):
        keyword = value_of(item, "关键字")
        rule = value_of(item, "规约规则")
        conclusion = value_of(item, "结论")
        if not keyword or not rule:
            raise SystemExit("缺少关键字或规约规则")
        if conclusion not in kr.CONCLUSIONS:
            raise SystemExit("结论不合法: " + conclusion)
        model = value_of(item, "型号")
        source = value_of(item, "来源")
        attr = value_of(item, "属性JSON")
        if conclusion == "有型号":
            if not model:
                raise SystemExit("有型号但型号为空: " + keyword)
            if not value_of(item, "厂商") or not value_of(item, "类别"):
                raise SystemExit("有型号但厂商或类别为空: " + keyword)
            source = kr.check_source(source)
            if attr:
                attr = kr.normalize_attr(value_of(item, "类别"), attr)
        elif model or attr:
            raise SystemExit("非有型号不能填写型号或属性JSON: " + keyword)
        rows.append([
            keyword,
            rule,
            conclusion,
            value_of(item, "设备类型"),
            value_of(item, "厂商"),
            value_of(item, "类别"),
            model,
            value_of(item, "发布时间"),
            source,
            value_of(item, "依据"),
            attr,
        ])

    path = Path(args.hits)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        book = load_workbook(path)
        if "检索结果" not in book.sheetnames:
            raise SystemExit("命中文件缺少工作表: 检索结果")
        sheet = book["检索结果"]
    else:
        book = Workbook()
        sheet = book.active
        sheet.title = "检索结果"
        sheet.append(kr.HIT_COLUMNS)
    have = existing_keys(sheet)
    added = 0
    for row in rows:
        key = (row[0], row[1])
        if key in have:
            raise SystemExit("检索结果已有该关键字，不覆盖: %s / %s" % key)
        sheet.append(row)
        have.add(key)
        added += 1
    book.save(path)
    print("appended", added)
    print("OUT", path)


if __name__ == "__main__":
    main()
