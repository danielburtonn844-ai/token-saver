"""让测试无论用 pytest 还是 unittest 都能从仓库根目录导入包。"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
