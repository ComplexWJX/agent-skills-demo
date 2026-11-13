# 检索记录与去重

## 待检索里会剩下的关键字

脚本用同一套规则重算每行 hostname，不保存百万行主机映射。

会检索：

- 去掉尾部实例号后的型号片段：十六进制、长数字、前缀里已有数字时末尾 1 到 2 位数字、`_miap` 加 4 位十六进制、海尔 `uplus-haier-日期-十六进制-v版本-后缀`、末尾 MAC。
- 同一主机名原文出现不少于 2 次。
- 只出现 1 次，但是中文、以 `TL-` / `MIWIFI-` / `360-ROUTER-` / `NEWIFI` 开头，或 `MW310R`、`DIR-616` 这类短型号。

不检索：Windows 随机名，空主机名，只出现 1 次的普通人名，以及关键字恰好是 `DESKTOP`、`LAPTOP`、`WIN`、`PC`、`USER`、`HP`、`NPI`、`MI`、`DEFAULT`、`UNKNOWN`、`LOCALHOST`、`ANDROID`、`HUAWEI`、`HONOR`、`XIAOMI`、`REDMI`、`OPPO`、`VIVO`、`IPHONE`、`IPAD`、`CAMERA`、`ZTE`。

关键字不是型号。`HUAWEI_P30_PRO` 对应清单里的 `HUAWEI P30 Pro`。下划线、连字符、大小写和品牌别名可以忽略后再比，`HUAWEI_P30` 不等于 `HUAWEI P30 Pro`。

型号写在主机名末尾、前面是随机串的单次记录不会进入待检索。不要把这种行编成型号。

## 检索结果列

工作表名：`检索结果`。用 `append_hits.py` 写入，不要手改表。

| 列 | 要求 |
|---|---|
| 关键字 | 与待检索一致 |
| 规约规则 | 与待检索一致 |
| 结论 | 有型号 / 仅系列 / 仅类别 / 空 / 冲突 |
| 设备类型 | 定不出硬件型号时写类别，如 Windows计算机 |
| 厂商 | 有型号时必填 |
| 类别 | 有型号时必填，用清单里已有类别 |
| 型号 | 仅结论为有型号时填写 |
| 发布时间 | 没有可信月份就留空，格式 `YYYY-MM` |
| 来源 | 可核对的 URL，多个用 ` ; ` 分隔 |
| 依据 | 一句话说明为什么能定到这个型号 |
| 属性JSON | 新型号必填；清单里已有且同名时留空 |

`apply_hits.py` 只把结论为 `有型号` 的行回写到命中型号。

一批的 JSON 是数组。非有型号不要填型号和属性 JSON。

```json
[
  {
    "关键字": "HUAWEI_P30_PRO",
    "规约规则": "前缀-十六进制",
    "结论": "有型号",
    "设备类型": "",
    "厂商": "华为",
    "类别": "手机",
    "型号": "HUAWEI P30 Pro",
    "发布时间": "",
    "来源": "https://<本次打开的规格页或商城页>",
    "依据": "关键字与清单型号同名",
    "属性JSON": ""
  }
]
```

来源必须是这次依据对应的真实页面，不要照抄示例。

## 已在清单中的判定

`lookup_model.py` 和 `apply_hits.py` 用同一规则。先去掉空白并忽略大小写。再把厂商归一（红米/Redmi、水星/Mercury、小米/Xiaomi、华为/HUAWEI、荣耀/HONOR、苹果/Apple、TP-LINK/TPLINK），并从型号字符串里去掉这些品牌别名后比较。

同一型号，不更新：

- `小米路由器4A千兆版` = `小米 路由器4A千兆版`
- `Redmi路由器AC2100` = `红米 Redmi 路由器AC2100`
- `HUAWEI P30 Pro` = `华为 HUAWEI P30 Pro`
- `荣耀 20` = `HONOR 20`

不是同一型号，可以新增：

- `TP-LINK TL-WDR5660千兆版` 与 `TP-LINK TL-WDR5660千兆易展版`
- `小米 路由器AC2100` 与 `红米 Redmi 路由器AC2100`
- `HUAWEI P30` 与 `HUAWEI P30 Pro`
- `荣耀 20` 与 `荣耀 200`

命中型号回写时，用清单里已有的那条型号原文。`MATCH` 且 `同名` 为否时，不能复用清单来源，要另找页面说明这个关键字为什么是该型号；找不到就记 `空`。

`AMBIGUOUS` 表示多条清单型号都相近。改准型号字符串再查，不要选第一条。

## 属性键

新型号的键必须和该类别已有行一致。没有来源的值用空字符串。脚本会按这个顺序重排：

| 类别 | 键 |
|---|---|
| 手机 | cpu, mem, release_time |
| 平板 | cpu, mem, release_time |
| 交换机 | cpu, mem, release_time |
| 打印机 | cpu, mem, release_time |
| 电脑 | release_time, type, cpu, memory, storage, gpu, screen, os, wireless, ports, power, dimension |
| 路由器 | release_time, type, standard, speed, band, ports, antenna, wireless, cpu_mem, power, features, usb |
| 摄像头 | release_time, type, resolution, sensor, night_vision, power, fov, ai, storage, wireless, protection |
| 网关 | release_time, type, wireless, protocol, power |
| 网络存储 | release_time, type, storage, interface, wireless, power |

清单里没有的类别仍可新增，键只用 `cpu`、`mem`、`release_time`。

## 回写

`tab_attach_device_info_phone_hostname-1.csv`：

```csv
"attach_type","hostname","命中型号"
"phone","HUAWEI_P30_Pro-811b1d5ef2","HUAWEI P30 Pro"
```

没有命中型号的行不出现在这个文件里。`tr_rms_lan_host_Router_hostname-1.csv` 同样只输出命中行，前面三列保持 `x_cu_hosttype,hostname,vendorclassid`。

同一关键字下的命中行使用同一个命中型号。未检索、非有型号、或该行规约后对不上关键字时，不写入匹配文件。
