#!/usr/bin/env python3
"""给文件/目录/标准输入做 token 体检。

薄封装：实现位于 token_saver 包，直接运行本文件时会自动把仓库根目录加入 sys.path。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from token_saver.cli import audit_main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(audit_main())
