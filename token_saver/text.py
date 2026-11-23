"""公共文本工具：token 估算、ANSI 清理、编码识别、安全读取。

所有模块共用这一份实现，避免四个脚本各抄一套系数导致结果不一致。
系数经 bench/calibrate.py 对 cl100k_base 拟合：CJK 字 1.24、字母与空格 0.19、
数字与符号 0.64。测试集中位误差 4.9%，p90 7.2%，详见 bench/CALIBRATION.md。
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
    "decode_bytes",
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

MAX_BYTES = 64 * 1024 * 1024

BOMS = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32"),
    (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)

VALID_ENCODINGS = ("auto", "utf-8", "gb18030", "utf-16", "latin-1")


def clean_ansi(text: str) -> str:
    """去掉 ANSI 转义序列。"""
    return ANSI.sub("", text)


def est_tokens(text: str) -> int:
    """中英混合 token 估算（cl100k 校准）。

    三类计权：CJK 字、字母与空格、数字与符号。实测中位误差约 4.9%，
    p90 约 7.2%，可用于「压不压」的取舍，不要用来核对账单。
    """
    if not text:
        return 0
    cjk = len(CJK.findall(text))
    cjk_punct = len(CJK_PUNCT.findall(text))  # 同属 CJK 与「非单词字符」，需扣掉
    symbols = len(NONWORD.findall(text)) - cjk_punct + len(DIGIT.findall(text))
    other = len(text) - cjk - symbols
    return max(1, int(round(cjk * CJK_WEIGHT + other * LATIN_WEIGHT + symbols * SYMBOL_WEIGHT)))


def _printable_ratio(text: str) -> float:
    """可打印字符占比，用于判断 UTF-16 是不是真文本。"""
    if not text:
        return 0.0
    good = sum(1 for ch in text if ch >= " " or ch in "\t\n\r")
    return good / len(text)


ASCII_PUNCT = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")


def _textual_ratio(text: str) -> float:
    """像正经文本的字符占比：字母数字、空白、ASCII 标点。"""
    if not text:
        return 0.0
    good = sum(1 for ch in text if ch.isalnum() or ch.isspace() or ch in ASCII_PUNCT)
    return good / len(text)


def _utf16_encoding(head: bytes) -> str | None:
    """通过 NUL 分布判断是不是无 BOM 的 UTF-16。"""
    if len(head) < 8 or b"\x00" not in head:
        return None
    half = len(head) // 2
    for enc, lane in (("utf-16-le", 1), ("utf-16-be", 0)):
        lane_zeros = sum(1 for i in range(lane, len(head), 2) if head[i] == 0)
        if lane_zeros / half > 0.6:
            try:
                decoded = head.decode(enc, errors="ignore")
            except LookupError:
                continue
            uniq = len(set(decoded))
            if (_printable_ratio(decoded) > 0.9 and _textual_ratio(decoded) > 0.6
                    and uniq >= 8 and ("\n" in decoded or " " in decoded or uniq >= 20)):
                return enc
    return None


def looks_binary(data: bytes, sample: int = 8192) -> bool:
    """判断字节流是否像二进制。

    规则：有 BOM 一律当文本；有 NUL 的先用 UTF-16 试解码；
    其余按 C0 控制字符比例判断（GBK 高位字节不算控制字符，因此不会误伤）。
    """
    if not data:
        return False
    if any(data.startswith(bom) for bom, _ in BOMS):
        return False
    head = data[:sample]
    if b"\x00" in head:
        return _utf16_encoding(head) is None
    ctrl = sum(1 for b in head if b < 9 or 13 < b < 32 or b == 127)
    return ctrl / len(head) > 0.15


def decode_bytes(data: bytes, encoding: str = "auto") -> tuple[str, str]:
    """解码字节流，返回 ``(文本, 实际使用的编码)``。

    auto 顺序：BOM → UTF-8 → GB18030 → Latin-1。GB18030 覆盖绝大多数
    中文 Windows 日志，Latin-1 兜底保证不抛异常。
    """
    if encoding not in ("auto", None):
        return data.decode(encoding, errors="replace"), encoding

    for bom, enc in BOMS:
        if data.startswith(bom):
            return data.decode(enc, errors="replace"), enc

    utf16 = _utf16_encoding(data[:8192])
    if utf16:
        try:
            return data.decode(utf16), utf16
        except UnicodeDecodeError:
            pass

    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("gb18030"), "gb18030"
    except UnicodeDecodeError:
        pass
    return data.decode("latin-1", errors="replace"), "latin-1"


def read_bytes(path: str, max_bytes: int = MAX_BYTES) -> tuple[bytes, bool]:
    """读取文件或 stdin（path 为 ``-``）。返回 ``(数据, 是否被截断)``。"""
    if path == "-":
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        data = stream.read(max_bytes + 1)
    else:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            data = fh.read(max_bytes + 1)
        if size > max_bytes:
            return data[:max_bytes], True
    if len(data) > max_bytes:
        return data[:max_bytes], True
    return data, False


def read_text(path: str, max_bytes: int = MAX_BYTES,
              encoding: str = "auto") -> tuple[str, bool, str]:
    """读取并按 auto/指定编码解码。返回 ``(文本, 是否截断, 实际编码)``。"""
    data, cut = read_bytes(path, max_bytes)
    text, used = decode_bytes(data, encoding)
    return text, cut, used


def split_lines(text: str) -> list[str]:
    """按通用换行切分，去掉行尾残留的 ``\\r``。"""
    return [ln.rstrip("\r") for ln in text.splitlines()]
