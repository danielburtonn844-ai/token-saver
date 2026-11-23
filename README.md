<div align="center">

# token-saver

**省 token 的作业规范与配套工具**

版本 `v2.1.1` · Python 3.9+ · 零第三方依赖

[![CI](https://github.com/danielburtonn844-ai/token-saver/actions/workflows/ci.yml/badge.svg)](https://github.com/danielburtonn844-ai/token-saver/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)

<br>

作者 **[ @fenghaogou ](https://t.me/fenghaogou)** &nbsp;·&nbsp; 频道 **[ @TvT_GG ](https://t.me/TvT_GG)**

</div>

---

## 这是什么

一套给 AI 编程助手用的作业规范，加一套处理文本的命令行工具。

解决三个具体问题：长会话越跑越贵、工具输出把上下文塞满、换个会话就得从头讲一遍。

仓库给出的答案：**三条常驻规则 + 四个命令行工具 + 六篇可复现基准**。可以挂到 Claude Code、Codex、Minis 这类环境里，每次开新会话自动带上。

```
压缩 12 万行构建日志：3,613,333 tk → 1,219 tk（99.97%）
错误签名召回：100%（同类错误折叠成一个样本 + 次数）
token 估算误差：中位 4.9%，p90 7.2%（cl100k_base 校准）
```

以上数字来自 `bench/RESULTS.md`，可用 `python3 bench/bench.py` 复现。

---

## 60 秒上手

```bash
# 1. 装 CLI（可选）
pip install .

 # 2. 只试压一次，不改任何配置
npm run build 2>&1 | tk 1200

# 3. 装进助手，让每个会话自动带上规则
git clone https://github.com/danielburtonn844-ai/token-saver.git
cd token-saver && bash scripts/install.sh --target auto --dry-run   # 先看计划
bash scripts/install.sh --target auto                              # 真装

# 4. 自检
tk-doctor
```

不想装 Python 包也能用：`scripts/` 下的脚本直接 `python3 scripts/xxx.py` 就能跑。

---

## 安装

### 方式一：pip（只要命令行工具）

```bash
pip install .
tk --version && tk-audit --version && tk-pack --version && tk-handover --version && tk-doctor
```

装出来五个命令：`tk`、`tk-audit`、`tk-pack`、`tk-handover`、`tk-doctor`。

### 方式二：安装脚本（工具 + 技能 + 常驻内核）

```bash
git clone https://github.com/danielburtonn844-ai/token-saver.git
cd token-saver
bash scripts/install.sh --target auto
```

安装器做两件事：复制技能目录，把一段约 200 token 的规则写进会话入口文件。

| target | 技能目录 | 入口文件 |
|---|---|---|
| `minis` | `/var/minis/skills/token-saver` | `/var/minis/memory/GLOBAL.md` |
| `claude` | `~/.claude/skills/token-saver` | `~/.claude/CLAUDE.md` |
| `codex` | `~/.codex/token-saver` | `~/.codex/AGENTS.md` |
| `project` | `./skills/token-saver` | `./AGENTS.md` |
| `custom --dir D` | `D/token-saver` | `D/AGENTS.md` |

常用选项：

```bash
bash scripts/install.sh --target claude --dry-run    # 只打印计划，不改文件
bash scripts/install.sh --target claude --status     # 查装没装
bash scripts/install.sh --target claude --core-only  # 只注入内核
bash scripts/install.sh --target claude --skill-only # 只复制技能
bash scripts/install.sh --target claude --uninstall  # 卸载，默认留备份
bash scripts/install.sh --target claude --no-backup --force  # 覆盖且不留备份
```

写入采用标记块包裹 + 原子替换，重复执行会原地升级，不会追加第二份。

### 卸载

```bash
bash scripts/install.sh --target claude --uninstall
pip uninstall token-saver
```

卸载默认把入口文件和技能目录改名备份（`*.bak.<时间戳>` / `*.removed.<时间戳>`），确认无误后自行删除。

---

## 命令参考

### `tk` / `tk compress_toolout.py` — 压缩工具输出

```bash
npm run build 2>&1 | tk 1200
tk --file /tmp/build.log --budget 2000 --head 30
cat huge.json | tk --profile json --strict --out /tmp/summary.txt
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--file` | stdin | 输入文件 |
| `--budget` | 1500 | 输出 token 预算（软上限） |
| `--head` / `--tail` | 12 / 8 | 强制保留的首尾行数 |
| `--max-line` | 400 | 单行最大字符数，0 表示不截断 |
| `--profile` | auto | `default/build/test/json/traversal/auto` |
| `--strict` | 关 | 预算改为硬上限，超了丢低分行 |
| `--no-keep-errors` | 关 | 允许省略错误行（默认全保留） |
| `--stats` / `--json` | 关 | 只出统计 / 统计以 JSON 写到 stderr |
| `--out` | 无 | 正文写入文件 |
| `--max-bytes` | 64MB | 读取上限 |

处理顺序：去 ANSI → 截超长行 → 折叠连续重复 → 同型行按签名合并 → 保头尾 → 保错误 → 按分数补满预算。

**预算语义（重要）**：预算约束的是「补选内容」。头尾行和错误行受保护，可能让总量略超预算；要硬上限请加 `--strict`。预算很小时头尾会自动收缩。

### `tk-audit` — token 体检

```bash
tk-audit build.log
tk-audit --dir ./src --top 10 --exclude '*.min.js' --ext py
tk-audit --json session.jsonl
cat session.jsonl | tk-audit -
```

找出重复行、超长行、进度条和最大段落，回答「这段值不值得压」。

### `tk-pack` — 目录索引卡

```bash
tk-pack ./project -o INDEX.md
tk-pack ./project --depth 3 --max-files 80 --json
```

先看卡，再决定读哪几个文件，避免一上来就整仓库扫一遍。

### `tk-handover` — 跨会话交接单

```bash
tk-handover new   HANDOVER.md
tk-handover check HANDOVER.md --json
tk-handover show  HANDOVER.md
```

校验六类问题：缺段、重复段、空段、残留占位符、超长、非标准段落。

### `tk-doctor` — 环境自检

```bash
tk-doctor          # 人读
tk-doctor --json   # 机读
```

检查 Python 版本、安装位置、内核块、PATH、常驻内核 token 体积。

### 模块方式

```bash
python -m token_saver {compress|audit|pack|handover|doctor} ...
```

### 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 业务失败（交接单未通过、已存在不覆盖等） |
| 2 | 参数错误 |
| 3 | 输入错误（文件不存在、二进制输入） |
| 4 | 输出错误（写文件失败） |

---

## 实测数据

`bench/RESULTS.md` 由 `python3 bench/bench.py` 生成，固定种子，可复现。

| 语料 | 行数 | 原始 tk | 预算 | 输出 tk | 压缩 | 错误签名召回 | 耗时 |
|---|---:|---:|---:|---:|---:|---:|---:|
| build_log | 120,000 | 3,613,333 | 1500 | 1,219 | 99.97% | 100% | 4.4s |
| test_output | 8,534 | 151,674 | 800 | 397 | 99.74% | 100% | 0.23s |
| json_dump | 60,000 | 3,967,076 | 1500 | 1,097 | 99.97% | — | 4.3s |
| traversal | 80,001 | 1,643,894 | 800 | 386 | 99.98% | — | 2.3s |
| access_log | 150,000 | 8,479,587 | 1500 | 882 | 99.99% | — | 10.7s |
| stacktrace | 3,000 | 30,926 | 300 | 282 | 99.09% | 100% | 0.05s |
| chinese_log | 12,000 | 520,172 | 1500 | 919 | 99.82% | 100% | 0.32s |

几点说明：

- 错误按「签名」统计：同一类错误（只差数字/时间/IP）折叠成一个样本并标注次数，视为未丢失；具体行召回会低于 100%，属预期。
- 错误行不参与预算裁剪，所以错误极密的样本会超预算：`build_log` 给 300 预算实际 864 tk（20+ 种不同错误各占一行）。要硬上限用 `--strict`。
- 吞吐约 2 MB/s（aarch64 单核）。日志场景够用；TB 级请先用 `rg` 粗筛。
- 所有语料都做了保真检查：输出中不允许出现原文没有的内容，全部通过。

token 估算误差（`bench/CALIBRATION.md`，cl100k_base，50 份样本，训练/测试各半）：

| 指标 | 中位误差 | p90 | 最大 |
|---|---:|---:|---:|
| 三特征模型 | **4.9%** | 7.2% | 11.3% |

---

## 兼容性

| 平台 | 状态 | 说明 |
|---|---|---|
| Linux x86_64 / aarch64 | 完整支持 | CI 全绿 |
| macOS | 完整支持 | CI 全绿 |
| Windows | CLI 与测试支持 | 安装脚本需 WSL 或 Git Bash |
| Python 3.9–3.13 | 支持 | CI 矩阵覆盖 |
| 第三方依赖 | 无 | 核心只用标准库；`bench/calibrate.py` 可选 tiktoken |

---

## 为什么有效

每次请求的输入不只是刚打的字，还包括系统提示、工具定义、之前所有轮次的内容。历史部分每一轮都会重新发一遍，这才是账单的主要来源。

设初始上下文 `C0`，每轮平均新增 `Δ`，共 `N` 轮：

```
累计输入 ≈ N·C0 + Δ·N(N−1)/2
```

第二项和轮数平方相关。以 `C0 = 20K`、`Δ = 3K`、`N = 30`：

| 做法 | 累计输入 | 相对原始 |
|---|---:|---:|
| 原始 | 1,905,000 | — |
| 只把 Δ 压到 1K | 1,035,000 | −46% |
| 只把轮数减到 15 | 405,000 | −79% |
| 两个都做 | 195,000 | −90% |

这是**模型推算**，不是实测账单。它说明优先级：先砍轮数，再砍增量，最后砍初始上下文。仓库的基准数据只覆盖第二项里的「工具输出压缩」，另外两项是方法，靠规范落地。

---

## 三类内容

| 类型 | 典型内容 | 处理 |
|---|---|---|
| 载荷 | 报错原文、关键代码、接口字段、金额与 ID、用户约束 | 原样保留 |
| 搬运 | 全量日志、整文件重贴、重复需求、进度条、客套话 | 压缩或折叠 |
| 探索 | 翻目录、抓网页、反复试错 | 交给子代理，只收结论 |

判断标准只有一条：删掉这段内容，会不会让结论出错。

---

## 红线

以下内容在任何情况下都不压缩：

1. 首次出现的完整报错和堆栈
2. 测试与构建的执行结果
3. 用户给出的约束原文
4. 金额、ID、端口、版本号、哈希、时间戳
5. 接口字段名、类型、状态码
6. 鉴权、加密、SQL、权限判断相关代码
7. 并发与边界条件
8. 提交前的完整 diff
9. 依赖版本与锁文件
10. 删除或迁移前的影响面确认
11. 不确定时的查证
12. 推理过程本身

前十一条是信息，第十二条是方法。压缩的对象是输入输出，不是思考。

工具层面：错误行默认不参与预算裁剪；同型重复的错误折叠成一个样本 + 次数，保证「每种错误都看得见」。

---

## 目录结构

```
token-saver/
├── token_saver/               可导入的包（全部逻辑）
│   ├── text.py                token 估算 / 编码 / 二进制识别
│   ├── compress.py            压缩算法
│   ├── audit.py               体检
│   ├── pack.py                索引卡
│   ├── handover.py            交接单
│   ├── doctor.py              环境自检
│   └── cli.py                 命令行
├── scripts/                   薄封装（也可直接运行）
│   ├── compress_toolout.py    tk
│   ├── tk_audit.py
│   ├── ctx_pack.py
│   ├── handover.py
│   ├── tk_doctor.py
│   ├── apply_core.py          内核块增删查
│   ├── tk                    bash 简写
│   └── install.sh            安装 / 卸载 / 状态
├── SKILL.md                   主规范
├── CHEATSHEET.md              一页速查
├── references/                九篇细则
├── templates/                 常驻内核 / 交接单 / 子代理任务单
├── bench/                     语料 / 基准 / 校准 / 结果
├── tests/                     130 项测试
└── pyproject.toml
```

---

## 测试

```bash
python -m unittest discover -s tests -t .   # 零依赖
python -m pytest -q                          # 装了 pytest 也行
python -m ruff check .                       # 可选
python bench/bench.py                        # 基准
```

覆盖：空输入、二进制、坏字节、BOM/CRLF、超长行、极值参数、错误保留、折叠、重复、profile 识别、JSON/CSV、安装/卸载/幂等/权限、6 万行性能回归。

---

## FAQ / 排错

**Q：压缩后看不到我要的东西怎么办？**
先 `--budget` 加大，或 `--profile build/test/json` 换预设；仍不行就 `--head 50 --tail 20` 或直接 `rg` 原文——输出末尾会打印原文路径。

**Q：为什么输出比预算大？**
头尾行和错误行受保护。要硬上限加 `--strict`；或把 `--head/--tail` 调小。

**Q：装完没生效？**
规则只在**新会话**加载。老会话不会重新读入口文件，开新会话；`tk-doctor` 会告诉你内核块在不在。

**Q：`install.sh: Permission denied`？**
目标目录不可写。换 `--dir` 到可写位置，或用有权限的用户执行；别直接 sudo 改用户目录权限。

**Q：Windows 上跑不了 install.sh？**
用 WSL / Git Bash，或只用 `pip install .` 拿 CLI。

**Q：token 数是准的吗？**
估算，中位误差 4.9%、p90 7.2%，用于取舍够用，别拿它核对账单。

**Q：会改我的仓库文件吗？**
`project` 目标会写 `./AGENTS.md` 和 `./skills/`；默认先备份、原子写入；`--dry-run` 可以先看。

---

## 已知限制

- token 是估算，误差见上；超长单个样本（几万字符）偏差会更大
- 压缩有损，细节必须回原文核对，输出里保留原文路径
- 规范靠执行者遵守；脚本不会自动改变助手行为
- 子代理能力因产品而异，本仓库只给方法和任务单模板
- 吞吐约 2 MB/s，超大文件建议先粗筛

---

## 参与

见 [CONTRIBUTING.md](CONTRIBUTING.md)。安全问题走 [SECURITY.md](SECURITY.md)。

## 许可

MIT，见 [LICENSE](LICENSE)。
