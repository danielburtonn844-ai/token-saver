# 实战演示：一次「贵」的会话怎么变便宜

场景：一个 Node 项目构建失败，要找原因并修好。下面是两种打法的对比。

> 说明：节奏与轮次是常见真实形态，总计数字按 `references/01` 的成本公式推算（示意），单条命令的 token 数为 `tk_audit.py` 估算。

---

## 打法 A：直觉流（贵）

```
轮 1  cat package.json                       → 2,100 tk
轮 2  npm install                            → 18,000 tk（进度条 + 警告）
轮 3  npm run build                          → 26,000 tk（全量日志）
轮 4  cat src/index.ts                       → 4,300 tk
轮 5  改一行
轮 6  npm run build（又全量）                 → 26,000 tk
轮 7  还是错，grep -m1 error                 → 漏了真正原因
轮 8  再改
轮 9  再 build                                → 26,000 tk
轮 10 终于好了，总结一遍
```

累计输入约 **3.5M token**（含历史重复计费），其中真正决定正确性的不到 3%。

---

## 打法 B：本仓库的流程

### 第 1 步：先落盘，不读全文

```bash
npm install --loglevel=error 2>&1 | tail -5        # 40 tk
npm run build > /tmp/build.log 2>&1; echo "exit=$?"  # 10 tk
wc -l /tmp/build.log                                # 3 tk
```

### 第 2 步：压缩输出

```bash
python3 scripts/compress_toolout.py --file /tmp/build.log --budget 1200
```

输出：

```
TS2304: Cannot find name 'OrderService'.        …[同型 ×3]…
src/orders/service.ts:42
…[省略 1,204 行]…
[1,240 行 → 18 行 | 21,800 tk → 1,030 tk | 省 95%]
```

**关键点**：错误类型 + 文件:行号 完整保留，进度条和重复行全部折叠。

### 第 3 步：只读命中的那一段

```bash
sed -n '30,60p' src/orders/service.ts
```

### 第 4 步：改完只跑一次验证

```bash
npm run build > /tmp/build2.log 2>&1; echo "exit=$?"
tail -3 /tmp/build2.log
```

### 第 5 步：写交接

```bash
python3 scripts/handover.py new HANDOVER.md
```

---

## 结果对比

| 指标 | 打法 A | 打法 B | 差异 |
|---|---:|---:|---:|
| 轮次 | 10 | 5 | −50% |
| 累计输入 token | ~3.5M | ~180K | **−95%** |
| 定位准确率 | 靠猜，试错 3 次 | 一次命中 | 更高 |
| 可交接性 | 无 | HANDOVER | — |

---

## 复盘：省在哪

1. **没有一次读全文** —— 全部先落盘，只取字段
2. **构建日志压了 95%** —— 但错误原文与行号一个没丢
3. **轮数减半** —— 合并命令、一次定位
4. **结论落文件** —— 后续排查不用重读历史

**没有省掉的**：报错原文、源码上下文、两次真实构建、验证。

这就是「省搬运，不省核实」。
