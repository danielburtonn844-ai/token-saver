"""公共文本工具：token 估算、ANSI 清理、安全读取、二进制识别。

所有模块共用这一份实现，避免四个脚本各抄一套系数导致结果不一致。
系数经 bench/calibrate.py 对 cl100k_base 拟合：CJK 字 1.24、字母与空格 0.19、
数字与符号 0.64。测试集中位误差 5.9%，p90 13.6%，详见 bench/CALIBRATION.md。
"""
from __future__ import annotations

import os
import re
import sys

__all__ = [
    "ANSI",
    "CJK",
    "CJK_WEIGHT",
    "LATIN_WEIGHT",
    "SYMBOL_WEIGHT",
    "MAX_BYTES",
    "clean_ansi",
    "est_tokens",
    "looks_binary",
    "read_bytes",
    "read_text",
    "split_lines",
]

# 覆盖 CSI（含 ?25l 这类私有模式）、OSC（标题/超链接）、以及两字节 ESC 序列。
ANSI = re.compile(
    r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]"  # CSI
    r"|\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC … BEL / ST
    r"|[@-_])"  # 两字节序列
)

# CJK 汉字、假名、全角字符（含 CJK 标点，与校准脚本口径一致）
CJK = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef]")
# CJK 标点与全角符号：计入「符号」类，且要从 CJK 计数中排除
CJK_PUNCT = re.compile(r"[\u3000-\u303f\ufe30-\ufe4f\uff00-\uffef]")
# 非单词、非空白字符：英文标点、符号、括号
NONWORD = re.compile(r"[^\w\s]")
DIGIT = re.compile(r"[0-9]")

# 校准结果（cl100k_base）。改这三个值等于改全站估算。
CJK_WEIGHT = 1.24
LATIN_WEIGHT = 0.19
SYMBOL_WEIGHT = 0.64

# 默认单次读取上限，防止误把几个 G 的日志灌进内存。
MAX_BYTES = 64 * 1024 * 1024


def clean_ansi(text: str) -> str:
    """去掉 ANSI 转义序列。"""
    return ANSI.sub("", text)


def est_tokens(text: str) -> int:
    """中英混合 token 估算（cl100k 校准）。

    三类计权：CJK 字、字母与空格、数字与符号。实测中位误差约 6%，
    p90 约 14%，可用于「压不压」的取舍，不要用来核对账单。
    """
    if not text:
        return 0
    cjk = len(CJK.findall(text))
    cjk_punct = len(CJK_PUNCT.findall(text))  # 同时属于 CJK 与「非单词字符」，需从符号里扣掉
    symbols = len(NONWORD.findall(text)) - cjk_punct + len(DIGIT.findall(text))
    other = len(text) - cjk - symbols
    return max(1, int(round(cjk * CJK_WEIGHT + other * LATIN_WEIGHT + symbols * SYMBOL_WEIGHT)))


def looks_binary(data: bytes, sample: int = 8192) -> bool:
    """判断字节流是否像二进制。

    先看 NUL（最可靠的信号），再按 UTF-8 解码后的替换字符比例判断：
    正常 UTF-8 文本几乎不会产生 U+FFFD，二进制乱码会大量产生。
    """
    if not data:
        return False
    head = data[:sample]
    if b"\x00" in head:
        return True
    decoded = head.decode("utf-8", errors="replace")
    bad = decoded.count("\ufffd")
    if decoded and bad / len(decoded) > 0.02:
        return True
    # 兜底：大量控制字符也算二进制
    ctrl = sum(1 for b in head if b < 9 or 13 < b < 32 or b == 127)
    return ctrl / len(head) > 0.15


def read_bytes(path: str, max_bytes: int = MAX_BYTES) -> tuple[bytes, bool]:
    """读取文件或 stdin（path 为 ``-``）。

    返回 ``(数据, 是否被截断)``。stdin 只读一次，不做 seek。
    """
    if path == "-":
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        data = stream.read(max_bytes + 1)
    else:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            data = fh.read(max_bytes + 1)
        if size > max_bytes:
            data = data[:max_bytes]
            return data, True
    if len(data) > max_bytes:
        return data[:max_bytes], True
    return data, False


def read_text(path: str, max_bytes: int = MAX_BYTES) -> tuple[str, bool]:
    """按 UTF-8 读取并替换坏字节，二进制输入不再抛 UnicodeDecodeError。"""
    data, cut = read_bytes(path, max_bytes)
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return data.decode("utf-8", errors="replace"), cut


def split_lines(text: str) -> list[str]:
    """按通用换行切分，去掉行尾残留的 ``\\r``。"""
    return [ln.rstrip("\r") for ln in text.splitlines()]
