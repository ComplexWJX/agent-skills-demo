---
name: tj-hostname-model-match
description: >-
  从 tab_attach_device_info 与 tr_rms_lan_host 的 hostname CSV 规约 hostname 和 vendorclassid，按可信来源检索设备型号与属性。新型号追加进 model_attribute_all_market-v1.xlsx 的型号清单和型号属性，已有型号不改。再把命中了型号的行写入 xxxx_hostname_match.csv。在用户提到 tj、hostname 型号匹配、hostname 规约、vendorclassid、命中型号、tab_attach_device_info 或 tr_rms_lan_host 时使用。
disable-model-invocation: true
---

# hostname 型号匹配

底座是当前目录的 `model_attribute_all_market-v1.xlsx`。只给新型号入库；已在型号清单中的型号不改清单、不改属性。找不到可信型号就留空，不要编造。

脚本在本 `SKILL.md` 同级的 `scripts/`。下面的命令在仓库根目录执行，把 `SKILL_DIR` 换成该目录的绝对路径。

## 文件

未指定目录时，在当前仓库根目录找文件。指定了目录时，只在该目录找。一次处理一个源 CSV。用户给出多个文件时按顺序做，不要并行改同一本型号表。

两类源文件：

- `tab_attach_device_info_*_hostname*.csv`，表头 `attach_type,hostname`。只按 hostname 规约。
- `tr_rms_lan_host_*_hostname*.csv`，表头 `x_cu_hosttype,hostname,vendorclassid`。按 hostname 规约，并用 vendorclassid 判断；vendorclassid 可以为空。列名 `vendclassid` 同样认。

`型号清单` 列：厂商、类别、型号、发布时间、来源依据、检索时间。
`型号属性` 列：厂商、类别、型号、属性、来源依据、检索时间。
`断点记录` 列：层级、类别、厂商、阶段、范围、状态、行数、交付物位置、最后更新时间、备注。

不要读、不要改 `待复盘`。不要把源 CSV 整表或 `待检索.csv` 读进上下文。

输出与源文件同目录：去掉主名末尾的 `_hostname` 或 `_hostname-数字`，加上 `_hostname_match.csv`。例如 `tab_attach_device_info_phone_hostname-1.csv` 写成 `tab_attach_device_info_phone_hostname_match.csv`。只写入命中了型号的行，列是源文件全部列再加 `命中型号`。没有命中型号的行不写入。不改源文件。

## 流程

中间文件在仓库 `output/`，主名是源文件去掉扩展名：

- `{主名}-关键字规约.xlsx`
- `{主名}-待检索.csv`
- `{主名}-型号检索.xlsx`

```bash
python SKILL_DIR/scripts/reduce_keywords.py --input <源.csv> --output output/<主名>-关键字规约.xlsx
python SKILL_DIR/scripts/pending_keywords.py --mapping output/<主名>-关键字规约.xlsx --hits output/<主名>-型号检索.xlsx --limit 15
python SKILL_DIR/scripts/lookup_model.py --catalog model_attribute_all_market-v1.xlsx --vendor <厂商> --model "<型号>" --keyword "<关键字>"
python SKILL_DIR/scripts/append_hits.py --hits output/<主名>-型号检索.xlsx --json output/<主名>-batch.json
python SKILL_DIR/scripts/apply_hits.py --catalog model_attribute_all_market-v1.xlsx --input <源.csv> --mapping output/<主名>-关键字规约.xlsx --hits output/<主名>-型号检索.xlsx --dry-run
python SKILL_DIR/scripts/apply_hits.py --catalog model_attribute_all_market-v1.xlsx --input <源.csv> --mapping output/<主名>-关键字规约.xlsx --hits output/<主名>-型号检索.xlsx --checkpoint
```

1. 规约。脚本只把值得检索的关键字写入 `关键字` 页和 `待检索.csv`。单次人名、Windows 随机名、纯品牌词不会出现在待检索里。不要检索那些被跳过的主机名。
2. 用 `pending_keywords.py` 每次取下一批，不要打开整份待检索。关键字、规约规则必须原样抄进检索结果。
3. 逐个关键字检索。结论只允许：`有型号`、`仅系列`、`仅类别`、`空`、`冲突`。一批完就 `append_hits.py`，避免中断后重头检索。已写入的关键字不要重搜，脚本会拒绝覆盖。
4. 只有 `结论=有型号` 且型号、来源都有值，才可能回写命中型号。新型号还要有属性 JSON。`仅系列`、`仅类别`、`空`、`冲突` 不写底座，也不写命中型号。
5. 入库前用 `lookup_model.py`。`MATCH` 且 `同名` 为是：检索结果里的型号用它打印的型号原文，来源用它打印的来源，属性 JSON 留空。`NEW` 才准备新的厂商、类别、型号和属性。`AMBIGUOUS` 时把型号写准再查，不要猜。
6. 全部待检索都有结论后，先 `--dry-run`。确认 `added` 数量后再正式写入。正式写入必须能通过检索完整性检查，并加 `--checkpoint`，往 `断点记录` 追加一条，不改历史行。

文件类型只是线索。`Router` 文件里会有净水器、灯、窗帘，不要因为文件名就写成路由器。`MSFT 5.0` 出现在 vendorclassid 里也不是硬件型号。

## 检索硬规则

- 来源只接受官网规格页、厂商文档、OpenWrt 硬件表、微软协议文档、正规商城商品页。拆机帖、论坛芯片表、百科转载、搜索摘要不能单独作为型号或参数依据。互相矛盾的参数弃用。
- 没有来源的字段留空字符串。不要从相近型号抄参数。`TL-WDR5660千兆版` 与 `TL-WDR5660千兆易展版` 不是同一型号。
- 系列名不是型号。多个 SKU 的系列结论记 `仅系列`。样例里被去掉的若是随机十六进制、`_miap` 或 MAC，关键字可以对应一个型号。被去掉的若是另一套产品编号（如 `021e02` 与 `056a01`），记 `仅系列`。关键字只剩品牌或大类时脚本已经跳过，不要再检索。
- hostname 与 vendorclassid 指向不同设备时：只有一侧能定到具体型号，采用该型号；两侧都能定到不同具体型号，结论记 `冲突`，型号留空。vendorclassid 为空时只看 hostname。
- `MSFT 5.0` 是 Windows DHCP 客户端，不是硬件型号，也不是 Windows 版本。`udhcp` 版本号不是型号。`HP`/`NPI`/`MI` 加 6 位十六进制是 MAC 尾号，不是型号。日期后缀是安装时间，不是型号。
- 断点记录里的「路由器暂不跑」只约束主动全市场爬取。本次从入参检索到、且有来源的新型号仍然入库。

属性 JSON 跟随 `型号属性` 里同一类别已有行的键，见 [reference.md](reference.md)。该类别没有样本时用 `{"cpu":"","mem":"","release_time":""}`。`json.dumps(..., ensure_ascii=False)`。

判定是否已在清单中，以及检索结果列，见 [reference.md](reference.md)。
