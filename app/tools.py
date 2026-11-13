"""The capability boundary: only these registered functions are executable."""
from datetime import datetime
import json
import logging
import sys
import subprocess
from pathlib import Path
from statistics import mean
from pathlib import Path

from langchain.tools import tool

from app.skills import SkillRegistry

logger = logging.getLogger(__name__)

SKILL_DIR = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "tj-hostname-model-match"
)

SCRIPT_PATH = SKILL_DIR / "scripts" / "reduce_keywords.py"


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
    def reduce_keywords(inputCsv: str, outputCsv: str = "C:\\Users\\wjxa6\\Desktop\\待检索.csv"):
        """规约。脚本只把值得检索的关键字写入 `关键字` 页和 `待检索.csv`。"""
        return run_script(str(SCRIPT_PATH), ["--input", inputCsv, "--output", outputCsv])

    @tool
    def pending_keywords(mapping: str, limit: int = 15):
        """每次从待检索文件取一批型号进行处理"""
        return run_script(str(SCRIPT_PATH), ["--mapping", mapping, "--limit", str(limit)])

    @tool
    def lookup_model(catalog: str, model: str, keyword: str):
        """原始检索关键字，用于判定是否同名"""
        return run_script(str(SCRIPT_PATH), ["--catalog", catalog, "--model", model, "--keyword", keyword])

    @tool
    def apply_hits(catalog: str, mapping: str, hits: str, checkpoint: str):
        """规约。脚本只把值得检索的关键字写入 `关键字` 页和 `待检索.csv`。"""
        return run_script(str(SCRIPT_PATH), ["--catalog", catalog, "--mapping", mapping, "--hits", hits, "--checkpoint", checkpoint])

    @tool
    def append_hits(hits: str, output: str):
        """规约。脚本只把值得检索的关键字写入 `关键字` 页和 `待检索.csv`。"""
        return run_script(str(SCRIPT_PATH), ["--hits", hits, "--output", output])

    return [load_skill, read_skill_reference, get_device_status,
            get_device_events, summarize_heartbeat_intervals, reduce_keywords, lookup_model, apply_hits, append_hits]

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