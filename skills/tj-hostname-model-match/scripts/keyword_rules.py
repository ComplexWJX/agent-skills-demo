# -*- coding: utf-8 -*-
"""Hostname reduction and catalog identity rules shared by the skill scripts."""
import json
import re
from collections import Counter

DATE_YMD = re.compile(r"(19|20)\d{2}(0[1-9]|1[0-2])([0-2]\d|3[01])")
WIN_RE = re.compile(r"^(DESKTOP|LAPTOP|WIN)-[A-Z0-9]{5,}$", re.I)
MAC_RE = re.compile(r"^(HP|NPI|MI)([0-9A-F]{6})(?:-\d{1,4})?$", re.I)
SHORT_DATE_RE = re.compile(r"^(.+?)[-_\s](\d{10,14})$")
HEX_TAIL_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]{0,48})[-_]([0-9A-Fa-f]{6,12})$")
LONG_NUM_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]{0,48})[-_](\d{8,})$")
SHORT_NUM_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]{0,48})[-_](\d{1,2})$")
NUM_TAIL_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]{0,48})[-_](\d{3,7})$")
MIAP_RE = re.compile(r"^(.+)_miap([0-9A-Fa-f]{4})$", re.I)
UPLUS_RE = re.compile(r"^(uplus-haier)-\d{4}-[0-9a-f]{4}-(v\d+-[a-z0-9]+)$", re.I)
MAC_TAIL_RE = re.compile(r"^(.+?)[-:]((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})$")
SRV_RE = re.compile(r"^(.+)-srv$", re.I)
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
KEEP_SINGLE = ("TL-", "MIWIFI-", "360-ROUTER-", "NEWIFI")
MODELISH = re.compile(
    r"^(MW\d{3,4}[A-Z]?|DIR-\d{3,4}[A-Z]?|APALIS-[A-Z0-9]+|(?:DELL|ASUS|LENOVO|ROG)-[A-Z0-9-]{2,16})$",
    re.I,
)
CONCLUSIONS = ("有型号", "仅系列", "仅类别", "空", "冲突")
DEFAULT_KEYS = ["cpu", "mem", "release_time"]
CATEGORY_KEYS = {
    "电脑": ["release_time", "type", "cpu", "memory", "storage", "gpu", "screen", "os", "wireless", "ports", "power", "dimension"],
    "手机": ["cpu", "mem", "release_time"],
    "路由器": ["release_time", "type", "standard", "speed", "band", "ports", "antenna", "wireless", "cpu_mem", "power", "features", "usb"],
    "摄像头": ["release_time", "type", "resolution", "sensor", "night_vision", "power", "fov", "ai", "storage", "wireless", "protection"],
    "交换机": ["cpu", "mem", "release_time"],
    "网关": ["release_time", "type", "wireless", "protocol", "power"],
    "网络存储": ["release_time", "type", "storage", "interface", "wireless", "power"],
    "打印机": ["cpu", "mem", "release_time"],
    "平板": ["cpu", "mem", "release_time"],
}
BRAND_TOKENS = [
    "tp-link", "tplink", "mercury", "redmi", "xiaomi", "huawei", "honor", "apple",
    "小米", "红米", "水星", "华为", "荣耀", "苹果", "d-link", "dlink",
]
VENDOR_ALIAS = {
    "xiaomi": "小米",
    "小米": "小米",
    "redmi": "红米",
    "红米": "红米",
    "mercury": "水星",
    "水星": "水星",
    "huawei": "华为",
    "华为": "华为",
    "honor": "荣耀",
    "荣耀": "荣耀",
    "apple": "苹果",
    "苹果": "苹果",
    "tp-link": "tp-link",
    "tplink": "tp-link",
    "d-link": "d-link",
    "dlink": "d-link",
    "360": "360",
}
BARE_KEYWORDS = {
    "DESKTOP": "空",
    "LAPTOP": "空",
    "WIN": "空",
    "PC": "空",
    "USER": "空",
    "HP": "空",
    "NPI": "空",
    "MI": "空",
    "DEFAULT": "空",
    "UNKNOWN": "空",
    "LOCALHOST": "空",
    "ANDROID": "空",
    "HUAWEI": "仅系列",
    "HONOR": "仅系列",
    "XIAOMI": "仅系列",
    "REDMI": "仅系列",
    "OPPO": "仅系列",
    "VIVO": "仅系列",
    "IPHONE": "仅系列",
    "IPAD": "仅系列",
    "CAMERA": "仅类别",
    "ZTE": "仅系列",
}
HIT_COLUMNS = ["关键字", "规约规则", "结论", "设备类型", "厂商", "类别", "型号", "发布时间", "来源", "依据", "属性JSON"]


_ILLEGAL_XLSX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def norm(s):
    if s is None:
        return ""
    return _ILLEGAL_XLSX.sub("", str(s)).strip()


def canon(k):
    k = re.sub(r"\s+", " ", k).strip(" -_")
    if k and re.fullmatch(r"[ -~]+", k):
        return k.upper()
    return k


def fold(s):
    s = str(s or "").casefold()
    s = s.replace("（", "(").replace("）", ")")
    return re.sub(r"\s+", "", s)


def vendor_key(vendor, model):
    v = VENDOR_ALIAS.get(fold(vendor), fold(vendor))
    body = fold(model)
    for token in sorted(BRAND_TOKENS, key=len, reverse=True):
        body = body.replace(token, "")
    return v, body.strip("-_")


def loose_name(s):
    body = fold(s)
    body = body.replace("-", "").replace("_", "")
    for token in sorted(BRAND_TOKENS, key=len, reverse=True):
        body = body.replace(token, "")
    return body.strip()


def same_loose(a, b):
    left, right = loose_name(a), loose_name(b)
    return bool(left) and left == right


def same_model(old_vendor, old_model, new_vendor, new_model):
    if fold(old_model) == fold(new_model) and fold(new_model):
        return True
    ov, ob = vendor_key(old_vendor, old_model)
    nv, nb = vendor_key(new_vendor, new_model)
    return bool(ob) and bool(nb) and (ov, ob) == (nv, nb)


def vendor_compatible(left, right):
    if not norm(left) or not norm(right):
        return True
    return vendor_key(left, "")[0] == vendor_key(right, "")[0]


def keys_for(category):
    return list(CATEGORY_KEYS.get(norm(category), DEFAULT_KEYS))


def normalize_attr(category, raw):
    text = "" if raw is None else str(raw).strip()
    if text in ("", "{}"):
        return ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit("属性JSON无法解析: " + str(exc))
    if not isinstance(data, dict):
        raise SystemExit("属性JSON必须是对象")
    keys = keys_for(category)
    extra = [k for k in data if k not in keys]
    if extra:
        raise SystemExit("属性有多余键 %s，该类别只允许 %s" % (",".join(extra), ",".join(keys)))
    ordered = {}
    for key in keys:
        value = data.get(key, "")
        ordered[key] = "" if value is None else str(value).strip()
    return json.dumps(ordered, ensure_ascii=False)


def check_source(source):
    parts = [part.strip() for part in str(source or "").split(";")]
    parts = [part for part in parts if part]
    if not parts:
        raise SystemExit("有型号但来源为空")
    for part in parts:
        if not (part.startswith("http://") or part.startswith("https://")):
            raise SystemExit("来源不是网页: " + part)
    return " ; ".join(parts)


def norm_vci(v, host):
    v = norm(v)
    host = norm(host)
    if v and v == host:
        return "主机名回声"
    upper = v.upper()
    if v in ("", "::", "-", "0") or upper in ("UNKNOWN", "NONE", "NULL", "OTHER"):
        return "空"
    compact = upper.replace(" ", "")
    if compact in ("MSFT5.0", "MSFT50", "MSFT5"):
        return "MSFT 5.0"
    if upper.startswith("MSFT") and "XBOX" in upper:
        return "MSFT 5.0 XBOX"
    if upper.startswith("MSFT"):
        return upper
    if upper.startswith("UDHCP"):
        return "udhcp"
    squashed = re.sub(r"[\s\-]", "", upper)
    if "OFFICEJET" in squashed:
        return "HP OfficeJet"
    if upper in ("HP PRINTER", "HP NETWORK PRINTER", "HP"):
        return "HP Printer"
    matched = re.fullmatch(r"([A-Z0-9]+):PC:?", upper)
    if matched:
        return matched.group(1) + ":PC"
    return v


def structural(host):
    text = norm(host)
    if not text:
        return "", "空主机名"
    matched = WIN_RE.fullmatch(text)
    if matched:
        return canon(matched.group(1)), "Windows随机名"
    matched = MAC_RE.fullmatch(text)
    if matched:
        return matched.group(1).upper(), "MAC主机名"
    matched = SRV_RE.fullmatch(text)
    if matched and matched.group(1).strip("-_ "):
        return canon(matched.group(1)), "去掉srv后缀"
    matched = DATE_YMD.search(text)
    if matched and matched.start() > 0:
        keyword = text[: matched.start()].strip(" -_")
        if keyword:
            return canon(keyword), "前缀-日期"
    matched = SHORT_DATE_RE.fullmatch(text)
    if matched:
        digits = matched.group(2)
        month, day = int(digits[2:4]), int(digits[4:6])
        year = int(digits[0:2])
        if 1 <= month <= 12 and 1 <= day <= 31 and year <= 40:
            keyword = matched.group(1).strip(" -_")
            if keyword:
                return canon(keyword), "前缀-短日期"
    matched = HEX_TAIL_RE.fullmatch(text)
    if matched and re.search(r"[A-Fa-f]", matched.group(2)):
        return canon(matched.group(1)), "前缀-十六进制"
    matched = LONG_NUM_RE.fullmatch(text)
    if matched:
        return canon(matched.group(1)), "前缀-长数字"
    matched = SHORT_NUM_RE.fullmatch(text)
    if matched and re.search(r"\d", matched.group(1)):
        return canon(matched.group(1)), "前缀-短数字"
    matched = MIAP_RE.fullmatch(text)
    if matched and matched.group(1).strip("-_ "):
        return canon(matched.group(1)), "去掉miap后缀"
    matched = UPLUS_RE.fullmatch(text)
    if matched:
        return canon(matched.group(1) + "-" + matched.group(2)), "前缀-实例号"
    matched = MAC_TAIL_RE.fullmatch(text)
    if matched and matched.group(1).strip("-_ "):
        return canon(matched.group(1)), "去掉MAC后缀"
    return None


def assign_keyword(host, collapsed):
    hit = structural(host)
    if hit:
        return hit
    text = norm(host)
    matched = NUM_TAIL_RE.fullmatch(text)
    if matched:
        prefix = canon(matched.group(1))
        if prefix and prefix in collapsed:
            return prefix, "前缀-重复数字后缀"
    return (canon(text) if text else ""), "原文"


def raw_keep(keyword):
    if not keyword or len(keyword) < 2:
        return False
    upper = keyword.upper()
    if CJK_RE.search(keyword) or upper.startswith(KEEP_SINGLE) or MODELISH.fullmatch(keyword):
        return True
    return False


def early_skip(keyword, rule):
    if rule in ("Windows随机名", "空主机名"):
        return True
    if keyword in BARE_KEYWORDS or keyword in ("DESKTOP", "LAPTOP", "WIN"):
        return True
    if not keyword or len(keyword) < 2:
        return True
    return False


def match_output_path(src):
    from pathlib import Path
    path = Path(src)
    stem = re.sub(r"_hostname(?:-\d+)?$", "", path.stem, flags=re.I)
    return path.with_name(stem + "_hostname_match.csv")


def dedupe_rows(rows):
    kept = []
    seen = set()
    for row in rows:
        key = fold(row["model"])
        if key in seen:
            continue
        seen.add(key)
        kept.append(row)
    return kept


def classify_hit(existing, vendor, model):
    vendor = norm(vendor)
    model = norm(model)
    if not model:
        return "new", None
    exact = dedupe_rows([row for row in existing if fold(row["model"]) == fold(model)])
    if len(exact) == 1:
        return "match", exact[0]
    if len(exact) > 1:
        return "ambiguous", exact
    fuzzy = []
    for row in existing:
        if vendor and not vendor_compatible(row["vendor"], vendor):
            continue
        use_vendor = vendor or row["vendor"]
        if same_model(row["vendor"], row["model"], use_vendor, model):
            fuzzy.append(row)
    fuzzy = dedupe_rows(fuzzy)
    if len(fuzzy) == 1:
        return "match", fuzzy[0]
    if len(fuzzy) > 1:
        return "ambiguous", fuzzy
    return "new", None


def top_text(counter, limit=3):
    if not counter:
        return "", ""
    pairs = counter.most_common(limit)
    main = pairs[0][0]
    detail = "; ".join("%s:%d" % (name, count) for name, count in pairs)
    return main, detail


class Group(object):
    def __init__(self, keyword, rule):
        self.keyword = keyword
        self.rule = rule
        self.rows = 0
        self.distinct = 0
        self.samples = []
        self.vcis = Counter()
        self._seen = set()
        self.capped = False

    def add(self, host, vci):
        self.rows += 1
        if len(self.vcis) < 20 or vci in self.vcis:
            self.vcis[vci] += 1
        else:
            self.vcis["（其他）"] += 1
        if self.capped or host in self._seen:
            return
        self._seen.add(host)
        self.distinct += 1
        if len(self.samples) < 5:
            self.samples.append(host)
        if self.distinct >= 2000:
            self.capped = True
            self._seen.clear()

    def distinct_text(self):
        if self.capped:
            return "2000+"
        return str(self.distinct)

    def as_row(self):
        main, detail = top_text(self.vcis)
        return [
            self.keyword,
            self.rule,
            self.rows,
            self.distinct_text(),
            main,
            detail,
            " | ".join(norm(sample) for sample in self.samples),
            "检索",
        ]


if __name__ == "__main__":
    assert loose_name("HUAWEI_P30_Pro") == loose_name("HUAWEI P30 Pro")
    assert loose_name("HUAWEI_P30") != loose_name("HUAWEI P30 Pro")
    assert loose_name("Redmi-Note-14-Pro") == loose_name("红米 Note 14 Pro")
    assert loose_name("HONOR_20") == loose_name("荣耀 20")
    assert loose_name("HONOR_20") != loose_name("荣耀 200")
    cases = {
        "HUAWEI_P30_Pro-811b1d5ef2": ("HUAWEI_P30_PRO", "前缀-十六进制"),
        "HUAWEI_Mate_30E_Pro_5G-27": ("HUAWEI_MATE_30E_PRO_5G", "前缀-短数字"),
        "nova_8_SE-4e5f5f9da1": ("NOVA_8_SE", "前缀-十六进制"),
        "LAPTOP-B6LUL30K": ("LAPTOP", "Windows随机名"),
        "PC-202101101218": ("PC", "前缀-日期"),
        "yunmi-waterpuri-lx6_miap3BC5": ("YUNMI-WATERPURI-LX6", "去掉miap后缀"),
        "uplus-haier-0128-70f4-v6-sapbz": ("UPLUS-HAIER-V6-SAPBZ", "前缀-实例号"),
        "ZXHN E1630-04:20:84:1a:d9:5f": ("ZXHN E1630", "去掉MAC后缀"),
        "iPhone-11": ("IPHONE-11", "原文"),
    }
    for host, expect in cases.items():
        got = assign_keyword(host, set())
        if got != expect:
            raise SystemExit("%s -> %s, want %s" % (host, got, expect))
    print("ok")
