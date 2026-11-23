<div align="center">

# token-saver

**省 token，不降智。**

`v2.1.0` · Python 3.9+ · 零依赖

[![CI](https://github.com/danielburtonn844-ai/token-saver/actions/workflows/ci.yml/badge.svg)](https://github.com/danielburtonn844-ai/token-saver/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

<br>

作者 **[@fenghaogou](https://t.me/fenghaogou)** · 频道 **[@TvT_GG](https://t.me/TvT_GG)**

</div>

---

## 是什么

一套给 AI 编程助手用的省 token 规范，配五个命令行工具。

解决三件事：长会话越跑越贵、工具输出塞满上下文、换会话从头讲一遍。

## 效果

| 输入 | 原始 | 压缩后 | 错误召回 | 耗时 |
|---|---:|---:|---:|---:|
| 12 万行构建日志 | 3,613,333 tk | 1,219 tk | 100% | 4.4s |
| 15 万行访问日志 | 8,479,587 tk | 882 tk | — | 10.7s |
| 6 万行 JSON | 3,967,076 tk | 1,097 tk | — | 4.3s |
| 3000 行堆栈 | 30,926 tk | 282 tk | 100% | 0.05s |

语料固定种子生成，`python3 bench/bench.py` 可复现。错误按签名统计：同类错误折叠成一个样本加次数，不算丢失。

token 估算是 cl100k 校准过的：中位误差 4.9%，p90 7.2%。

## 安装

```bash
pip install .                            # 五个命令（只含 CLI）
bash scripts/install.sh --target auto    # 技能 + 常驻内核（需 clone）
tk-doctor                                # 自检
```

先看计划、卸载：

```bash
bash scripts/install.sh --target auto --dry-run
bash scripts/install.sh --target auto --uninstall
```

安装器支持 `minis` / `claude` / `codex` / `project`，写入带标记块、自动备份、重复执行只升级不追加。

## 命令

| 命令 | 用途 |
|---|---|
| `tk [预算]` | 压缩工具输出，默认 1500 token |
| `tk-audit` | 找文件/目录里的重复、超长行、最大块 |
| `tk-pack` | 给目录生成索引卡 |
| `tk-handover` | 生成和校验跨会话交接单 |
| `tk-doctor` | 检查安装、内核块、PATH |

```bash
npm run build 2>&1 | tk 1200
tk-audit --dir ./src --top 10
tk-pack ./project -o INDEX.md
```

参数看 `tk --help`。预算默认是软上限：头尾和错误行受保护；`--strict` 是硬上限，超了会连错误行一起丢。

输入编码自动识别 UTF-8 / GB18030 / UTF-16，也可 `--encoding gbk` 指定。

## 为什么有效

单轮输入 = 系统提示 + 历史全部轮次 + 本轮内容。历史每轮重发一次。

```
累计输入 ≈ N·C0 + Δ·N(N−1)/2
```

第二项是平方项，所以顺序是：**先砍轮数，再砍每轮增量，最后砍初始上下文**。

以 `C0=20K, Δ=3K, N=30` 推算：只压增量省 46%，只减轮数省 79%，两个都做省 90%。这是模型推算，不是账单实测。

## 分类

| 类型 | 内容 | 处理 |
|---|---|---|
| 载荷 | 报错原文、关键代码、字段、金额、约束 | 原样保留 |
| 搬运 | 全量日志、重复描述、进度条、客套话 | 压缩折叠 |
| 探索 | 翻目录、抓网页、反复试错 | 交子代理，只收结论 |

判据一条：删掉它，会不会让结论出错。

## 红线

不压缩：首次完整报错、测试与构建结果、用户约束原文、金额与 ID、接口字段、鉴权与安全代码、并发边界、提交前 diff、依赖版本、删除前的影响面、不确定时的查证、推理过程本身。

工具层面：错误行不参与预算裁剪；同型重复折叠成样本加次数，保证每种错误都看得见。

## 结构

```
token_saver/     逻辑（text/compress/audit/pack/handover/doctor/cli）
scripts/         薄封装 + install.sh
SKILL.md         规范主文件
references/      九篇细则
templates/       内核、交接单、子代理任务单
bench/           语料、基准、校准
tests/           131 项测试
```

## 限制

- token 是估算，不要拿来核对账单
- 压缩有损，细节回原文核对，输出会打印原文路径
- 规范靠执行者遵守，脚本不会自动改变助手行为
- 错误极密的日志会超预算；`--strict` 能封顶，但会牺牲错误行

## 许可

MIT
