#!/usr/bin/env python3
"""compress_toolout.py — 把冗长的工具输出压成「能看懂又便宜」的摘要。

用法：
    cmd 2>&1 | python3 compress_toolout.py --budget 1500
    python3 compress_toolout.py --file /tmp/build.log --budget 2000 --keep-errors
    python3 compress_toolout.py --file big.log --budget 0 --stats   # 只看统计

策略：去 ANSI → 截超长行 → 折叠连续重复 → 打分 → 保头尾 → 按分补满预算。
输出里保留 `…[省略 N 行]…` 标记，原始路径写在末尾。
"""
import argparse
import os
import re
import sys

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
CJK = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")

ERR = re.compile(
    r"error|exception|traceback|fatal|critical|panic|failed|failure|denied|"
    r"timeout|refused|not found|undefined|cannot|invalid|错误|失败|异常|超时|拒绝",
    re.I,
)
WARN = re.compile(r"warn|deprecated|警告", re.I)
NUM = re.compile(r"\d")
PATH = re.compile(r"(/[\w.\-]+){2,}|[\w\-]+\.(py|js|ts|go|java|php|json|log|yml|yaml|md|txt)")
PROGRESS = re.compile(r"^\s*\[[=>#\-\s.]*\]\s*\d{0,3}%?\s*$|^\s*\d{1,3}%\s*[|#=]")


def est_tokens(s: str) -> int:
    cjk = len(CJK.findall(s))
    return int(cjk * 0.6 + (len(s) - cjk) * 0.28) + 1


def signature(line: str) -> str:
    """把数字/十六进制/IP 抹平成签名，用于识别「同型行」。"""
    s = re.sub(r"\b0x[0-9a-fA-F]+\b", "#", line)
    s = re.sub(r"\d+", "#", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:140]


def score(line: str) -> int:
    s = 0
    if ERR.search(line):
        s += 6
    if WARN.search(line):
        s += 2
    if NUM.search(line):
        s += 1
    if PATH.search(line):
        s += 1
    if line.strip().startswith(("+", "-", "@@")):  # diff 行
        s += 2
    if len(line.strip()) < 3:
        s -= 3
    if PROGRESS.match(line):
        s -= 6
    return s


def load(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def compress(lines, budget_tokens, head_n, tail_n, max_line, keep_errors):
    # 1) 行内截断
    norm = []
    truncated = 0
    for ln in lines:
        if len(ln) > max_line:
            truncated += 1
            keep = max_line // 2
            ln = f"{ln[:keep]} …[截断 {len(ln) - max_line} 字符]… {ln[-keep // 2:]}"
        norm.append(ln.rstrip())

    # 2) 折叠连续重复
    folded, i = [], 0
    while i < len(norm):
        j = i
        while j + 1 < len(norm) and norm[j + 1] == norm[i]:
            j += 1
        n = j - i + 1
        if n >= 3 and norm[i].strip():
            folded.append((i, f"{norm[i]}    …[重复 ×{n}]…", n))
        else:
            for k in range(i, j + 1):
                folded.append((k, norm[k], 1))
        i = j + 1

    total = len(folded)
    head_n = min(head_n, total)
    tail_n = min(tail_n, total - head_n)
    keep = set(range(head_n)) | set(range(total - tail_n, total))

    # 2.5) 同型行折叠：签名相同且 ≥4 条时，只留第一条，其余丢弃
    buckets: dict[str, list[int]] = {}
    for idx, (_, line, _) in enumerate(folded):
        if line.strip() and not line.startswith("…["):
            buckets.setdefault(signature(line), []).append(idx)
    dropped: set[int] = set()
    same_kind: dict[int, int] = {}
    for idxs in buckets.values():
        if len(idxs) >= 4:
            n_drop = 0
            for i in idxs[1:]:
                if i in keep:      # 头尾行受保护，不折叠
                    continue
                dropped.add(i)
                n_drop += 1
            if n_drop:
                same_kind[idxs[0]] = n_drop
    keep -= dropped

    if keep_errors:
        for idx, (_, line, _) in enumerate(folded):
            if ERR.search(line) and idx not in dropped:
                keep.add(idx)

    used = sum(est_tokens(folded[i][1]) for i in keep)
    rest = [i for i in range(total) if i not in keep and i not in dropped]
    rest.sort(key=lambda i: score(folded[i][1]), reverse=True)

    for i in rest:
        t = est_tokens(folded[i][1])
        if used + t > budget_tokens:
            continue
        keep.add(i)
        used += t

    # 3) 还原顺序 + 省略标记
    out, skipped, cur_skip = [], 0, 0
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
            skipped += folded[i][2]
    if cur_skip:
        out.append(f"…[省略 {cur_skip} 行]…")

    return out, {
        "raw_lines": len(lines),
        "kept_lines": len(keep),
        "skipped_lines": skipped,
        "truncated_lines": truncated,
        "raw_tokens": est_tokens("\n".join(lines)),
        "out_tokens": est_tokens("\n".join(out)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="工具输出压缩")
    ap.add_argument("--file", default="-", help="输入文件，默认 stdin")
    ap.add_argument("--budget", type=int, default=1500, help="输出 token 预算")
    ap.add_argument("--head", type=int, default=12)
    ap.add_argument("--tail", type=int, default=8)
    ap.add_argument("--max-line", type=int, default=400)
    ap.add_argument("--keep-errors", action="store_true")
    ap.add_argument("--stats", action="store_true", help="只打印统计到 stderr")
    ap.add_argument("--out", help="结果写文件而不是 stdout")
    args = ap.parse_args()

    text = ANSI.sub("", load(args.file))
    lines = text.splitlines()
    out, st = compress(
        lines, args.budget, args.head, args.tail, args.max_line, args.keep_errors
    )
    body = "\n".join(out)

    if args.file not in ("-", None):
        body += f"\n…[原文 {args.file}，共 {st['raw_lines']} 行]…"

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(body + "\n")
    elif not args.stats:
        print(body)

    ratio = (1 - st["out_tokens"] / max(st["raw_tokens"], 1)) * 100
    print(
        f"[{st['raw_lines']:,} 行 → {st['kept_lines']:,} 行 | "
        f"{st['raw_tokens']:,} tk → {st['out_tokens']:,} tk | 省 {ratio:.0f}%]",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
