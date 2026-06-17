#!/usr/bin/env python3
"""FastAPI 服务启动入口"""
import sys
import uvicorn
from dotenv import load_dotenv

# Windows 默认 GBK 编码无法处理 Unicode 日志字符，强制设为 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

if __name__ == "__main__":
    uvicorn.run("src.api:app", host="0.0.0.0", port=8099, reload=False)
