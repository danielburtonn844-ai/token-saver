# 一页速查（打印贴墙版）

## 三个数字

- **30 行**：单条命令输出的上限，超了就截断或落盘
- **20KB / 6 轮**：超过就外派子代理
- **300 token**：HANDOVER 的上限

## 五个动作

```bash
# 1 只看状态
curl -s -o /dev/null -w "%{http_code} %{size_download}\n" URL

# 2 落盘再筛
cmd > /tmp/o.log 2>&1; grep -nE "error|fail" /tmp/o.log | head

# 3 只取字段
curl -s URL | jq -r '.items[] | [.id,.status] | @tsv' | head -20

# 4 压输出
cmd 2>&1 | python3 scripts/compress_toolout.py --budget 1500

# 5 交接
python3 scripts/handover.py new HANDOVER.md
```

## 三句判断

1. 删了它，我会答错吗？ → 会，别删
2. 这活超过 6 轮吗？ → 超，外派
3. 下轮还要用吗？ → 要，写文件

## 绝不省的 12 项

报错原文 · 测试 · 用户约束 · 数字 · 接口字段 · 安全代码 · 边界条件 · diff · 依赖版本 · 破坏性操作影响面 · 查证 · 推理

## 常见浪费

| 动作 | 改法 |
|---|---|
| `cat big.json` | `jq keys` / `.[0]` |
| `git log -p` | `--oneline` / `-S` |
| 连截 5 张图 | `get_readable` |
| 复述需求 | 直接答 |
| 整文件重贴 | 只贴 diff |
| 60 轮会话加新活 | 新开会话 + HANDOVER |

## 一句话

> 省搬运，不省核实；省重复，不省推理。
