"""The capability boundary: only these registered functions are executable."""
from datetime import datetime
import json
import logging
import re
import sys
import subprocess
from pathlib import Path
from statistics import mean
from pathlib import Path

from langchain.tools import tool

from app.skills import SkillRegistry

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s %(levelname)s "
        "%(name)s:%(lineno)d - %(message)s"
    ),
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]

SKILL_DIR = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "tj-hostname-model-match"
)

SCRIPT_PATH = SKILL_DIR / "scripts"

PENDING_REQUIRED_COLUMNS = ("关键字", "规约规则")
LOOKUP_STATUSES = {"MATCH", "NEW", "AMBIGUOUS"}


def parse_pending_keywords_output(text: str) -> dict:
    """Parse pending_keywords.py TSV rows and its trailing counters."""
    header = None
    rows = []
    metrics = {}
    metric_pattern = re.compile(r"^(shown|remaining) (\d+)$")

    for line in text.splitlines():
        if not line:
            continue
        metric_match = metric_pattern.fullmatch(line.strip())
        if metric_match:
            key, value = metric_match.groups()
            if key in metrics:
                raise ValueError("待检索输出包含重复计数: " + key)
            metrics[key] = int(value)
            continue
        if line.startswith("关键字\t"):
            if header is not None:
                raise ValueError("待检索输出包含重复表头")
            header = line.split("\t")
            if len(set(header)) != len(header):
                raise ValueError("待检索表头包含重复字段")
            missing = [name for name in PENDING_REQUIRED_COLUMNS if name not in header]
            if missing:
                raise ValueError("待检索表头缺少字段: " + ",".join(missing))
            continue
        if header is None:
            raise ValueError("无法识别待检索表头")
        values = line.split("\t")
        if len(values) != len(header):
            raise ValueError("待检索字段数不正确")
        rows.append(dict(zip(header, values)))

    if header is None:
        raise ValueError("无法识别待检索表头")
    for key in ("shown", "remaining"):
        if key not in metrics:
            raise ValueError("待检索输出缺少计数: " + key)
    if metrics["shown"] != len(rows):
        raise ValueError("shown 与待检索行数不一致")
    if metrics["remaining"] < metrics["shown"]:
        raise ValueError("remaining 小于 shown")
    return {"keywords": rows, "shown": metrics["shown"],
            "remaining": metrics["remaining"]}


def parse_lookup_model_output(text: str) -> dict:
    """Parse lookup_model.py MATCH, NEW, and AMBIGUOUS outputs."""
    lines = [line for line in text.splitlines() if line]
    if not lines:
        raise ValueError("型号查重输出为空")
    status = lines[0].strip()
    if status not in LOOKUP_STATUSES:
        raise ValueError("无法识别型号查重状态: " + status)

    if status == "AMBIGUOUS":
        candidates = []
        total = None
        for line in lines[1:]:
            count_match = re.fullmatch(r"count (\d+)", line.strip())
            if count_match:
                if total is not None:
                    raise ValueError("型号查重输出包含重复 count")
                total = int(count_match.group(1))
                continue
            values = line.split("\t")
            if len(values) != 3:
                raise ValueError("歧义候选字段数不正确")
            candidates.append({"厂商": values[0], "类别": values[1], "型号": values[2]})
        if total is None:
            raise ValueError("歧义结果缺少 count")
        if total < len(candidates):
            raise ValueError("count 小于返回的歧义候选数")
        return {"status": status, "candidates": candidates, "count": total}

    fields = {}
    for line in lines[1:]:
        tab = line.find("\t")
        if tab < 1:
            raise ValueError("型号查重字段格式不正确")
        key, value = line[:tab], line[tab + 1:]
        if key in fields:
            raise ValueError("型号查重输出包含重复字段: " + key)
        fields[key] = value

    required_fields = (("厂商", "类别", "型号", "来源", "属性键")
                       if status == "MATCH" else ("属性键",))
    missing = [name for name in required_fields if name not in fields]
    if missing:
        raise ValueError("型号查重输出缺少字段: " + ",".join(missing))
    if "同名" in fields and fields["同名"] not in ("是", "否"):
        raise ValueError("同名字段只能为是或否")
    return {"status": status, **fields}


def parse_script_result(result: dict, parser) -> dict:
    """Keep process failures intact and parse only successful stdout."""
    if "error" in result or result.get("returncode") != 0:
        return result
    try:
        parsed = parser(result.get("stdout", ""))
    except (TypeError, ValueError) as exc:
        return {"error": "invalid_script_output", "detail": str(exc),
                "returncode": result.get("returncode"),
                "stderr": result.get("stderr", "")}
    parsed["returncode"] = result["returncode"]
    if result.get("stderr"):
        parsed["stderr"] = result["stderr"]
    return parsed


class DeviceRepository:
    """Local fixture; replace methods with authenticated HTTP/DB adapters."""
    def __init__(self, fixture: Path):
        self.data = json.loads(fixture.read_text(encoding="utf-8"))

    def get(self, device_id: str) -> dict | None:
        return self.data["devices"].get(device_id)


def build_tools(registry: SkillRegistry, repository: DeviceRepository):
    @tool
    def load_skill(skill_name: str) -> dict:
        """按 skill_name 加载完整 Skill 操作说明；处理匹配任务前先调用。"""
        try:
            instructions = registry.load(skill_name)
        except (ValueError, OSError, UnicodeError) as exc:
            logger.warning("load_skill failed: %s", type(exc).__name__)
            return {"error": "skill_unavailable", "available": registry.catalog()}
        logger.info("skill_loaded name=%s", skill_name)
        return {"skill_name": skill_name, "instructions": instructions}

    @tool
    def read_skill_reference(skill_name: str, relative_path: str) -> dict:
        """读取 Skill 明确引用的 references/*.md 文档，路径相对该 Skill 目录。"""
        try:
            return {"skill_name": skill_name, "path": relative_path,
                    "content": registry.read_reference(skill_name, relative_path)}
        except (ValueError, OSError, UnicodeError):
            return {"error": "reference_unavailable", "hint": "Use a listed references/*.md path"}

    @tool
    def get_device_status(device_id: str) -> dict:
        """查询设备最后业务心跳、心跳间隔和传输连接状态；示例读取固定测试数据。"""
        device = repository.get(device_id)
        if device is None:
            return {"error": "device_not_found", "device_id": device_id}
        observed = repository.data["observed_at"]
        age = (datetime.fromisoformat(observed) - datetime.fromisoformat(device["last_heartbeat"])).total_seconds()
        return {"device_id": device_id, "source": repository.data["source"],
                "observed_at": observed, "last_heartbeat": device["last_heartbeat"],
                "heartbeat_age_seconds": age,
                "expected_heartbeat_seconds": device["expected_heartbeat_seconds"],
                "transport_connected": device["transport_connected"]}

    @tool
    def get_device_events(device_id: str) -> dict:
        """查询设备事件证据，区分业务心跳、服务端 ping 发送和客户端回应。"""
        device = repository.get(device_id)
        if device is None:
            return {"error": "device_not_found", "device_id": device_id}
        return {"device_id": device_id, "source": repository.data["source"],
                "observed_at": repository.data["observed_at"], "events": device["events"]}

    @tool
    def summarize_heartbeat_intervals(device_id: str) -> dict:
        """确定性统计心跳间隔：样本量、均值、最大值，以及超过预期间隔两倍的样本占比。"""
        device = repository.get(device_id)
        if device is None:
            return {"error": "device_not_found", "device_id": device_id}
        values = device["heartbeat_delays_seconds"]
        threshold = 2 * device["expected_heartbeat_seconds"]
        count = sum(value > threshold for value in values)
        return {"device_id": device_id, "source": repository.data["source"],
                "observed_at": repository.data["observed_at"], "sample_count": len(values),
                "mean_seconds": round(mean(values), 2) if values else None,
                "max_seconds": max(values) if values else None,
                "threshold_seconds": threshold, "exceeding_count": count,
                "exceeding_ratio": round(count / len(values), 4) if values else None}

    @tool
    def reduce_keywords(inputCsv: str, outputCsv: str):
        """规约。脚本只把值得检索的关键字写入 `关键字` 页和 `待检索.csv`。"""
        res = run_script(str(SCRIPT_PATH  / "reduce_keywords.py"), ["--input", BASE_DIR / inputCsv, "--output", BASE_DIR / outputCsv])
        # logger.info("reduce_keywords: result=%s", res)
        return res

    @tool
    def pending_keywords(mapping: str, hits: str, limit: int = 15):
        """读取下一批未检索关键字，返回关键字列表及 shown/remaining 计数。"""
        logger.info("pending_keywords: mapping=%s, hits=%s, limit=%d base_dir=%s", str(BASE_DIR  / mapping), str(BASE_DIR  / hits), limit, BASE_DIR)
        result = run_script(str(SCRIPT_PATH / "pending_keywords.py"),
                            ["--mapping", str(BASE_DIR / mapping),
                             "--hits", str(BASE_DIR / hits), "--limit", str(limit)])
        retObject = parse_script_result(result, parse_pending_keywords_output)
        logger.info("pending_keywords parse: retObject=%s", retObject)
        keywords = []
        if "keywords" in retObject:
            keywords = [row["关键字"] for row in retObject["keywords"]]
        logger.info("pending_keywords: keywords=%s", keywords)    
        return keywords

    @tool
    def device_info_search(keyword: str, limit: int = 5):
        """调用搜索引擎，返回网页标题和 URL，keyword是精简的型号关键字，limit是返回结果数。"""
        logger.info("device_info_search: keyword=%s, limit=%d", keyword, limit)
        # result = json.loads(BASE_DIR / "fetch.json")
        result = {}
        with open (BASE_DIR / "fetch.json", "r", encoding="utf-8") as f:
            result = json.load(f)
            for key in result:
                if key in keyword:
                    result = result[key]
        logger.info("device_info_search: result=%s", result)                    
        return result # TODO: replace with real search engine call

    @tool
    def lookup_model(catalog: str, vendor: str, model: str, keyword: str):
        """查询型号底座，结构化返回 MATCH、NEW 或 AMBIGUOUS 结果。"""
        result = run_script(str(SCRIPT_PATH / "lookup_model.py"),
                            ["--catalog", str(BASE_DIR / catalog), "--vendor", vendor,
                             "--model", model, "--keyword", keyword])
        return parse_script_result(result, parse_lookup_model_output)

    @tool
    def apply_hits(catalog: str, mapping: str, hits: str, args: list[str]):
        """1.先预演新增量和命中量(--dry-run)；2.正式追加新型号、生成命中 CSV，并写入断点记录(--checkpoint)"""
        return run_script(str(SCRIPT_PATH / "apply_hits.py"), ["--catalog", str(BASE_DIR / catalog), "--mapping", str(BASE_DIR / 'output' / mapping), "--hits", str(BASE_DIR / 'output' / hits), *args])

    @tool
    def append_hits(hits: str, output: str):
        """负责严格校验并增量保存每批结论，禁止覆盖"""
        return run_script(str(SCRIPT_PATH / "append_hits.py"), ["--hits", str(BASE_DIR / 'output' / hits), "--output", str(BASE_DIR / output)])

    return [load_skill, read_skill_reference, get_device_status,
            get_device_events, summarize_heartbeat_intervals, reduce_keywords, pending_keywords, lookup_model,
              apply_hits, append_hits, device_info_search]

def run_script(script_path: str, args: list[str]) -> dict:
    if not Path(script_path).is_file():
        return {
            "error": "script_not_found",
            "path": script_path,
        }

    try:
        result = subprocess.run(
            [
                sys.executable,
                script_path,
                *args
            ],
            cwd=str(SKILL_DIR),
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {"error": "script_timeout"}

    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
