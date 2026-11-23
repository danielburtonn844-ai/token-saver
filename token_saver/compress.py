"""工具输出压缩：去噪 → 折叠 → 打分 → 保头尾 → 按预算补满。

设计约束（v2.1）：
- 预算默认是软上限：头尾行受保护，宁可超一点也不能丢上下文。
  ``strict=True`` 时改为硬上限，超了就按分数从低到高丢弃。
- 错误行默认不丢，``keep_errors=True``；显式 ``drop_errors`` 才允许省略。
- 二进制作输入直接拒绝，不产生乱码。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text import MAX_BYTES, clean_ansi, decode_bytes, est_tokens, looks_binary, read_bytes

__all__ = ["PROFILES", "CompressResult", "compress", "detect_profile", "load_input", "Stats"]

ERR = re.compile(
    r"\berror\b|exception|traceback|fatal|critical|panic|failed|failure|denied|"
    r"timeout|refused|not found|undefined|cannot|invalid|segfault|killed|oom|"
    r"错误|失败|异常|超时|拒绝|崩溃",
    re.I,
)
WARN = re.compile(r"\bwarn(?:ing)?\b|deprecated|警告", re.I)
NUM = re.compile(r"\d")
PATH = re.compile(r"(/[\w.\-]+){2,}|[\w\-]+\.(?:py|js|ts|go|java|php|json|log|yml|yaml|md|txt|rs|rb|cs)")
PROGRESS = re.compile(r"^\s*\[[=>#\-\s.]*\]\s*\d{0,3}%?\s*$|^\s*\d{1,3}%\s*[|#=]|\r")
# 同型行签名：抹掉数字、十六进制、UUID、时间戳、IP，只留骨架。
UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
HEX = re.compile(r"\b0x[0-9a-fA-F]+\b")
IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
TIME = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b")

PROFILES = {
    "default": {"budget": 1500, "head": 12, "tail": 8, "max_line": 400},
    "build": {"budget": 1200, "head": 6, "tail": 14, "max_line": 300},
    "test": {"budget": 1500, "head": 4, "tail": 24, "max_line": 400},
    "json": {"budget": 1200, "head": 3, "tail": 3, "max_line": 600},
    "traversal": {"budget": 800, "head": 5, "tail": 5, "max_line": 200},
}

MAX_LINE_HARD = 20000


@dataclass
class Stats:
    raw_lines: int = 0
    kept_lines: int = 0
    skipped_lines: int = 0
    truncated_lines: int = 0
    raw_tokens: int = 0
    out_tokens: int = 0
    budget: int = 0
    over_budget: bool = False
    profile: str = "default"
    input_bytes: int = 0
    truncated_input: bool = False
    encoding: str = "utf-8"

    @property
    def ratio(self) -> float:
        """节省比例（0~1）。空输入按 0 处理。"""
        if self.raw_tokens <= 0:
            return 0.0
        return 1 - self.out_tokens / self.raw_tokens

    def as_dict(self) -> dict:
        d = {
            "raw_lines": self.raw_lines,
            "kept_lines": self.kept_lines,
            "skipped_lines": self.skipped_lines,
            "truncated_lines": self.truncated_lines,
            "raw_tokens": self.raw_tokens,
            "out_tokens": self.out_tokens,
            "budget": self.budget,
            "over_budget": self.over_budget,
            "profile": self.profile,
            "input_bytes": self.input_bytes,
            "truncated_input": self.truncated_input,
            "encoding": self.encoding,
            "saved_ratio": round(self.ratio, 4),
        }
        return d


@dataclass
class CompressResult:
    text: str = ""
    stats: Stats = field(default_factory=Stats)


def signature(line: str) -> str:
    """把易变字段抹平成签名，用于识别同型行。

    先去掉本工具自己加的 `…[同型/重复 ×N]…` 注解，保证输出行与原文行可比。
    """
    s = re.split(r"\s+…\[", line)[0]
    s = UUID.sub("#", s)
    s = TIME.sub("#", s)
    s = IP.sub("#", s)
    s = HEX.sub("#", s)
    s = re.sub(r"\d+", "#", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:160]


def score(line: str) -> int:
    s = 0
    if ERR.search(line):
        s += 8
    if WARN.search(line):
        s += 2
    if NUM.search(line):
        s += 1
    if PATH.search(line):
        s += 2
    if line.strip().startswith(("+", "-", "@@")):
        s += 2
    if len(line.strip()) < 3:
        s -= 3
    if PROGRESS.match(line):
        s -= 8
    return s


def detect_profile(text: str) -> str:
    """按内容猜一个 profile，猜不准就回 default。"""
    head = text[:65536]
    if not head.strip():
        return "default"
    sample = [ln for ln in head.splitlines()[:400] if ln.strip() and not PROGRESS.match(ln)]
    if not sample:
        return "build"
    json_like = sum(
        1 for ln in sample
        if ln.lstrip().startswith(("{", "}", "[{", "}]", '"')) or
        re.match(r'^\s*"[^"]+"\s*:', ln)
    )
    if json_like > len(sample) * 0.5:
        return "json"
    if sum(1 for ln in head.splitlines()[:400] if PROGRESS.match(ln)) > 40:
        return "build"
    if sum(1 for ln in sample if ln.startswith(("+", "-", "@@", "--- ", "+++ "))) > len(sample) * 0.25:
        return "default"
    if re.search(r"^(?:PASS|FAIL|ok |not ok |\s*✓|\s*✗)", head, re.M):
        return "test"
    if re.search(r"^(?:[-dl][rwx-]{9}\s|\S+/\s*$)", head, re.M):
        return "traversal"
    return "default"


def load_input(path: str, max_bytes: int = MAX_BYTES,
               encoding: str = "auto") -> tuple[str, int, bool, str]:
    """读输入并清理 ANSI。二进制直接抛 ValueError，避免产出乱码。

    编码默认 auto：BOM → UTF-8 → GB18030 → Latin-1，GBK 中文日志不会被误杀。
    """
    data, cut = read_bytes(path, max_bytes)
    if looks_binary(data):
        raise ValueError("输入看起来是二进制文件，已拒绝压缩（可先 xxd/strings 处理）")
    text, used = decode_bytes(data, encoding)
    return clean_ansi(text), len(data), cut, used


def _fold_repeats(lines: list[str]) -> list[tuple[int, str, int]]:
    folded: list[tuple[int, str, int]] = []
    i = 0
    while i < len(lines):
        j = i
        while j + 1 < len(lines) and lines[j + 1] == lines[i]:
            j += 1
        n = j - i + 1
        if n >= 3 and lines[i].strip():
            folded.append((i, f"{lines[i]}    …[重复 ×{n}]…", n))
        else:
            for k in range(i, j + 1):
                folded.append((k, lines[k], 1))
        i = j + 1
    return folded


def compress(
    lines: list[str],
    budget: int = 1500,
    head: int | None = None,
    tail: int | None = None,
    max_line: int = 400,
    keep_errors: bool = True,
    strict: bool = False,
    profile: str = "default",
    _depth: int = 0,
) -> CompressResult:
    """压缩入口。纯函数，便于测试。"""
    if budget < 0:
        raise ValueError("budget 不能为负数")
    if head is None:
        head = 12
    if tail is None:
        tail = 8
    if head < 0 or tail < 0:
        raise ValueError("head/tail 不能为负数")
    if max_line < 0 or max_line > MAX_LINE_HARD:
        raise ValueError(f"max-line 必须在 0..{MAX_LINE_HARD} 之间（0 表示不截断）")

    stats = Stats(budget=budget, profile=profile)
    stats.raw_lines = len(lines)
    stats.raw_tokens = est_tokens("\n".join(lines))
    if not lines:
        return CompressResult("", stats)

    # 1) 行内截断
    norm = []
    for ln in lines:
        if max_line and len(ln) > max_line:
            stats.truncated_lines += 1
            keep = max_line // 2
            ln = f"{ln[:keep]} …[截断 {len(ln) - max_line} 字符]… {ln[-keep // 2:]}"
        norm.append(ln.rstrip())

    # 2) 连续重复折叠
    folded = _fold_repeats(norm)
    total = len(folded)
    head_n = min(head, total)
    tail_n = min(tail, total - head_n)

    # 头尾是受保护的固定开销：预算小时按 token 成本从少保留，避免预算形同虚设
    costs = [est_tokens(line) for _, line, _ in folded]
    allowance = max(int(budget * 0.6), 40)
    head_cost = sum(costs[:head_n])
    tail_cost = sum(costs[total - tail_n:]) if tail_n else 0
    while head_n + tail_n > 2 and head_cost + tail_cost > allowance:
        if head_cost >= tail_cost and head_n > 1:
            head_n -= 1
            head_cost -= costs[head_n]
        elif tail_n > 1:
            tail_n -= 1
            tail_cost -= costs[total - tail_n - 1]
        else:
            head_n -= 1
            head_cost -= costs[head_n]
    protected = set(range(head_n)) | set(range(total - tail_n, total))
    keep = set(protected)

    # 3) 同型行折叠：签名相同且 >= 4 条时只留第一条（头尾受保护）
    buckets: dict[str, list[int]] = {}
    for idx, (_, line, _) in enumerate(folded):
        if line.strip() and not line.startswith("…["):
            buckets.setdefault(signature(line), []).append(idx)
    dropped: set[int] = set()
    same_kind: dict[int, int] = {}
    for idxs in buckets.values():
        if len(idxs) >= 4:
            n_drop = sum(1 for i in idxs[1:] if i not in protected)
            if n_drop:
                same_kind[idxs[0]] = n_drop
                dropped.update(i for i in idxs[1:] if i not in protected)
                keep.add(idxs[0])  # 代表行必须在场，否则次数标注看不见
    keep -= dropped

    # 4) 错误行默认保底：不进预算裁剪；但同型重复的（骨架相同 ≥4 条）
    #    已经在第 3 步折叠成一个代表行并标注次数，不再重复保留。
    if keep_errors:
        for idx, (_, line, _) in enumerate(folded):
            if ERR.search(line) and idx not in dropped:
                keep.add(idx)

    used = sum(est_tokens(folded[i][1]) for i in sorted(keep))
    rest = sorted(
        (i for i in range(total) if i not in keep and i not in dropped),
        key=lambda i: (score(folded[i][1]), -i),
        reverse=True,
    )

    if not strict:
        # 软上限：补满预算即停，头尾可能让总量略超
        for i in rest:
            t = est_tokens(folded[i][1])
            if used + t > budget:
                continue
            keep.add(i)
            used += t
    else:
        # 硬上限：先补高分行，再从头尾往外丢分最低的行，直到不超预算
        for i in rest:
            if used + est_tokens(folded[i][1]) > budget:
                continue
            keep.add(i)
            used += est_tokens(folded[i][1])
        if used > budget:
            def _rank(i: int):
                line = folded[i][1]
                return (bool(keep_errors and ERR.search(line)), i in protected,
                        score(line), -i)

            removable = sorted((i for i in keep if i not in dropped), key=_rank)
            for i in removable:
                if used <= budget:
                    break
                keep.discard(i)
                used -= est_tokens(folded[i][1])

    # 5) 还原顺序 + 省略标记
    out: list[str] = []
    cur_skip = 0
    for i in range(total):
        if i in keep:
            if cur_skip:
                out.append(f"…[省略 {cur_skip} 行]…")
                cur_skip = 0
            line = folded[i][1]
            if i in same_kind:
                line = f"{line}    …[同型 ×{same_kind[i]}]…"
            out.append(line)
        else:
            cur_skip += folded[i][2]
            stats.skipped_lines += folded[i][2]
    if cur_skip:
        out.append(f"…[省略 {cur_skip} 行]…")

    text = "\n".join(out)
    stats.kept_lines = len(keep)
    stats.out_tokens = est_tokens(text)
    stats.over_budget = stats.out_tokens > budget

    # 硬上限：省略标记本身也占 token，按实际超出的量收紧预算重算，最多三轮
    if strict and stats.over_budget and budget > 0 and _depth < 3:
        tighter = max(0, budget - (stats.out_tokens - budget) - 8)
        return compress(lines, budget=tighter, head=head, tail=tail, max_line=max_line,
                        keep_errors=keep_errors, strict=strict, profile=profile,
                        _depth=_depth + 1)

    # 硬上限的兜底：预算连一个省略标记都放不下时，宁可输出空也不超预算
    if strict and stats.out_tokens > budget:
        text = ""
        stats.out_tokens = 0
        stats.kept_lines = 0
        stats.over_budget = False
    return CompressResult(text, stats)
