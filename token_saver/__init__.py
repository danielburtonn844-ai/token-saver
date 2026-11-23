"""token-saver —— 省 token 但不降智的工具与作业规范。

四个小工具共用同一套 token 估算口径：

>>> from token_saver import est_tokens
>>> est_tokens("hello 世界")
6
"""
from __future__ import annotations

__version__ = "2.1.0"
__all__ = ["__version__", "est_tokens"]

from .text import est_tokens  # noqa: E402,F401
