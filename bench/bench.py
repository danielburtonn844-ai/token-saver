"""跑基准：压缩比、错误召回、内容保真、耗时。

    python3 bench/bench.py                # 跑全部语料
    python3 bench/bench.py --only build_log
    python3 bench/bench.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import corpus  # noqa: E402

from token_saver import __version__  # noqa: E402
from token_saver.compress import ERR, compress, signature  # noqa: E402
from token_saver.text import est_tokens  # noqa: E402

MARKER = re.compile(r"…\[")


def distinct_errors(lines):
    """返回 {签名: 代表行}，用于衡量「错误种类」是否都保留。"""
    seen = {}
    for ln in lines:
        if ERR.search(ln):
            seen.setdefault(signature(ln), ln)
    return seen


def error_recall(text, errors):
    """按错误签名计算召回：同一类错误保留一个样本即算命中。"""
    if not errors:
        return 1.0
    out_sigs = {signature(ln) for ln in text.splitlines()}
    hit = sum(1 for sig in errors if sig in out_sigs)
    return hit / len(errors)


def line_recall(text, lines):
    """按具体错误行计算召回（同型折叠会拉低这个值，属预期）。无错误行返回 None。"""
    errs = [ln for ln in lines if ERR.search(ln)]
    if not errs:
        return None
    return sum(1 for ln in errs if ln in text) / len(errs)


def fabricated(text, lines):
    """检查输出是否凭空造了原文没有的内容（省略标记与截断行除外）。"""
    source = "\n".join(lines)
    bad = []
    for ln in text.splitlines():
        if not ln.strip() or MARKER.search(ln):
            continue
        base = ln
        if "[截断" in base:
            base = base.split(" …[截断")[0]
        if "…[重复" in base or "…[同型" in base:
            base = base.split("    …[")[0]
        if base and base not in source:
            bad.append(ln[:80])
    return bad


def run_one(name, lines, budgets):
    raw_tokens = est_tokens("\n".join(lines))
    raw_bytes = len("\n".join(lines).encode("utf-8"))
    errors = distinct_errors(lines)
    rows = []
    for budget in budgets:
        start = time.perf_counter()
        result = compress(lines, budget=budget)
        elapsed = time.perf_counter() - start
        text = result.text
        rows.append({
            "budget": budget,
            "out_tokens": result.stats.out_tokens,
            "ratio": round(result.stats.ratio, 4),
            "error_recall": round(error_recall(text, errors), 4),
            "line_recall": (None if line_recall(text, lines) is None
                            else round(line_recall(text, lines), 4)),
            "over_budget": result.stats.over_budget,
            "seconds": round(elapsed, 3),
            "mb_per_s": round(raw_bytes / 1e6 / max(elapsed, 1e-9), 2),
            "kept_lines": result.stats.kept_lines,
            "fabricated": fabricated(text, lines)[:3],
        })
    return {"corpus": name, "lines": len(lines), "bytes": raw_bytes,
            "raw_tokens": raw_tokens, "distinct_errors": len(errors), "rows": rows}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--budgets", default="300,800,1500")
    ap.add_argument("--json", dest="json_out", default=os.path.join(HERE, "results.json"))
    ap.add_argument("--markdown", default=os.path.join(HERE, "RESULTS.md"))
    args = ap.parse_args(argv)

    budgets = [int(b) for b in args.budgets.split(",")]
    names = args.only or list(corpus.CORPORA)
    results = []
    for name in names:
        lines = corpus.get(name)
        print(f"[{name}] {len(lines):,} 行 …", file=sys.stderr)
        results.append(run_one(name, lines, budgets))

    payload = {
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "budgets": budgets,
        "results": results,
    }
    with open(args.json_out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    md = [f"# 基准结果（token-saver {__version__}）", "",
          f"- 环境：Python {platform.python_version()} · {platform.machine()} · {platform.system()}",
          "- 语料：固定种子生成，见 `bench/corpus.py`；重跑命令 `python3 bench/bench.py`",
          "- 估算口径：`token_saver.text.est_tokens`（cl100k 校准，见 `bench/CALIBRATION.md`）",
          "- 错误召回按「错误签名」计：同型重复的错误折叠成一个样本 + 次数，即视为未丢失",
          "- 窗口召回（line_recall）记录具体错误行保留比例，供参考",
          "",
          "| 语料 | 行数 | 原始 tk | 预算 | 输出 tk | 压缩 | 错误签名召回 | 行召回 | 超预算 | 耗时 | 吞吐 |",
          "|---|---:|---:|---:|---:|---:|---:|---:|:--:|---:|---:|"]
    for r in results:
        for row in r["rows"]:
            md.append(
                f"| {r['corpus']} | {r['lines']:,} | {r['raw_tokens']:,} | {row['budget']} | "
                f"{row['out_tokens']:,} | {row['ratio'] * 100:.1f}% | "
                f"{row['error_recall'] * 100:.1f}% | "
              f"{'—' if row['line_recall'] is None else str(round(row['line_recall'] * 100, 1)) + '%'} | "
                f"{'是' if row['over_budget'] else '否'} | "
                f"{row['seconds']:.2f}s | {row['mb_per_s']:.0f} MB/s |"
            )
    fab = [(r["corpus"], row["budget"], row["fabricated"]) for r in results
           for row in r["rows"] if row["fabricated"]]
    md += ["", "## 保真检查", "",
           "输出中不允许出现原文没有的行。检查结果：" +
           ("全部通过" if not fab else "存在可疑行，见下"), ""]
    for name, budget, bad in fab:
        md.append(f"- `{name}` budget={budget}: {bad}")
    with open(args.markdown, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
