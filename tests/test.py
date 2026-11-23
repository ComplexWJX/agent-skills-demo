

from asyncio.log import logger
import json
from pathlib import Path
from unittest import result

print('Hello' in 'Hello, World!')

BASE_DIR = Path(__file__).resolve().parents[1]
print(f"load fetch.json from {BASE_DIR / 'fetch.json'}")
with open (BASE_DIR / "fetch.json", "r", encoding="utf-8") as f:
    result = json.load(f)
    ret = {}
    for key in result:
        print(f"loop key={key}")
        if key in '小米 12S Ultra 官网 规格参数':
            ret = result[key]
    print(f"device_info_search: result={ret}")
    print(ret)