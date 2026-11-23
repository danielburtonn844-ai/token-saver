# 02 · 工具输出压缩实战

目标：**任何一条命令的输出，都应该能在 30 行内让你做出判断。** 做不到，就先落盘。

## 1. 万能三段式

```bash
cmd > /tmp/out.log 2>&1; echo "exit=$?"; wc -l < /tmp/out.log
head -20 /tmp/out.log
grep -nE "error|fail|exception|denied|timeout" /tmp/out.log | head -10
tail -10 /tmp/out.log
```

信息量：退出码 + 规模 + 头部 + 异常 + 尾部。通常 40 行以内搞定一个几万行的日志。

## 2. HTTP / API

```bash
# 只要状态与大小
curl -s -o /dev/null -w "%{http_code}\t%{size_download}\t%{time_total}\n" "$URL"

# 要响应但不想全读：先看结构
curl -s "$URL" | head -c 2000

# JSON 只取字段（jq）
curl -s "$URL" | jq -r '.[] | [.id, .name, .status] | @tsv' | head -20

# 数组长度与键名（判断结构，不读数据）
curl -s "$URL" | jq -r 'if type=="array" then "len=\(length)" else keys|join(",") end'

# 分页：先拿第一页的 total
curl -s "$URL?page=1" | jq -r '.total, (.items|length)'
```

坑：`jq` 不带 `-r` 会输出带引号的 JSON，体积翻倍；`jq .` 美化反而更大——**要读结构可以用，要省 token 别用**。

## 3. 日志

```bash
# 只看异常，带行号
grep -nE "ERROR|FATAL|CRITICAL|Traceback|panic" app.log | head -30

# 统计而不是罗列
grep -c "ERROR" app.log
awk '{print $5}' app.log | sort | uniq -c | sort -rn | head -10

# 时间窗
sed -n '/2026-11-22 10:00/,/2026-11-22 10:05/p' app.log | head -50

# 去重折叠（同一错误刷屏时最有用）
sort app.log | uniq -c | sort -rn | head -20
```

## 4. 文件与目录

```bash
# 先看规模再决定读法
wc -l file.txt; du -h file.txt

# 找符号而不是读全文
grep -n "func HandleLogin" *.go

# 读窗口（file_read 的 offset/lines 同理）
sed -n '120,180p' file.py

# 目录结构只到两层
find . -maxdepth 2 -type f | head -40
# 或
tree -L 2 -I 'node_modules|.git' | head -40
```

## 5. Git

```bash
git status --short
git log --oneline -15
git diff --stat
git diff -U3 -- path/to/file        # 只 -U3，不要 -U99
git show --stat HEAD
git log --oneline --since="2 days ago" --author="me"
```

`git log -p` 是上下文炸弹，除非就是要看某个 commit 的完整改动。

## 6. 包管理 / 构建

```bash
npm install --loglevel=error 2>&1 | tail -15
pip install -q pkg 2>&1 | tail -5
make 2>&1 | grep -E "error|Error|warning" | head -20
cargo build 2>&1 | tail -20
```

## 7. 容器 / K8s

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker logs --tail 50 container
kubectl get pods --no-headers | awk '{print $1,$3}' | head -20
kubectl logs deploy/x --tail=50 | grep -iE "error|warn"
kubectl describe pod x | grep -A5 "Events:"
```

## 8. 压缩包 / 二进制

```bash
unzip -l pkg.zip | grep -i "config\|README"     # 不列全表
tar -tzf pkg.tar.gz | head -30
file binary; head -c 16 binary | xxd
strings -n 8 binary | head -20
```

## 9. 数据库

```sql
-- 先看规模
SELECT count(*) FROM t;
-- 再看样本
SELECT * FROM t LIMIT 5;
-- 结构
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='t';
```

```bash
sqlite3 db.sqlite ".tables"
sqlite3 db.sqlite "select count(*) from users;"
```

## 10. 网页 / 浏览器

| 想要 | 用什么 | 省多少 |
|---|---|---|
| 正文 | `get_readable` | 省 90%+ |
| 纯文本 | `get_text` | 省 80% |
| 结构 | `get_backbone`（max_depth 3~5） | 省 70% |
| 布局/渲染验证 | `screenshot` | 贵，慎用 |
| 长列表 | `scroll_and_collect` 一次拿完 | 省重复滚动 |

截图 ≈ 1000~1600 token/张。**连续截 5 张就等于白读一本手册。**

## 11. 输出压缩器用法

```bash
python3 scripts/compress_toolout.py [--file F] [--budget N]
    [--profile default|build|test|json|traversal|auto]
    [--strict] [--no-keep-errors] [--stats|--json] [--out F]
```

行为：
1. 按行切分，超长行（> 500 字符）截断并标注
2. 全等行折叠为 `重复 ×N`
3. 打分：错误/警告行 +3，含数字 +1，含路径 +1，空行 −1
4. 预算内先保头 10 行、尾 10 行，再按分数补
5. 末尾输出 `[原 12,345 行 / 压后 42 行 / 估算省 96%]`

## 12. 常见反模式

| 反模式 | 代价 |
|---|---|
| `cat big.json` | 一次几十万 token |
| `curl -v` 排障之外 | 头部噪音 2~3KB |
| `git log -p` 全历史 | 无上限 |
| `npm install` 不带 `-q` | 几百行进度条 |
| `find /` | 无上限 + 权限报错刷屏 |
| 循环里 `echo` 每行 | 几千行 |
| 失败的 `rsync -av --progress` | 每文件一行 |
