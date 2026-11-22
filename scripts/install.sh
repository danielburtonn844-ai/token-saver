#!/usr/bin/env bash
# install.sh — 安装 token-saver 技能，并把 200 token 常驻内核注入到会话入口文件。
#
#   bash scripts/install.sh --target auto      # 自动探测
#   bash scripts/install.sh --target minis     # /var/minis/skills
#   bash scripts/install.sh --target claude    # ~/.claude/skills
#   bash scripts/install.sh --target project   # ./skills
#   bash scripts/install.sh --core-only        # 只注入内核，不复制技能
#   bash scripts/install.sh --dry-run          # 只打印将要做什么
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BEGIN="<!-- token-saver:core:begin -->"
END="<!-- token-saver:core:end -->"

TARGET="auto"
CORE_ONLY=0
DRY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET="${2:-auto}"; shift 2 ;;
    --core-only) CORE_ONLY=1; shift ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

log() { printf '  %s\n' "$*"; }
run() { if [ "$DRY" = 1 ]; then log "[dry] $*"; else eval "$@"; fi; }

detect_target() {
  if [ -d /var/minis/skills ]; then echo minis
  elif [ -d "$HOME/.claude" ]; then echo claude
  else echo project; fi
}

[ "$TARGET" = auto ] && TARGET="$(detect_target)"

case "$TARGET" in
  minis)   SKILL_DIR="/var/minis/skills/token-saver"; ENTRY="/var/minis/memory/GLOBAL.md" ;;
  claude)  SKILL_DIR="$HOME/.claude/skills/token-saver"; ENTRY="$HOME/.claude/CLAUDE.md" ;;
  project) SKILL_DIR="$PWD/skills/token-saver"; ENTRY="$PWD/AGENTS.md" ;;
  *) echo "未知 target: $TARGET" >&2; exit 2 ;;
esac

echo "token-saver 安装"
log "源目录: $SRC"
log "目标:   $TARGET"
log "技能:   $SKILL_DIR"
log "入口:   $ENTRY"

if [ "$CORE_ONLY" = 0 ]; then
  echo "[1/2] 复制技能文件"
  run "mkdir -p '$SKILL_DIR'"
  run "cp -R '$SRC/SKILL.md' '$SRC/references' '$SRC/scripts' '$SRC/templates' '$SKILL_DIR/'"
else
  echo "[1/2] 跳过技能复制（--core-only）"
fi

echo "[2/2] 注入常驻内核"
CORE="$(cat "$SRC/templates/AGENTS.core.md")"
run "mkdir -p '$(dirname "$ENTRY")'"
if [ -f "$ENTRY" ] && grep -qF "$BEGIN" "$ENTRY" 2>/dev/null; then
  log "已存在内核块，跳过（幂等）"
else
  if [ "$DRY" = 1 ]; then
    log "[dry] 追加内核到 $ENTRY"
  else
    {
      printf '\n%s\n' "$BEGIN"
      printf '%s\n' "$CORE"
      printf '%s\n' "$END"
    } >> "$ENTRY"
    log "已追加到 $ENTRY"
  fi
fi

echo "完成。新会话自动生效；细则按需读 $SKILL_DIR/SKILL.md"
