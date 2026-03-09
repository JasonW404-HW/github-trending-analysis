#!/usr/bin/env python3
"""GitHub Topics Trending CLI 入口，仅负责参数路由。"""

import os
import sys

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.cli_app import run_cli


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:]))
