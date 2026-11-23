# 更新记录

## 2.1.0

从「一份规范 + 四个脚本」升级为可安装、可测试、有实测数据的工具。

**工具**
- 逻辑收敛到 `token_saver` 包，`pip install .` 得到五个命令；脚本保留为薄封装
- 压缩新增 `--profile`、`--strict`；错误行默认保留，同型错误折叠为样本 + 次数
- 输入编码自动识别 UTF-8 / GB18030 / UTF-16，可用 `--encoding` 指定；GBK 日志不再被当二进制
- `--strict` 真正封顶：预算连省略标记都放不下时输出空
- 新增 `tk-doctor`；所有命令统一 `--json`、退出码和 UTF-8 输出
- 安装器支持 uninstall/status/dir/codex，备份 + 原子写，重复执行不追加

**质量**
- 131 项单元测试 + 48 项冒烟；CI 覆盖 Python 3.9–3.13 × Linux/macOS/Windows
- 修二进制 stdin 崩溃、Windows 编码、macOS bash 3.2 变量边界
- token 估算按 cl100k 校准：中位误差 4.9%，p90 7.2%

**基准**
- 7 类语料 × 3 档预算，结果见 `bench/RESULTS.md`，可复现

## 2.0.0

- 重写 `SKILL.md`：成本模型、三类 token、12 条红线
- 九篇 `references/`、四个脚本、安装器、冒烟测试

## 1.0.0

- 单文件 `SKILL.md`
