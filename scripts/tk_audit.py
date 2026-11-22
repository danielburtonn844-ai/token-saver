#!/usr/bin/env python3
"""tk_audit.py — 给文件/目录/标准输入做 token 体检，找出「搬运型」浪费。

用法：
    python3 tk_audit.py FILE [FILE...]
    python3 tk_audit.py --dir /path/to/project --top 15
    cat session.jsonl | python3 tk_audit.py -
    python3 tk_audit.py --json FILE

只做估算与提示，不做判断。估算误差通常 ±15%，足以支撑「省不省」的决策。
"""
import argparse
import json
import os
import re
import sys

CJK = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")
PROGRESS = re.compile(r"^\s*\[[=>#\-\s.]*\]\s*\d{0,3}%?\s*$|^\s*\d{1,3}%\s*[|#=]")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def est_tokens(text: str) -> int:
    """中英混合粗估：CJK 0.6 token/字，其余 0.25 token/字符。"""
    cjk = len(CJK.findall(text))
    other = len(text) - cjk
    return int(cjk * 0.6 + other * 0.25) + 1


def read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def audit_text(name: str, text: str, top: int) -> dict:
    text = ANSI.sub("", text)
    lines = text.splitlines()
    n_lines = len(lines)
    n_chars = len(text)
    tokens = est_tokens(text)

    blank = sum(1 for ln in lines if not ln.strip())
    long_lines = [ln for ln in lines if len(ln) > 500]
    progress = sum(1 for ln in lines if PROGRESS.match(ln))

    seen, dup_lines, dup_chars = set(), 0, 0
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s in seen:
            dup_lines += 1
            dup_chars += len(ln)
        else:
            seen.add(s)

    # 段落（空行分隔）作为「大块」单位，找最占地方的段落
    blocks, cur = [], []
    for ln in lines:
        if ln.strip():
            cur.append(ln)
        elif cur:
            blocks.append("\n".join(cur))
            cur = []
    if cur:
        blocks.append("\n".join(cur))
    blocks.sort(key=len, reverse=True)

    waste_chars = dup_chars + sum(len(ln) for ln in long_lines) // 2 + blank
    return {
        "name": name,
        "lines": n_lines,
        "chars": n_chars,
        "tokens": tokens,
        "blank_lines": blank,
        "dup_lines": dup_lines,
        "dup_chars": dup_chars,
        "long_lines": len(long_lines),
        "progress_lines": progress,
        "est_waste_tokens": est_tokens("x" * waste_chars) if waste_chars else 0,
        "top_blocks": [
            {"chars": len(b), "tokens": est_tokens(b), "head": b.splitlines()[0][:80]}
            for b in blocks[:top]
        ],
    }


def render(r: dict) -> str:
    out = []
    out.append(f"文件: {r['name']}")
    out.append(f"  行数 {r['lines']:,} | 字符 {r['chars']:,} | 估算 {r['tokens']:,} token")
    out.append(
        f"  空行 {r['blank_lines']:,} | 重复行 {r['dup_lines']:,} | "
        f"超长行 {r['long_lines']:,} | 进度条行 {r['progress_lines']:,}"
    )
    if r["tokens"]:
        pct = r["est_waste_tokens"] / max(r["tokens"], 1) * 100
        out.append(f"  可压缩估算 {r['est_waste_tokens']:,} token（≈{pct:.0f}%）")
    if r["top_blocks"]:
        out.append("  最大块:")
        for b in r["top_blocks"]:
            out.append(f"    {b['tokens']:>8,} tk  {b['head']}")
    return "\n".join(out)


def iter_files(root: str, max_files: int):
    skip = {".git", "node_modules", "__pycache__", ".venv", "dist", "build", ".idea"}
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".cache")]
        for fn in sorted(filenames):
            p = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(p) > 5 * 1024 * 1024:
                    continue
            except OSError:
                continue
            yield p
            count += 1
            if count >= max_files:
                return


def main() -> int:
    ap = argparse.ArgumentParser(description="token 体检")
    ap.add_argument("paths", nargs="*", help="文件路径，- 表示 stdin")
    ap.add_argument("--dir", help="目录递归体检")
    ap.add_argument("--top", type=int, default=5, help="每文件列出几个最大块")
    ap.add_argument("--max-files", type=int, default=200)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    targets = list(args.paths)
    if args.dir:
        targets += list(iter_files(args.dir, args.max_files))
    if not targets:
        ap.print_help()
        return 2

    reports = []
    for t in targets:
        try:
            reports.append(audit_text(t, read_text(t), args.top))
        except Exception as e:  # noqa: BLE001
            print(f"跳过 {t}: {e}", file=sys.stderr)

    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        return 0

    total = 0
    for r in reports:
        print(render(r))
        print()
        total += r["tokens"]
    print(f"合计: {len(reports)} 个文件 / 估算 {total:,} token")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
