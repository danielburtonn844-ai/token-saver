"""用 tiktoken 校准 token 估算系数，并给出误差分布。

    python3 bench/calibrate.py            # 需要 pip install tiktoken

三特征模型：CJK 字 / 字母与空格 / 数字与符号。过原点最小二乘拟合，
训练集与测试集各占一半，避免用同一批数据既拟合又打分。
没有 tiktoken 时会明确报错退出，不会伪造数据。
"""
from __future__ import annotations

import glob
import json
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import corpus  # noqa: E402

from token_saver.text import (  # noqa: E402
    CJK,
    CJK_PUNCT,
    CJK_WEIGHT,
    DIGIT,
    LATIN_WEIGHT,
    NONWORD,
    SYMBOL_WEIGHT,
)

try:
    import tiktoken
except ImportError:  # pragma: no cover
    print("缺少 tiktoken：pip install tiktoken", file=sys.stderr)
    raise SystemExit(2)

ENC = tiktoken.get_encoding("cl100k_base")


def features(text):
    """返回 (cjk, other, symbol) 三类字符数。"""
    cjk = len(CJK.findall(text))
    cjk_punct = len(CJK_PUNCT.findall(text))
    symbols = len(NONWORD.findall(text)) - cjk_punct + len(DIGIT.findall(text))
    return cjk, len(text) - cjk - symbols, symbols


def load_samples():
    samples = []
    patterns = ["README.md", "SKILL.md", "CHEATSHEET.md", "references/*.md",
                "scripts/*.py", "token_saver/*.py", "tests/*.py"]
    for pat in patterns:
        for path in sorted(glob.glob(os.path.join(ROOT, pat))):
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            if text.strip():
                samples.append((os.path.relpath(path, ROOT), text))

    # 英文代码（标准库）作为「纯英文」样本
    rnd = random.Random(20261123)
    stdlib = sorted(glob.glob(os.path.join(os.path.dirname(os.__file__), "*.py")))
    for path in rnd.sample(stdlib, min(8, len(stdlib))):
        with open(path, encoding="utf-8", errors="replace") as fh:
            samples.append((os.path.basename(path), fh.read()[:40000]))

    # 合成语料，覆盖日志/JSON/中文/堆栈
    for name in corpus.CORPORA:
        lines = corpus.get(name)
        samples.append(("corpus:" + name, "\n".join(lines[:3000])))
    return samples


def solve(matrix, vec):
    """高斯消元解小型线性方程组。"""
    n = len(matrix)
    m = [row[:] + [vec[i]] for i, row in enumerate(matrix)]
    for i in range(n):
        pivot = max(range(i, n), key=lambda r: abs(m[r][i]))
        m[i], m[pivot] = m[pivot], m[i]
        if abs(m[i][i]) < 1e-12:
            return None
        for r in range(i + 1, n):
            f = m[r][i] / m[i][i]
            for k in range(i, n + 1):
                m[r][k] -= f * m[i][k]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
    return x


def fit(samples):
    """最小二乘拟合 t ≈ a*cjk + b*other + d*symbol。"""
    a = [[0.0] * 3 for _ in range(3)]
    b = [0.0] * 3
    for _, text in samples:
        f = features(text)
        y = len(ENC.encode(text, disallowed_special=()))
        for i in range(3):
            b[i] += f[i] * y
            for j in range(3):
                a[i][j] += f[i] * f[j]
    coef = solve(a, b)
    if not coef:
        return (CJK_WEIGHT, LATIN_WEIGHT, SYMBOL_WEIGHT)
    return tuple(max(0.0001, c) for c in coef)


def errors(samples, weights):
    out = []
    for name, text in samples:
        c, o, s = features(text)
        est = c * weights[0] + o * weights[1] + s * weights[2] + 1
        real = len(ENC.encode(text, disallowed_special=()))
        if real:
            out.append((name, abs(est - real) / real))
    return out


def summarize(values):
    vals = sorted(v for _, v in values)
    return {
        "p50": round(statistics.median(vals) * 100, 2),
        "p90": round(vals[max(0, int(len(vals) * 0.9) - 1)] * 100, 2),
        "max": round(vals[-1] * 100, 2),
        "mean": round(statistics.fmean(vals) * 100, 2),
    }


def main():
    samples = load_samples()
    rnd = random.Random(7)
    rnd.shuffle(samples)
    cut = max(1, len(samples) // 2)
    train, test = samples[:cut], samples[cut:]

    fitted = fit(train)
    current = (CJK_WEIGHT, LATIN_WEIGHT, SYMBOL_WEIGHT)

    summary = {
        "samples": len(samples),
        "train": len(train),
        "test": len(test),
        "current": {"weights": dict(zip(("cjk", "other", "symbol"), current)),
                    "test": summarize(errors(test, current)),
                    "all": summarize(errors(samples, current))},
        "fitted": {"weights": dict(zip(("cjk", "other", "symbol"), [round(x, 4) for x in fitted])),
                   "test": summarize(errors(test, fitted)),
                   "all": summarize(errors(samples, fitted))},
    }

    rows = []
    for name, text in test[:12]:
        c, o, s = features(text)
        real = len(ENC.encode(text, disallowed_special=()))
        est = int(c * current[0] + o * current[1] + s * current[2] + 1)
        rows.append((name[:40], len(text), c, real, est,
                     round(abs(est - real) / max(real, 1) * 100, 1)))

    md = ["# 估算系数校准（cl100k_base）", "",
          f"样本 {len(samples)} 份：仓库文档与代码、标准库 Python、7 类合成日志。"
          f"训练 {len(train)} / 测试 {len(test)}，随机种子固定。", "",
          "| 系数 | CJK | 字母空格 | 数字符号 | 测试集中位误差 | p90 | 最大 | 全样本中位误差 |",
          "|---|---:|---:|---:|---:|---:|---:|---:|",
          f"| 现用 | {current[0]} | {current[1]} | {current[2]} | "
          f"{summary['current']['test']['p50']}% | {summary['current']['test']['p90']}% | "
          f"{summary['current']['test']['max']}% | {summary['current']['all']['p50']}% |",
          f"| 重拟合 | {fitted[0]:.3f} | {fitted[1]:.3f} | {fitted[2]:.3f} | "
          f"{summary['fitted']['test']['p50']}% | {summary['fitted']['test']['p90']}% | "
          f"{summary['fitted']['test']['max']}% | {summary['fitted']['all']['p50']}% |",
          "", "## 测试集抽样", "",
          "| 样本 | 字符 | CJK | 真实 tk | 估算 tk | 误差 |",
          "|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        md.append("| `%s` | %d | %d | %d | %d | %.1f%% |" % row)

    with open(os.path.join(HERE, "CALIBRATION.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    with open(os.path.join(HERE, "calibration.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
