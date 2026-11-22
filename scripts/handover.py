#!/usr/bin/env python3
"""handover.py — 跨会话交接单的生成 / 校验 / 读取。

用法：
    python3 handover.py new   /path/HANDOVER.md
    python3 handover.py check /path/HANDOVER.md      # 缺段/超长会报错
    python3 handover.py show  /path/HANDOVER.md      # 打印，带 token 估算
"""
import os
import re
import sys

SECTIONS = ["目标", "状态", "关键决策", "文件指针", "下一步"]
CJK = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")

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


def est_tokens(s: str) -> int:
    cjk = len(CJK.findall(s))
    return int(cjk * 0.6 + (len(s) - cjk) * 0.25) + 1


def cmd_new(path: str) -> int:
    if os.path.exists(path):
        print(f"已存在，不覆盖：{path}", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(TEMPLATE)
    print(f"已创建：{path}")
    return 0


def cmd_check(path: str) -> int:
    text = open(path, encoding="utf-8").read()
    headings = re.findall(r"^##\s+(.+?)\s*$", text, re.M)
    missing = [s for s in SECTIONS if not any(s in h for h in headings)]
    tokens = est_tokens(text)
    ok = True
    if missing:
        print(f"缺少段落：{', '.join(missing)}")
        ok = False
    empty = [h for h in headings if len(re.sub(r"^##.*$", "", h)) > 0 and _section_body(text, h) == 0]
    if empty:
        print(f"未填写段落：{', '.join(empty)}")
        ok = False
    if tokens > 400:
        print(f"超长：{tokens} token（建议 ≤300，上限 400）")
        ok = False
    print(f"{'通过' if ok else '未通过'}：{tokens} token / {len(text.splitlines())} 行")
    return 0 if ok else 1


def _section_body(text: str, heading: str) -> int:
    m = re.search(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    if not m:
        return 0
    return len([ln for ln in m.group(1).splitlines() if ln.strip() and not ln.strip().startswith("<")])


def cmd_show(path: str) -> int:
    text = open(path, encoding="utf-8").read()
    print(text)
    print(f"---\n[估算 {est_tokens(text)} token / {len(text.splitlines())} 行]", file=sys.stderr)
    return 0


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in ("new", "check", "show"):
        print(__doc__)
        return 2
    cmd, path = sys.argv[1], sys.argv[2]
    return {"new": cmd_new, "check": cmd_check, "show": cmd_show}[cmd](path)


if __name__ == "__main__":
    raise SystemExit(main())
