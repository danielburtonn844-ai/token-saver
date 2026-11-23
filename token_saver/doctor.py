"""环境自检：装没装、能不能写、入口有没有内核块、版本是否一致。"""
from __future__ import annotations

import json
import os
import shutil
import sys

from . import __version__
from .text import est_tokens

__all__ = ["run", "render"]

BEGIN = "<!-- token-saver:core:begin -->"
END = "<!-- token-saver:core:end -->"

TARGETS = {
    "minis": ("/var/minis/skills/token-saver", "/var/minis/memory/GLOBAL.md"),
    "claude": ("~/.claude/skills/token-saver", "~/.claude/CLAUDE.md"),
    "codex": ("~/.codex/token-saver", "~/.codex/AGENTS.md"),
    "project": ("<cwd>/skills/token-saver", "<cwd>/AGENTS.md"),
}


def _expand(path: str) -> str:
    return os.path.expanduser(path.replace("<cwd>", os.getcwd()))


def _check(name: str, ok: bool, detail: str, hint: str = "", level: str = "error") -> dict:
    """level=error 时失败会让整体不通过；level=warn 只提示。"""
    return {"name": name, "ok": ok, "detail": detail, "hint": hint, "level": level}


def run() -> dict:
    checks = []
    py = "%d.%d.%d" % sys.version_info[:3]
    checks.append(_check("python", sys.version_info >= (3, 9), f"Python {py}",
                         "需要 Python 3.9 及以上"))
    checks.append(_check("version", True, f"token-saver {__version__}"))

    installer = shutil.which("tk") or ""
    checks.append(_check("tk-on-path", bool(installer), installer or "未找到 tk",
                         "pip install . 或把 scripts/ 加进 PATH", level="warn"))

    for target, (skill, entry) in TARGETS.items():
        skill_p, entry_p = _expand(skill), _expand(entry)
        installed = os.path.isfile(os.path.join(skill_p, "SKILL.md"))
        if not installed:
            continue
        text = ""
        if os.path.isfile(entry_p):
            with open(entry_p, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        has_core = BEGIN in text and END in text
        checks.append(_check(f"install:{target}", has_core,
                             f"技能已装，内核块{'已' if has_core else '缺'}注入",
                             f"bash scripts/install.sh --target {target}"))

    core = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "templates", "AGENTS.core.md")
    if os.path.isfile(core):
        with open(core, encoding="utf-8") as fh:
            checks.append(_check("core-size", True,
                                 f"常驻内核约 {est_tokens(fh.read())} token"))
    ok = all(c["ok"] or c["level"] == "warn" for c in checks)
    return {"version": __version__, "python": py, "ok": ok, "checks": checks}


def render(result: dict) -> str:
    lines = [f"token-saver {result['version']} · Python {result['python']}", ""]
    for c in result["checks"]:
        mark = "OK  " if c["ok"] else ("WARN" if c["level"] == "warn" else "FAIL")
        lines.append(f"[{mark}] {c['name']}: {c['detail']}")
        if not c["ok"] and c["hint"]:
            lines.append(f"        → {c['hint']}")
    lines.append("")
    lines.append("全部通过" if result["ok"] else "存在问题，按提示修复")
    return "\n".join(lines)


def dumps(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
