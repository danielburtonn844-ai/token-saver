# 参与贡献

## 环境

- Python 3.9+（CI 覆盖 3.9–3.13）
- Bash（安装脚本测试用；Windows 会跳过这部分）
- 不需要任何运行时依赖

```bash
git clone https://github.com/danielburtonn844-ai/token-saver.git
cd token-saver
python -m unittest discover -s tests -t .   # 130 项，约 30 秒
```

可选：

```bash
pip install pytest ruff tiktoken
python -m pytest -q
python -m ruff check .
python bench/calibrate.py    # 重新校准 token 系数（需要 tiktoken）
```

## 改动前先跑基准

压缩算法、估算系数、识别规则的任何改动，都要给出前后对比：

```bash
python bench/bench.py
python bench/calibrate.py
```

关注四项：压缩比、错误签名召回、保真检查、耗时。任何一项退化都要在 PR 里说明原因。

## 代码约定

- 核心包 `token_saver/` 只用标准库；第三方依赖只允许出现在 `bench/` 且必须可选
- 逻辑写在包里，`scripts/*.py` 只做薄封装
- 中文注释与文档，变量名用英文
- 新功能必须带测试；修 bug 先补一个会失败的测试
- 输出面向人读，错误信息说清楚「什么不行 + 怎么办」

## 提交

```
<type>: <一句话>
```

type 用 `feat` / `fix` / `perf` / `docs` / `test` / `refactor` / `chore`。

## 版本

改版本号要同时改三处：`token_saver/__init__.py`、`pyproject.toml`、`SKILL.md` 的 frontmatter，并在 `CHANGELOG.md` 加一节。`tests/test_packaging.py` 会检查一致性。

## 行为准则

见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。
