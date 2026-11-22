#!/usr/bin/env python3
"""ctx_pack.py — 给一个目录生成「索引卡」，用于渐进式披露（先看卡，再决定读哪个）。

用法：
    python3 ctx_pack.py /path/to/project                 # 打印 markdown
    python3 ctx_pack.py /path/to/project -o INDEX.md
    python3 ctx_pack.py /path/to/project --max-files 80 --depth 3

索引卡 = 文件清单 + 每个文件一行摘要 + token 估算。通常占总代码量的 3~5%，
却足以让你决定「该读哪几个文件」。
"""
import argparse
import os
import re
import sys

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".idea", ".vscode", ".cache", "target", ".next", "coverage", ".pytest_cache",
}
BIN_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".tar", ".7z", ".exe", ".dll", ".so", ".dylib", ".class", ".pyc", ".woff",
    ".woff2", ".ttf", ".mp4", ".mp3", ".db", ".sqlite", ".whl",
}
CJK = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")
DOC = re.compile(r'^\s*(?:#|//|/\*|\*|"""|\'\'\')\s*(.+)$')


def est_tokens(s: str) -> int:
    cjk = len(CJK.findall(s))
    return int(cjk * 0.6 + (len(s) - cjk) * 0.25) + 1


def count_lines(path: str) -> int:
    n = 0
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                n += chunk.count(b"\n")
    except OSError:
        return 0
    return n


def summary_line(path: str) -> tuple[str, int]:
    """返回（摘要, 行数）。读最多前 80 行找第一句有意义的注释/代码。"""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[:80]
    except OSError:
        return "", 0
    for ln in lines:
        s = ln.strip()
        if s.startswith("description:"):          # SKILL.md 这类 frontmatter
            return s.split(":", 1)[1].strip()[:110], count_lines(path)
        if s in ("---", "") or s.startswith(("name:", "version:", "license:", "author:", "allowed-tools:")):
            continue
        m = DOC.match(ln)
        cand = (m.group(1) if m else ln).strip()
        if len(cand) >= 8 and not cand.startswith(("!", "-*-", "coding")):
            return cand[:110], count_lines(path)
    return "", count_lines(path)


def walk(root: str, depth: int, max_files: int):
    out = []
    root_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        d = dirpath.rstrip(os.sep).count(os.sep) - root_depth
        if d >= depth:
            dirnames[:] = []
        dirnames[:] = sorted(x for x in dirnames if x not in SKIP_DIRS and not x.startswith("."))
        for fn in sorted(filenames):
            if fn.startswith(".") and fn not in (".env.example", ".gitignore"):
                continue
            p = os.path.join(dirpath, fn)
            if os.path.splitext(fn)[1].lower() in BIN_EXT:
                continue
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            if size > 2 * 1024 * 1024:
                continue
            out.append((p, size))
            if len(out) >= max_files:
                return out
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="目录索引卡")
    ap.add_argument("root")
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--max-files", type=int, default=120)
    ap.add_argument("-o", "--out")
    args = ap.parse_args()

    files = walk(args.root, args.depth, args.max_files)
    rows, total_tok, total_size = [], 0, 0
    for p, size in files:
        rel = os.path.relpath(p, args.root)
        line, n_lines = summary_line(p)
        try:
            tok = est_tokens(open(p, encoding="utf-8", errors="ignore").read())
        except OSError:
            tok = 0
        total_tok += tok
        total_size += size
        rows.append((rel, size, n_lines, tok, line))

    rows.sort(key=lambda r: r[3], reverse=True)
    md = [
        f"# 索引卡：{os.path.abspath(args.root)}",
        "",
        f"- 文件数：{len(rows)}（上限 {args.max_files}）",
        f"- 总体积：{total_size / 1024:.0f} KB",
        f"- 全量估算：{total_tok:,} token",
        f"- 本卡估算：约 {est_tokens(''.join(r[0] + r[4] for r in rows)):,} token",
        "",
        "| 文件 | 行数 | token | 摘要 |",
        "|---|---:|---:|---|",
    ]
    for rel, size, n_lines, tok, line in rows:
        desc = (line or "—").replace("|", "\\|")
        md.append(f"| `{rel}` | {n_lines} | {tok:,} | {desc} |")
    body = "\n".join(md) + "\n"

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(body)
        print(f"已写入 {args.out}（{est_tokens(body):,} token / {len(rows)} 文件）", file=sys.stderr)
    else:
        print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
