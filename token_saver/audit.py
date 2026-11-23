"""token 体检：指出哪些内容属于「搬运型」浪费。

只做估算与提示，不做判断；估算系数与 compress 共用 text.py，口径一致。
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import asdict, dataclass, field

from .text import CJK_WEIGHT, LATIN_WEIGHT, clean_ansi, est_tokens, looks_binary

__all__ = ["FileReport", "audit_text", "iter_files", "render", "render_totals", "report_to_json"]

PROGRESS_RE = re.compile(r"^\s*\[[=>#\-\s.]*\]\s*\d{0,3}%?\s*$|^\s*\d{1,3}%\s*[|#=]")
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".idea", ".vscode", ".cache", "target", ".next", "coverage", ".pytest_cache",
}
LONG_LINE = 500


@dataclass
class FileReport:
    name: str = ""
    lines: int = 0
    chars: int = 0
    tokens: int = 0
    blank_lines: int = 0
    dup_lines: int = 0
    dup_chars: int = 0
    long_lines: int = 0
    progress_lines: int = 0
    est_waste_tokens: int = 0
    top_blocks: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def audit_text(name: str, text: str, top: int = 5) -> FileReport:
    """体检一段文本。空文本返回全零报告。"""
    text = clean_ansi(text)
    lines = text.splitlines()
    report = FileReport(
        name=name,
        lines=len(lines),
        chars=len(text),
        tokens=est_tokens(text),
        blank_lines=sum(1 for ln in lines if not ln.strip()),
        long_lines=sum(1 for ln in lines if len(ln) > LONG_LINE),
        progress_lines=sum(1 for ln in lines if PROGRESS_RE.match(ln)),
    )

    seen: set = set()
    dup_text: list[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s in seen:
            report.dup_lines += 1
            report.dup_chars += len(ln)
            dup_text.append(ln)
        else:
            seen.add(s)

    # 段落（空行分隔）作为大块单位
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

    # 浪费 = 重复行全文 + 超长行超出 500 字的部分 + 空行的换行成本
    overflow = sum(len(ln) - LONG_LINE for ln in lines if len(ln) > LONG_LINE)
    waste = est_tokens("\n".join(dup_text)) if dup_text else 0
    waste += int(overflow * LATIN_WEIGHT)
    waste += int(report.blank_lines * LATIN_WEIGHT)
    report.est_waste_tokens = max(0, waste)

    if top > 0:
        report.top_blocks = [
            {"chars": len(b), "tokens": est_tokens(b), "head": b.splitlines()[0][:80]}
            for b in blocks[:top]
        ]
    return report


def _match(name: str, patterns: list[str] | None) -> bool:
    if not patterns:
        return False
    base = os.path.basename(name)
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(base, p) for p in patterns)


def iter_files(root: str, max_files: int = 200, exclude: list[str] | None = None,
               exts: list[str] | None = None):
    """递归列出可体检的文本文件，跳过二进制、软链接与大文件。"""
    count = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".cache")
        )
        for fn in sorted(filenames):
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, root)
            if _match(rel, exclude):
                continue
            if exts and os.path.splitext(fn)[1].lower().lstrip(".") not in exts:
                continue
            try:
                if os.path.getsize(p) > 5 * 1024 * 1024 or os.path.islink(p):
                    continue
                with open(p, "rb") as fh:
                    if looks_binary(fh.read(2048)):
                        continue
            except OSError:
                continue
            yield p
            count += 1
            if count >= max_files:
                return


def render(r: FileReport) -> str:
    out = [f"文件: {r.name}"]
    out.append(f"  行数 {r.lines:,} | 字符 {r.chars:,} | 估算 {r.tokens:,} token")
    out.append(
        f"  空行 {r.blank_lines:,} | 重复行 {r.dup_lines:,} | "
        f"超长行 {r.long_lines:,} | 进度条行 {r.progress_lines:,}"
    )
    if r.tokens:
        pct = r.est_waste_tokens / max(r.tokens, 1) * 100
        out.append(f"  可压缩估算 {r.est_waste_tokens:,} token（≈{pct:.0f}%）")
    if r.top_blocks:
        out.append("  最大块:")
        for b in r.top_blocks:
            out.append(f"    {b['tokens']:>8,} tk  {b['head']}")
    return "\n".join(out)


def render_totals(reports: list[FileReport]) -> str:
    total = sum(r.tokens for r in reports)
    waste = sum(r.est_waste_tokens for r in reports)
    pct = waste / max(total, 1) * 100
    return (f"合计: {len(reports)} 个文件 / 估算 {total:,} token / "
            f"可压缩 {waste:,} token（≈{pct:.0f}%）")


def report_to_json(reports: list[FileReport]) -> str:
    payload = {
        "files": [r.as_dict() for r in reports],
        "totals": {
            "files": len(reports),
            "tokens": sum(r.tokens for r in reports),
            "waste_tokens": sum(r.est_waste_tokens for r in reports),
            "lines": sum(r.lines for r in reports),
        },
        "estimator": {"cjk_weight": CJK_WEIGHT, "latin_weight": LATIN_WEIGHT},
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
