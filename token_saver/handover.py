"""跨会话交接单：生成、校验、展示。"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from .text import est_tokens, read_text

__all__ = ["DEFAULT_MAX_TOKENS", "Issue", "TEMPLATE", "check", "create"]

DEFAULT_MAX_TOKENS = 300
HARD_MAX_TOKENS = 400
REQUIRED = ["目标", "状态", "关键决策", "文件指针", "下一步"]
OPTIONAL = ["已排除"]

TEMPLATE = """# HANDOVER: <项目名>

> 更新：<YYYY-MM-DD HH:MM> · 预算：≤300 token

## 目标
<一句话说清这活要什么>

## 状态
- 已完成：<…>
- 进行中：<…>
- 卡点：<…>

## 关键决策
- <决策> —— 因为 <理由>

## 已排除
- <方案> —— 不行，因为 <原因>

## 文件指针
- 源码：`/path`
- 配置：`/path`
- 日志：`/path`

## 下一步
1. <具体动作>
2. <具体动作>
"""

HEADING = re.compile(r"^##\s+(.+?)\s*$", re.M)
PLACEHOLDER = re.compile(r"<[^<>\n]{0,80}>")


@dataclass
class Issue:
    level: str  # error / warn
    code: str
    message: str

    def as_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "message": self.message}


@dataclass
class Report:
    path: str = ""
    tokens: int = 0
    lines: int = 0
    issues: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.issues)

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "tokens": self.tokens,
            "lines": self.lines,
            "ok": self.ok,
            "issues": [i.as_dict() for i in self.issues],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2)


def create(path: str, force: bool = False, template: str | None = None) -> int:
    """新建交接单；已存在且未 force 时返回 1。"""
    if os.path.exists(path) and not force:
        return 1
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(template if template is not None else TEMPLATE)
    return 0


def _section_bodies(text: str) -> dict:
    bodies: dict = {}
    matches = list(HEADING.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        bodies[m.group(1).strip()] = text[m.end():end]
    return bodies


def _meaningful(body: str) -> int:
    """统计除去占位符后的有效行数。"""
    n = 0
    for ln in body.splitlines():
        s = ln.strip()
        if not s or s.startswith(">"):
            continue
        if PLACEHOLDER.sub("", s).strip(" -:：`*") == "":
            continue
        n += 1
    return n


def check(path: str, max_tokens: int = DEFAULT_MAX_TOKENS,
          encoding: str = "auto") -> Report:
    """校验交接单，返回结构化报告。"""
    text, _, _ = read_text(path, encoding=encoding)
    headings = [h.strip() for h in HEADING.findall(text)]
    bodies = _section_bodies(text)
    report = Report(path=path, tokens=est_tokens(text), lines=len(text.splitlines()))

    missing = [s for s in REQUIRED if not any(s in h for h in headings)]
    if missing:
        report.issues.append(Issue("error", "missing-sections", f"缺少段落：{', '.join(missing)}"))

    seen = set()
    dups = [h for h in headings if h in seen or seen.add(h)]
    if dups:
        report.issues.append(Issue("error", "duplicate-sections", f"重复段落：{', '.join(dups)}"))

    empty = []
    for want in REQUIRED:
        key = next((h for h in headings if want in h), None)
        if key is not None and _meaningful(bodies.get(key, "")) == 0:
            empty.append(want)
    if empty:
        report.issues.append(Issue("error", "empty-sections", f"未填写段落：{', '.join(empty)}"))

    leftovers = PLACEHOLDER.findall(text)
    if leftovers:
        sample = " ".join(dict.fromkeys(leftovers))[:120]
        report.issues.append(Issue("warn", "placeholders", f"仍有占位符：{sample}"))

    if report.tokens > HARD_MAX_TOKENS:
        report.issues.append(Issue("error", "too-long",
                                   f"超长：{report.tokens} token（上限 {HARD_MAX_TOKENS}）"))
    elif report.tokens > max_tokens:
        report.issues.append(Issue("warn", "over-budget",
                                   f"超出建议：{report.tokens} token（建议 ≤{max_tokens}）"))

    known = REQUIRED + OPTIONAL
    unknown = [h for h in headings if not any(k in h for k in known)]
    if unknown:
        report.issues.append(Issue("warn", "unknown-sections", f"非标准段落：{', '.join(unknown)}"))
    return report
