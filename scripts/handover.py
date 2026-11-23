#!/usr/bin/env python3
"""跨会话交接单：生成/校验/展示。

薄封装：实现位于 token_saver 包，直接运行本文件时会自动把仓库根目录加入 sys.path。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from token_saver.cli import handover_main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(handover_main())
