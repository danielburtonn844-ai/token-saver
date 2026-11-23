#!/usr/bin/env python3
"""apply_core.py — 在入口文件里安全地写入/删除常驻内核块。

    python3 scripts/apply_core.py add    ENTRY CORE_FILE [--dry-run]
    python3 scripts/apply_core.py remove ENTRY [--dry-run]
    python3 scripts/apply_core.py status ENTRY

特点：原子写入、保留文件权限、幂等（重复 add 会原地升级而不重复追加）、
删除时把块两侧多余的空行一起带走。
"""
import argparse
import os
import shutil
import sys
import tempfile

BEGIN = "<!-- token-saver:core:begin -->"
END = "<!-- token-saver:core:end -->"


def read(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def atomic_write(path, text, like=None):
    """写临时文件再 rename；尽量沿用原文件的权限位。"""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".token-saver-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        if like and os.path.exists(like):
            shutil.copymode(like, tmp)
        else:
            os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def strip_block(text):
    """删掉 BEGIN..END 整块及其两侧空白，返回 (新文本, 是否找到)。"""
    start = text.find(BEGIN)
    if start < 0:
        return text, False
    end = text.find(END, start)
    if end < 0:
        return text, False
    end += len(END)
    before = text[:start].rstrip("\n")
    after = text[end:].lstrip("\n")
    parts = [p for p in (before, after) if p]
    return ("\n\n".join(parts) + "\n") if parts else "", True


def add(entry, core_path, dry_run=False):
    core = read(core_path).strip("\n")
    old = read(entry)
    body, found = strip_block(old)
    block = "%s\n%s\n%s" % (BEGIN, core, END)
    new = (body.rstrip("\n") + "\n\n" + block + "\n") if body.strip() else block + "\n"
    if dry_run:
        print("[dry] 写入 %d 字节内核到 %s（%s）"
              % (len(block), entry, "替换旧块" if found else "新增块"))
        return 0
    atomic_write(entry, new, like=entry)
    print("%s内核：%s" % ("已更新" if found else "已写入", entry))
    return 0


def remove(entry, dry_run=False):
    old = read(entry)
    new, found = strip_block(old)
    if not found:
        print("未找到内核块：%s" % entry)
        return 1
    if dry_run:
        print("[dry] 从 %s 删除内核块" % entry)
        return 0
    atomic_write(entry, new, like=entry)
    print("已删除内核块：%s" % entry)
    return 0


def status(entry):
    text = read(entry)
    found = BEGIN in text and END in text
    print(("已注入" if found else "未注入") + "：" + entry)
    return 0 if found else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="apply_core")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("entry")
    p_add.add_argument("core")
    p_add.add_argument("--dry-run", action="store_true")

    p_rm = sub.add_parser("remove")
    p_rm.add_argument("entry")
    p_rm.add_argument("--dry-run", action="store_true")

    p_st = sub.add_parser("status")
    p_st.add_argument("entry")

    args = ap.parse_args(argv)
    if args.cmd == "add":
        return add(args.entry, args.core, args.dry_run)
    if args.cmd == "remove":
        return remove(args.entry, args.dry_run)
    return status(args.entry)


if __name__ == "__main__":
    sys.exit(main())
