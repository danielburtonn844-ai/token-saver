# 更新记录

## 2.1.0

工程化与实测升级，逐条修掉 2.0.0 的评审问题。

**健壮性**
- `compress_toolout` 读取 stdin 改为二进制读取 + 容错解码，管道喂二进制不再抛 UnicodeDecodeError（改为明确拒绝，退出码 3）
- 统一四条 CLI 的退出码：0 成功 / 1 业务失败 / 2 参数错误 / 3 输入错误 / 4 输出错误
- 增加 `--max-bytes` 读取上限，默认 64MB，超限截断并在 stderr 提示
- 新增 `--strict` 硬预算；默认仍是软预算（错误行受保护），头尾开销会按预算自动收缩，文档明确说明
- 错误行默认全量保留（含被同型折叠的错误行），可用 `--no-keep-errors` 关闭
- 所有文件读取按 UTF-8 容错解码，BOM/CRLF/坏字节都能处理

**功能**
- 四个脚本重构为可导入的 `token_saver` 包，逻辑与 CLI 分离，可 `pip install .`
- 新增 `--profile`（default/build/test/json/traversal/auto）与内容自动识别
- `tk_audit` 新增 `--exclude` / `--ext` / `--csv` / 汇总统计，目录模式跳过二进制与软链接
- `ctx_pack` 新增 `--json` / `--include` / `--exclude`，二进制按魔数识别而非只看后缀
- `handover` 校验重写：结构化问题码（missing/duplicate/empty/placeholders/too-long/unknown），支持 `--json`、`--max-tokens`、`--template`、`--force`
- 新增 `tk_doctor`：检查 Python 版本、安装位置、内核块、PATH、内核 token 体积
- 安装器重写：去掉 eval，新增 `--uninstall` / `--status` / `--dir` / `--entry` / `--force` / `--no-backup` / `--skill-only`，默认备份、原子写入、保留权限位，新增 codex 目标
- 新增 `scripts/apply_core.py`：内核块的增删查，幂等升级不重复追加
- 新增 `python -m token_saver {compress|audit|pack|handover|doctor}`

**估算校准**
- token 估算系数改为对 `cl100k_base` 实测拟合（CJK 0.68 / 其他 0.29），样本与误差见 `bench/RESULTS.md`
- 四个脚本共用同一份估算实现，不再各抄一套系数

**测试**
- 单元测试从 0 增加到 130+ 条，覆盖空输入、二进制、超长行、乱码、极值参数、错误保留、折叠、重复、profile 识别、JSON/CSV 输出、安装/卸载/幂等/权限
- 新增 6 万行性能回归（<10s）
- CI 改为 Python 3.9–3.13 × Linux/macOS/Windows 矩阵

**基准**
- 新增 `bench/bench.py` 与 `bench/calibrate.py`，可复现生成语料、跑压缩质量与估算误差，结果写入 `bench/RESULTS.md`

**文档与治理**
- README 重写：安装/卸载/命令参考/基准数据/兼容矩阵/FAQ/排错
- 新增 CONTRIBUTING、SECURITY、CODE_OF_CONDUCT、Issue/PR 模板、Makefile
- 新增 `pyproject.toml`，可直接 pip 安装

## 2.0.0

- 重写 SKILL.md：加入成本模型、三类 token 分级、12 条不许省的红线
- 新增 references/ 九篇：成本、工具输出、子代理、交接、缓存、压缩、输出格式、红线、翻车记录
- 新增 scripts/tk_audit.py：看文件或目录的 token 分布
- 新增 scripts/compress_toolout.py 和 scripts/tk：压缩命令输出
- 新增 scripts/handover.py：生成和检查交接单
- 新增 scripts/ctx_pack.py：生成目录索引卡
- 新增 scripts/install.sh：安装技能并写入常驻内核
- 新增 tests/smoke.sh 和 GitHub Actions

## 1.0.0

单文件 SKILL.md，分类表和命令建议。
