#!/usr/bin/env python3
"""環境設定載入。

敏感設定（資料源端點、下載模板等）不寫入 repo：
- 本機: 根目錄 .env（已 gitignore）
- 雲端: GitHub Secrets → workflow 注入環境變數
本模組不包含任何敏感值，可安全提交。
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

_loaded = False


def load_dotenv():
    global _loaded
    if _loaded or not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())
    _loaded = True


def get(name: str, default: str = "") -> str:
    load_dotenv()
    return os.environ.get(name, default)


def require(name: str) -> str:
    load_dotenv()
    val = os.environ.get(name, "")
    if not val:
        raise SystemExit(
            f"❌ 缺少必要環境變數: {name}\n"
            f"   本機: 在專案根目錄 .env 填寫\n"
            f"   雲端: 在 GitHub Secrets 設定 {name}"
        )
    return val
