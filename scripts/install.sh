#!/usr/bin/env bash
# install.sh — 安装/升级/卸载 token-saver 技能与常驻内核。
#
#   bash scripts/install.sh                      # 自动探测目标
#   bash scripts/install.sh --target claude      # ~/.claude
#   bash scripts/install.sh --target codex       # ~/.codex
#   bash scripts/install.sh --target minis       # /var/minis
#   bash scripts/install.sh --target project     # 当前目录
#   bash scripts/install.sh --dir /opt/skills    # 自定义目录
#   bash scripts/install.sh --dry-run            # 只打印计划
#   bash scripts/install.sh --status             # 看装没装
#   bash scripts/install.sh --uninstall          # 卸载（保留备份）
#   bash scripts/install.sh --core-only          # 只注入内核
#   bash scripts/install.sh --skill-only         # 只复制技能
#   bash scripts/install.sh --no-backup --force  # 覆盖且不留备份
set -euo pipefail
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/^version:[[:space:]]*//p' "$SRC/SKILL.md" 2>/dev/null | head -1)"
if [ -z "$VERSION" ]; then VERSION="unknown"; fi
TS="$(date +%Y%m%d-%H%M%S)"

TARGET="auto"
CUSTOM_DIR=""
ENTRY_OVERRIDE=""
ACTION="install"
CORE_ONLY=0
SKILL_ONLY=0
DRY=0
FORCE=0
BACKUP=1

log()  { printf '  %s\n' "$*"; }
die()  { printf '错误: %s\n' "$*" >&2; exit 2; }

usage() {
  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    --target)      TARGET="${2:-}"; [ -n "$TARGET" ] || die "--target 需要参数"; shift 2 ;;
    --dir)         CUSTOM_DIR="${2:-}"; [ -n "$CUSTOM_DIR" ] || die "--dir 需要参数"; TARGET="custom"; shift 2 ;;
    --entry)       ENTRY_OVERRIDE="${2:-}"; shift 2 ;;
    --core-only)   CORE_ONLY=1; shift ;;
    --skill-only)  SKILL_ONLY=1; shift ;;
    --dry-run)     DRY=1; shift ;;
    --force)       FORCE=1; shift ;;
    --no-backup)   BACKUP=0; shift ;;
    --uninstall)   ACTION="uninstall"; shift ;;
    --status)      ACTION="status"; shift ;;
    -h|--help)     usage ;;
    *) die "未知参数: $1（--help 查看用法）" ;;
  esac
done

if [ "$CORE_ONLY" = 1 ] && [ "$SKILL_ONLY" = 1 ]; then
  die "--core-only 与 --skill-only 不能同时使用"
fi

command -v python3 >/dev/null 2>&1 || die "没找到 python3，请先安装 Python 3.9+"
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  die "Python 版本过低：$(python3 -V 2>&1)，需要 3.9+"
fi

case "$TARGET" in
  auto)
    if [ -d /var/minis/skills ] && [ -w /var/minis/skills ]; then TARGET="minis"
    elif [ -d "$HOME/.claude" ]; then TARGET="claude"
    elif [ -d "$HOME/.codex" ]; then TARGET="codex"
    else TARGET="project"; fi ;;
  minis|claude|codex|project|custom) ;;
  *) die "未知 target: ${TARGET}（可选 auto/minis/claude/codex/project/custom）" ;;
esac

case "$TARGET" in
  minis)   SKILL_DIR="/var/minis/skills/token-saver";    ENTRY="/var/minis/memory/GLOBAL.md" ;;
  claude)  SKILL_DIR="$HOME/.claude/skills/token-saver"; ENTRY="$HOME/.claude/CLAUDE.md" ;;
  codex)   SKILL_DIR="$HOME/.codex/token-saver";         ENTRY="$HOME/.codex/AGENTS.md" ;;
  project) SKILL_DIR="$PWD/skills/token-saver";          ENTRY="$PWD/AGENTS.md" ;;
  custom)  SKILL_DIR="$CUSTOM_DIR/token-saver";          ENTRY="$CUSTOM_DIR/AGENTS.md" ;;
esac
if [ -n "$ENTRY_OVERRIDE" ]; then ENTRY="$ENTRY_OVERRIDE"; fi

CORE_FILE="$SRC/templates/AGENTS.core.md"
APPLY_CORE="$SRC/scripts/apply_core.py"
if [ ! -f "$APPLY_CORE" ]; then die "缺少 scripts/apply_core.py，请从完整仓库运行"; fi

header() {
  echo "token-saver $VERSION"
  log "源目录: $SRC"
  log "目标:   $TARGET"
  log "技能:   $SKILL_DIR"
  log "入口:   $ENTRY"
  echo
}

need_writable() {
  local p="$1" probe="$1"
  while [ ! -e "$probe" ] && [ "$probe" != "/" ]; do probe="$(dirname "$probe")"; done
  if [ ! -w "$probe" ]; then
    die "没有写权限: ${p}（当前用户 $(id -un)）。换 --dir 到可写位置，或用有权限的用户运行"
  fi
}

maybe_backup_file() {
  local f="$1"
  if [ "$BACKUP" = 1 ] && [ -f "$f" ]; then
    cp -p "$f" "$f.bak.$TS"
    log "已备份 $f.bak.$TS"
  fi
}

copy_skill() {
  mkdir -p "$SKILL_DIR"
  cp -R "$SRC/SKILL.md" "$SRC/references" "$SRC/scripts" "$SRC/templates" \
        "$SRC/token_saver" "$SKILL_DIR/"
  local extra
  for extra in CHEATSHEET.md README.md LICENSE CHANGELOG.md pyproject.toml; do
    if [ -f "$SRC/$extra" ]; then cp "$SRC/$extra" "$SKILL_DIR/"; fi
  done
  log "已安装到 $SKILL_DIR"
}

do_status() {
  header
  local skill_ok=0 core_ok=0
  if [ -f "$SKILL_DIR/SKILL.md" ]; then skill_ok=1; fi
  if python3 "$APPLY_CORE" status "$ENTRY" >/dev/null 2>&1; then core_ok=1; fi
  log "技能文件: $([ $skill_ok = 1 ] && echo 已安装 || echo 未安装)"
  log "常驻内核: $([ $core_ok = 1 ] && echo 已注入 || echo 未注入)"
  if [ $skill_ok = 1 ] && [ $core_ok = 1 ]; then
    log "状态: 可用"
    return 0
  fi
  log "状态: 不完整，运行 bash scripts/install.sh --target $TARGET"
  return 1
}

do_uninstall() {
  header
  echo "[1/2] 移除常驻内核"
  if [ "$DRY" = 1 ]; then
    python3 "$APPLY_CORE" remove "$ENTRY" --dry-run || true
  else
    maybe_backup_file "$ENTRY"
    if ! python3 "$APPLY_CORE" remove "$ENTRY"; then
      log "入口文件里没有内核块，跳过"
    fi
  fi

  echo "[2/2] 移除技能目录"
  if [ -e "$SKILL_DIR" ]; then
    if [ "$DRY" = 1 ]; then
      log "[dry] 移除 $SKILL_DIR"
    elif [ "$BACKUP" = 1 ]; then
      mv "$SKILL_DIR" "$SKILL_DIR.removed.$TS"
      log "已移到 $SKILL_DIR.removed.${TS}（确认无用后可删）"
    else
      rm -rf "$SKILL_DIR"
      log "已删除 $SKILL_DIR"
    fi
  else
    log "技能目录不存在，跳过"
  fi
  echo "卸载完成。"
}

do_install() {
  header
  if [ "$SKILL_ONLY" = 0 ]; then need_writable "$ENTRY"; fi
  if [ "$CORE_ONLY" = 0 ]; then need_writable "$SKILL_DIR"; fi

  if [ "$CORE_ONLY" = 0 ]; then
    echo "[1/2] 复制技能文件"
    if [ "$DRY" = 1 ]; then
      log "[dry] mkdir -p $SKILL_DIR"
      log "[dry] 复制 SKILL.md references scripts templates token_saver"
    else
      if [ -d "$SKILL_DIR" ]; then
        if [ "$BACKUP" = 1 ]; then
          mv "$SKILL_DIR" "$SKILL_DIR.bak.$TS"
          log "旧版本已备份到 $SKILL_DIR.bak.$TS"
        else
          rm -rf "$SKILL_DIR"
        fi
      fi
      copy_skill
    fi
  else
    echo "[1/2] 跳过技能复制（--core-only）"
  fi

  if [ "$SKILL_ONLY" = 0 ]; then
    echo "[2/2] 注入常驻内核"
    if [ "$DRY" = 1 ]; then
      python3 "$APPLY_CORE" add "$ENTRY" "$CORE_FILE" --dry-run
    else
      maybe_backup_file "$ENTRY"
      python3 "$APPLY_CORE" add "$ENTRY" "$CORE_FILE"
    fi
  else
    echo "[2/2] 跳过内核注入（--skill-only）"
  fi

  echo
  echo "完成。新会话自动生效。"
  echo "  自检: python3 $SRC/scripts/tk_doctor.py"
  echo "  卸载: bash $SRC/scripts/install.sh --target $TARGET --uninstall"
}

case "$ACTION" in
  status)    do_status ;;
  uninstall) do_uninstall ;;
  install)   do_install ;;
esac
