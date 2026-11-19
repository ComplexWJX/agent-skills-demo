

import json
from pathlib import Path

print('Hello' in 'Hello, World!')

BASE_DIR = Path(__file__).resolve().parents[1]
print(f"load fetch.json from {BASE_DIR / 'fetch.json'}")
with open (BASE_DIR / "fetch.json", "r", encoding="utf-8") as f:
    res = json.load(f)
    print(res)