#!/usr/bin/env bash
# smoke.sh — 快速冒烟：语法、核心功能、安装/卸载闭环。
# 单元测试请跑：python -m unittest discover -s tests -t .
set -uo pipefail
cd "$(dirname "$0")/.."
PASS=0; FAIL=0

ok()   { PASS=$((PASS+1)); printf '  \033[32mPASS\033[0m %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  \033[31mFAIL\033[0m %s\n' "$1"; }
check(){ if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }

echo "[1] 语法"
for f in scripts/*.py token_saver/*.py tests/*.py bench/*.py; do
  check "py_compile $f" "python3 -m py_compile '$f'"
done
check "bash -n install.sh" "bash -n scripts/install.sh"

echo "[2] 造数据"
python3 - <<'PY'
import random
random.seed(7)
out=[]
for i in range(2000):
    if i % 40 == 0:
        out.append(f"2026-01-01 00:00:{i%60:02d} ERROR db.go:{i%90} connection refused host=10.0.0.{i%255}")
    elif i % 9 == 0:
        out.append("npm WARN deprecated left-pad@1.0.0: use something else")
    else:
        out.append(f"2026-01-01 00:00:{i%60:02d} INFO req id={i} status=200 path=/v1/{i}")
open("/tmp/tk_smoke.log","w").write("\n".join(out)+"\n")
PY
check "生成测试日志" "[ -s /tmp/tk_smoke.log ]"

echo "[3] 体检与压缩"
check "audit 有输出" "python3 scripts/tk_audit.py /tmp/tk_smoke.log"
check "audit JSON 合法" "python3 scripts/tk_audit.py --json /tmp/tk_smoke.log | python3 -c 'import json,sys;json.load(sys.stdin)'"
python3 scripts/compress_toolout.py --file /tmp/tk_smoke.log --budget 600 > /tmp/tk_out.txt 2>/tmp/tk_stats.txt
LINES=$(wc -l < /tmp/tk_out.txt)
if [ "$LINES" -lt 80 ]; then ok "压缩到 $LINES 行（<80）"; else bad "压缩后仍有 $LINES 行"; fi
grep -q "省略" /tmp/tk_out.txt && ok "含省略标记" || bad "缺省略标记"
grep -qE "同型|重复" /tmp/tk_out.txt && ok "含同型/重复标记" || bad "缺同型标记"
check "tk 包装器" "head -50 /tmp/tk_smoke.log | bash scripts/tk 300"
check "二进制输入被拒" "printf '\000\001' | python3 scripts/compress_toolout.py; [ \$? -eq 3 ]"
check "严格预算" "python3 scripts/compress_toolout.py --file /tmp/tk_smoke.log --budget 200 --strict --out /tmp/tk_strict.txt"

echo "[4] 交接单"
rm -f /tmp/tk_ho.md
python3 scripts/handover.py new /tmp/tk_ho.md >/dev/null
python3 scripts/handover.py check /tmp/tk_ho.md >/dev/null 2>&1 && bad "空模板不应通过" || ok "空模板被拒"
cat > /tmp/tk_ho.md <<'EOF'
# HANDOVER: demo
## 目标
测试。
## 状态
- 已完成：全部
## 关键决策
- 用 A —— 因为 B 更贵
## 文件指针
- 源码：`/tmp/x`
## 下一步
1. 发布
EOF
python3 scripts/handover.py check /tmp/tk_ho.md >/dev/null 2>&1 && ok "完整交接单通过" || bad "完整交接单被误拒"

echo "[5] 索引卡"
check "索引卡生成" "python3 scripts/ctx_pack.py . --max-files 20 -o /tmp/tk_index.md && grep -q 索引卡 /tmp/tk_index.md"

echo "[6] 安装闭环（临时 HOME）"
TMPHOME=$(mktemp -d)
check "dry-run" "HOME=$TMPHOME bash scripts/install.sh --target claude --dry-run"
check "安装" "HOME=$TMPHOME bash scripts/install.sh --target claude"
check "状态可用" "HOME=$TMPHOME bash scripts/install.sh --target claude --status"
check "内核只一份" "[ \$(grep -c 'token-saver:core:begin' $TMPHOME/.claude/CLAUDE.md) -eq 1 ]"
check "重装幂等" "HOME=$TMPHOME bash scripts/install.sh --target claude && [ \$(grep -c 'token-saver:core:begin' $TMPHOME/.claude/CLAUDE.md) -eq 1 ]"
check "技能自带 doctor" "HOME=$TMPHOME python3 $TMPHOME/.claude/skills/token-saver/scripts/tk_doctor.py --json | python3 -c 'import json,sys; json.load(sys.stdin)'"
check "卸载" "HOME=$TMPHOME bash scripts/install.sh --target claude --uninstall"
check "卸载后无内核" "! grep -q 'token-saver:core' $TMPHOME/.claude/CLAUDE.md 2>/dev/null"
rm -rf "$TMPHOME"

echo
echo "结果：$PASS 通过 / $FAIL 失败"
[ "$FAIL" -eq 0 ]
