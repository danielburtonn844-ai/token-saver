"""目录索引卡：先给一张卡，再决定读哪几个文件。"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from .text import CJK, clean_ansi, est_tokens, looks_binary, read_text

__all__ = ["Entry", "build_card", "collect_files", "to_json"]

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".idea", ".vscode", ".cache", "target", ".next", "coverage", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", ".eggs",
}
BIN_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".tar", ".7z", ".exe", ".dll", ".so", ".dylib", ".class", ".pyc", ".woff",
    ".woff2", ".ttf", ".mp4", ".mp3", ".db", ".sqlite", ".whl", ".bin", ".o", ".a",
}
DOC_PREFIX = ("#", "//", "/*", "*", '"""', "'''", "--", ";", "%")


def _match(rel: str, patterns: list[str] | None) -> bool:
    import fnmatch
    if not patterns:
        return False
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(os.path.basename(rel), p)
               for p in patterns)


@dataclass
class Entry:
    path: str
    size: int
    lines: int
    tokens: int
    summary: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def collect_files(root: str, depth: int = 4, max_files: int = 120,
                  include: list[str] | None = None, exclude: list[str] | None = None):
    """返回 [(绝对路径, 相对路径, 大小)]，跳过二进制、隐藏目录和软链接。"""
    out = []
    root_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        d = dirpath.rstrip(os.sep).count(os.sep) - root_depth
        if d >= depth:
            dirnames[:] = []
        dirnames[:] = sorted(
            x for x in dirnames if x not in SKIP_DIRS and not x.startswith(".")
        )
        for fn in sorted(filenames):
            if fn.startswith(".") and fn not in (".env.example", ".gitignore", ".dockerignore"):
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, root)
            if os.path.islink(p):
                continue
            if os.path.splitext(fn)[1].lower() in BIN_EXT:
                continue
            if include and not _match(rel, include):
                continue
            if _match(rel, exclude):
                continue
            try:
                size = os.path.getsize(p)
                if size > 2 * 1024 * 1024:
                    continue
                with open(p, "rb") as fh:
                    if looks_binary(fh.read(2048)):
                        continue
            except OSError:
                continue
            out.append((p, rel, size))
            if len(out) >= max_files:
                return out
    return out


def _count_lines(path: str) -> int:
    n = 0
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                n += chunk.count(b"\n")
    except OSError:
        return 0
    return n


def _summary(path: str, encoding: str = "auto") -> str:
    """取前 80 行里第一句有意义的注释或代码，作为一行摘要。"""
    try:
        text, _, _ = read_text(path, 256 * 1024, encoding)
        lines = text.splitlines()[:80]
    except OSError:
        return ""
    for ln in lines:
        s = ln.strip()
        if s.startswith("description:"):
            return s.split(":", 1)[1].strip()[:110]
        if s in ("---", "") or s.startswith(("name:", "version:", "license:", "author:",
                                             "allowed-tools:", "title:", "date:")):
            continue
        cand = s
        for p in DOC_PREFIX:
            if cand.startswith(p):
                cand = cand[len(p):].strip()
                break
        # 中文 4 个字就够表达意思，英文至少要 8 个字符
        long_enough = len(cand) >= 8 or (len(cand) >= 4 and CJK.search(cand))
        if long_enough and not cand.startswith(("!", "-*-", "coding", "<")):
            return cand[:110]
    return ""


def _file_tokens(path: str, encoding: str = "auto") -> int:
    try:
        text, _, _ = read_text(path, 2 * 1024 * 1024, encoding)
        return est_tokens(clean_ansi(text))
    except OSError:
        return 0


def build_card(root: str, depth: int = 4, max_files: int = 120,
               include: list[str] | None = None, exclude: list[str] | None = None,
               encoding: str = "auto"):
    """生成索引卡。返回 (markdown, entries)。"""
    files = collect_files(root, depth, max_files, include, exclude)
    entries: list[Entry] = []
    for p, rel, size in files:
        entries.append(Entry(rel, size, _count_lines(p),
                             _file_tokens(p, encoding), _summary(p, encoding)))
    entries.sort(key=lambda e: e.tokens, reverse=True)

    total_tok = sum(e.tokens for e in entries)
    total_size = sum(e.size for e in entries)
    card_tok = est_tokens("".join(e.path + e.summary for e in entries))

    md = [
        f"# 索引卡：{os.path.abspath(root)}",
        "",
        f"- 文件数：{len(entries)}（上限 {max_files}）",
        f"- 总体积：{total_size / 1024:.0f} KB",
        f"- 全量估算：{total_tok:,} token",
        f"- 本卡估算：约 {card_tok:,} token（占全量 {card_tok / max(total_tok, 1) * 100:.1f}%）",
        "",
        "| 文件 | 行数 | token | 摘要 |",
        "|---|---:|---:|---|",
    ]
    for e in entries:
        desc = (e.summary or "—").replace("|", "\\|")
        md.append(f"| `{e.path}` | {e.lines} | {e.tokens:,} | {desc} |")
    return "\n".join(md) + "\n", entries


def to_json(root: str, entries: list[Entry]) -> str:
    return json.dumps(
        {
            "root": os.path.abspath(root),
            "files": [e.as_dict() for e in entries],
            "totals": {
                "files": len(entries),
                "bytes": sum(e.size for e in entries),
                "tokens": sum(e.tokens for e in entries),
            },
        },
        ensure_ascii=False,
        indent=2,
    )
