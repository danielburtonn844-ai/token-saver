<div align="center">

# token-saver

**省 token 的作业规范与配套脚本**

版本 `v2.0.0` · Python 3.9+ · 无第三方依赖

[![CI](https://github.com/danielburtonn844-ai/token-saver/actions/workflows/ci.yml/badge.svg)](https://github.com/danielburtonn844-ai/token-saver/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)

<br>

作者 **[ @fenghaogou ](https://t.me/fenghaogou)** &nbsp;·&nbsp; 频道 **[ @TvT_GG ](https://t.me/TvT_GG)**

</div>

---

## 这是什么

一套给 AI 编程助手用的作业规范，加四个处理文本的小脚本。

解决的具体问题：长会话越跑越贵、工具输出把上下文塞满、换个会话就得从头讲一遍。仓库给出的答案是三条规则加一套压缩工具，可以用安装脚本挂到 Claude Code、Codex、Minis 这类环境里，每次开新会话自动带上。

包含：

- **一份主规范** `SKILL.md`：成本算法、三类 token 的划分、五条操作规则、12 条不许压缩的红线
- **九篇细则** `references/`：工具输出、子代理、交接、缓存、压缩、输出格式、反例
- **四个脚本** `scripts/`：体检、压缩、交接单、目录索引卡
- **一个安装器** `scripts/install.sh`：支持 minis / claude / project 三种目标，幂等

---

## 为什么需要

每次请求的输入不只是刚打的字，还包括系统提示、工具定义、之前所有轮次的内容。历史部分每一轮都会重新发一遍，这部分才是账单的主要来源。

设初始上下文 `C0`，每轮平均新增 `Δ`，共 `N` 轮：

```
累计输入 ≈ N·C0 + Δ·N(N−1)/2
```

第二项和轮数的平方相关。以 `C0 = 20K`、`Δ = 3K`、`N = 30` 为例：

| 做法 | 累计输入 | 相对原始 |
|---|---:|---:|
| 原始 | 1,905,000 | — |
| 只把 Δ 压到 1K | 1,035,000 | −46% |
| 只把轮数减到 15 | 405,000 | −79% |
| 两个都做 | 195,000 | −90% |

结论：减少轮数的收益最大，其次是压缩每轮新增的内容，最后才是压缩初始上下文。顺序反过来做，效果会差很多。

---

## 核心思路

把上下文里的内容分成三类，分别处理：

| 类型 | 典型内容 | 处理方式 |
|---|---|---|
| 载荷 | 报错原文、关键代码、接口字段、金额与 ID、用户约束 | 原样保留 |
| 搬运 | 全量日志、整文件重贴、重复的需求描述、进度条、客套话 | 压缩或折叠 |
| 探索 | 翻目录、抓网页、反复试错 | 交给子代理，只收结论 |

判断标准只有一条：删掉这段内容，会不会让结论出错。

对应的五条操作规则：

1. 大输出先落盘，再用 `grep`、`jq` 取需要的部分
2. 输出控制在头、命中、尾三段，中间用省略标记
3. 预计超过 20KB 或 6 轮工具调用，交给子代理
4. 阶段结论写进 `HANDOVER.md`，对话里只留路径
5. 一个任务一个会话，换任务就新开

---

## 快速开始

### 环境要求

- Python 3.9 及以上，只用标准库
- Bash（安装脚本）
- Windows 可用 WSL 或 Git Bash，脚本本身不依赖系统特性

### 安装

```bash
git clone https://github.com/danielburtonn844-ai/token-saver.git
cd token-saver
bash scripts/install.sh --target auto
```

安装脚本做两件事：把技能目录复制到对应位置，把一段两百 token 左右的规则写进会话入口文件。

| target | 技能目录 | 入口文件 |
|---|---|---|
| `minis` | `/var/minis/skills/token-saver` | `/var/minis/memory/GLOBAL.md` |
| `claude` | `~/.claude/skills/token-saver` | `~/.claude/CLAUDE.md` |
| `project` | `./skills/token-saver` | `./AGENTS.md` |

`--target auto` 会按目录存在情况自动选择。只写规则、不复制技能：

```bash
bash scripts/install.sh --core-only
```

写入用标记块包裹，重复执行不会重复追加。确认会不会改动文件：

```bash
bash scripts/install.sh --target minis --dry-run
```

### 验证

```bash
bash tests/smoke.sh
```

十六项断言，包含语法检查、压缩效果、交接单校验、索引卡生成和安装脚本试运行。

---

## 脚本

### tk_audit.py

统计文件或目录的 token 分布，列出重复行、超长行、空行和占用最大的段落。用来判断哪一段值得压缩。

```bash
python3 scripts/tk_audit.py build.log
python3 scripts/tk_audit.py --dir ./src --top 10
python3 scripts/tk_audit.py --json session.jsonl
cat session.jsonl | python3 scripts/tk_audit.py -
```

| 参数 | 说明 |
|---|---|
| `--dir` | 递归统计目录 |
| `--top` | 每个文件列出几个最大的段落，默认 5 |
| `--max-files` | 目录模式下的文件上限，默认 200 |
| `--json` | 输出 JSON |

输出示例：

```
文件: build.log
  行数 3,000 | 字符 230,760 | 估算 57,691 token
  空行 0 | 重复行 172 | 超长行 0 | 进度条行 0
  可压缩估算 3,269 token（≈6%）
```

### compress_toolout.py

压缩命令输出，处理顺序为：去掉 ANSI 控制符、截断超长行、折叠连续重复、把只有数字不同的行合并成一条、保留开头和结尾、在剩余预算内优先保留错误和警告。

```bash
npm run build 2>&1 | python3 scripts/compress_toolout.py --budget 1200
python3 scripts/compress_toolout.py --file /tmp/build.log --budget 2000 --keep-errors
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--file` | stdin | 输入文件 |
| `--budget` | 1500 | 输出 token 预算 |
| `--head` / `--tail` | 12 / 8 | 强制保留的首尾行数 |
| `--max-line` | 400 | 单行最大字符数 |
| `--keep-errors` | 关 | 错误行不计入预算 |
| `--out` | 无 | 写入文件而不是标准输出 |
| `--stats` | 关 | 只输出统计 |

在三千行构建日志上的实测：64,613 tk 压到 474 tk，错误样本和首尾内容保留。

### tk

`compress_toolout.py` 的简写，参数是预算：

```bash
npm run build 2>&1 | scripts/tk 1200
```

### handover.py

生成、校验、查看跨会话交接单。校验会检查五个段落是否齐全、是否有空段、总长度是否超过 400 token。

```bash
python3 scripts/handover.py new   HANDOVER.md
python3 scripts/handover.py check HANDOVER.md
python3 scripts/handover.py show  HANDOVER.md
```

模板在 `templates/HANDOVER.md`，五段：目标、状态、关键决策、文件指针、下一步。

### ctx_pack.py

给目录生成一张索引卡，包含文件名、行数、token 估算和一行摘要。先看卡，再决定读哪几个文件。

```bash
python3 scripts/ctx_pack.py ./project -o INDEX.md
python3 scripts/ctx_pack.py ./project --depth 3 --max-files 80
```

跳过 `.git`、`node_modules`、`__pycache__` 和常见二进制后缀。六十多 KB 的仓库生成出来的卡约 350 token。

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

---

## 目录结构

```
token-saver/
├── SKILL.md                    主规范
├── CHEATSHEET.md               一页速查
├── references/
│   ├── 01-context-economics.md 成本模型与预算
│   ├── 02-tool-output.md       各工具压缩写法
│   ├── 03-delegation.md        子代理委派
│   ├── 04-handover.md          跨会话交接
│   ├── 05-prompt-caching.md    缓存友好
│   ├── 06-compaction.md        压缩保真度
│   ├── 07-output-format.md     输出格式
│   ├── 08-quality-guards.md    红线判定
│   └── 09-anti-patterns.md     翻车记录
├── scripts/
│   ├── tk_audit.py
│   ├── compress_toolout.py
│   ├── tk
│   ├── handover.py
│   ├── ctx_pack.py
│   └── install.sh
├── templates/
│   ├── AGENTS.core.md          常驻内核
│   ├── HANDOVER.md
│   └── SUBAGENT_BRIEF.md
├── examples/demo.md
└── tests/smoke.sh
```

---

## 已知限制

- token 数是估算，按中文字符 0.6、其他字符 0.25 折算，误差约 ±15%，够用来做取舍判断，不适合核对账单
- 规范需要执行者遵守，脚本只做文本处理，不会自动改变助手的行为
- 压缩是有损的，超长日志压完只能看个大概，细节要去原始文件里找，脚本会在输出里保留原文路径
- 子代理是各家产品的能力，本仓库只给委派方法和任务单模板，不包含具体实现

---

## 许可

MIT
