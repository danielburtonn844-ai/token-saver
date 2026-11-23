"""命令行入口。四个脚本和 ``python -m token_saver`` 共用这一份实现。"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys

from . import __version__
from . import audit as audit_mod
from . import compress as comp
from . import doctor as doctor_mod
from . import handover as handover_mod
from . import pack as pack_mod
from .text import MAX_BYTES, VALID_ENCODINGS


def _force_utf8() -> None:
    """Windows 控制台默认 cp1252，打印中文会抛 UnicodeEncodeError 或写成 \\uXXXX。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_INPUT = 3
EXIT_OUTPUT = 4


def _parser(prog: str, desc: str) -> argparse.ArgumentParser:
    _force_utf8()
    ap = argparse.ArgumentParser(prog=prog, description=desc)
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return ap


def compress_main(argv: list[str] | None = None) -> int:
    ap = _parser("tk", "把冗长的工具输出压成「能看懂又便宜」的摘要")
    ap.add_argument("--file", default="-", help="输入文件，默认 stdin")
    ap.add_argument("--budget", type=int, default=None, help="输出 token 预算（默认 1500）")
    ap.add_argument("--head", type=int, default=None, help="强制保留开头行数（默认 12）")
    ap.add_argument("--tail", type=int, default=None, help="强制保留结尾行数（默认 8）")
    ap.add_argument("--max-line", type=int, default=None, help="单行截断长度，0 表示不截断")
    ap.add_argument("--profile", default=None,
                    choices=sorted(comp.PROFILES) + ["auto"], help="按输出类型预设参数")
    ap.add_argument("--no-keep-errors", action="store_true", help="允许省略错误行")
    ap.add_argument("--strict", action="store_true", help="预算改为硬上限，超了丢低分行")
    ap.add_argument("--stats", action="store_true", help="只打印统计，不输出正文")
    ap.add_argument("--json", action="store_true", help="统计以 JSON 写到 stderr")
    ap.add_argument("--out", help="正文写入文件而不是 stdout")
    ap.add_argument("--max-bytes", type=int, default=MAX_BYTES, help="读取上限，默认 64MB")
    ap.add_argument("--encoding", default="auto", choices=VALID_ENCODINGS,
                    help="输入编码，默认自动识别（UTF-8/GB18030/UTF-16）")
    args = ap.parse_args(argv)

    try:
        text, nbytes, cut, used = comp.load_input(args.file, args.max_bytes, args.encoding)
    except FileNotFoundError:
        print(f"找不到文件：{args.file}", file=sys.stderr)
        return EXIT_INPUT
    except (OSError, ValueError) as exc:
        print(f"读取失败：{exc}", file=sys.stderr)
        return EXIT_INPUT

    profile = args.profile or "auto"
    if profile == "auto":
        profile = comp.detect_profile(text)
    preset = comp.PROFILES[profile]

    budget = args.budget if args.budget is not None else preset["budget"]
    max_line = args.max_line if args.max_line is not None else preset["max_line"]
    head = args.head if args.head is not None else preset["head"]
    tail = args.tail if args.tail is not None else preset["tail"]

    try:
        result = comp.compress(
            text.splitlines(), budget=budget, head=head, tail=tail,
            max_line=max_line, keep_errors=not args.no_keep_errors,
            strict=args.strict, profile=profile,
        )
    except ValueError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        return EXIT_USAGE

    stats = result.stats
    stats.input_bytes = nbytes
    stats.truncated_input = cut
    stats.encoding = used

    body = result.text
    if args.file not in ("-", None):
        body += f"\n…[原文 {args.file}，共 {stats.raw_lines} 行]…"

    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(body + "\n")
        except OSError as exc:
            print(f"写入失败：{exc}", file=sys.stderr)
            return EXIT_OUTPUT
    elif not args.stats:
        print(body)

    if args.json:
        print(json.dumps(stats.as_dict(), ensure_ascii=False), file=sys.stderr)
    else:
        over = " [超预算]" if stats.over_budget and args.strict is False else ""
        print(
            f"[{stats.raw_lines:,} 行 → {stats.kept_lines:,} 行 | "
            f"{stats.raw_tokens:,} tk → {stats.out_tokens:,} tk | "
            f"省 {stats.ratio * 100:.0f}% | 模式 {profile}{over}]",
            file=sys.stderr,
        )
    if cut:
        print(f"[输入超过 {args.max_bytes:,} 字节，已截断]", file=sys.stderr)
    return EXIT_OK


def audit_main(argv: list[str] | None = None) -> int:
    ap = _parser("tk-audit", "给文件/目录/标准输入做 token 体检")
    ap.add_argument("paths", nargs="*", help="文件路径，- 表示 stdin")
    ap.add_argument("--dir", help="目录递归体检")
    ap.add_argument("--top", type=int, default=5, help="每文件列出几个最大块，0 关闭")
    ap.add_argument("--max-files", type=int, default=200)
    ap.add_argument("--exclude", action="append", default=[], help="排除 glob，可重复")
    ap.add_argument("--ext", action="append", default=[], help="只体检这些扩展名，可重复")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--csv", action="store_true")
    ap.add_argument("--encoding", default="auto", choices=VALID_ENCODINGS)
    args = ap.parse_args(argv)

    targets = list(args.paths)
    if args.dir:
        if not os.path.isdir(args.dir):
            print(f"目录不存在：{args.dir}", file=sys.stderr)
            return EXIT_INPUT
        exts = [e.lower().lstrip(".") for e in args.ext]
        targets += list(audit_mod.iter_files(args.dir, args.max_files, args.exclude, exts))
    if not targets:
        ap.print_help()
        return EXIT_USAGE

    reports = []
    for t in targets:
        try:
            from .text import read_text
            data, _, used = read_text(t, encoding=args.encoding)
            reports.append(audit_mod.audit_text(t, data, args.top, used))
        except Exception as exc:  # noqa: BLE001 - 单个文件失败不该中断整批
            print(f"跳过 {t}: {exc}", file=sys.stderr)

    if args.json:
        print(audit_mod.report_to_json(reports))
        return EXIT_OK
    if args.csv:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["name", "lines", "chars", "tokens", "dup_lines",
                         "long_lines", "progress_lines", "est_waste_tokens"])
        for r in reports:
            writer.writerow([r.name, r.lines, r.chars, r.tokens, r.dup_lines,
                             r.long_lines, r.progress_lines, r.est_waste_tokens])
        sys.stdout.write(buf.getvalue())
        return EXIT_OK

    for r in reports:
        print(audit_mod.render(r))
        print()
    print(audit_mod.render_totals(reports))
    return EXIT_OK


def pack_main(argv: list[str] | None = None) -> int:
    ap = _parser("tk-pack", "给目录生成索引卡（渐进式披露第一屏）")
    ap.add_argument("root")
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--max-files", type=int, default=120)
    ap.add_argument("--include", action="append", default=[])
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("-o", "--out")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--encoding", default="auto", choices=VALID_ENCODINGS)
    args = ap.parse_args(argv)

    if not os.path.isdir(args.root):
        print(f"目录不存在：{args.root}", file=sys.stderr)
        return EXIT_INPUT

    card, entries = pack_mod.build_card(
        args.root, args.depth, args.max_files, args.include, args.exclude, args.encoding
    )
    if args.json:
        payload = pack_mod.to_json(args.root, entries)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(payload + "\n")
        else:
            print(payload)
        return EXIT_OK
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(card)
        print(f"已写入 {args.out}（{len(entries)} 文件）", file=sys.stderr)
    else:
        print(card)
    return EXIT_OK


def handover_main(argv: list[str] | None = None) -> int:
    ap = _parser("tk-handover", "跨会话交接单：生成 / 校验 / 展示")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new", help="生成模板")
    p_new.add_argument("path")
    p_new.add_argument("--force", action="store_true", help="已存在也覆盖")
    p_new.add_argument("--template", help="使用自定义模板文件")

    p_check = sub.add_parser("check", help="校验")
    p_check.add_argument("path")
    p_check.add_argument("--max-tokens", type=int, default=handover_mod.DEFAULT_MAX_TOKENS)
    p_check.add_argument("--json", action="store_true")
    p_check.add_argument("--encoding", default="auto", choices=VALID_ENCODINGS)

    p_show = sub.add_parser("show", help="打印并估算")
    p_show.add_argument("path")
    p_show.add_argument("--json", action="store_true")
    p_show.add_argument("--encoding", default="auto", choices=VALID_ENCODINGS)

    args = ap.parse_args(argv)

    if args.cmd == "new":
        template = None
        if args.template:
            with open(args.template, encoding="utf-8") as fh:
                template = fh.read()
        if handover_mod.create(args.path, args.force, template):
            print(f"已存在，不覆盖：{args.path}（用 --force 覆盖）", file=sys.stderr)
            return EXIT_FAIL
        print(f"已创建：{args.path}")
        return EXIT_OK

    try:
        if args.cmd == "check":
            report = handover_mod.check(args.path, args.max_tokens, args.encoding)
            if args.json:
                print(report.to_json())
            else:
                for issue in report.issues:
                    print(f"[{issue.level}] {issue.message}")
                print(f"{'通过' if report.ok else '未通过'}："
                      f"{report.tokens} token / {report.lines} 行")
            return EXIT_OK if report.ok else EXIT_FAIL
        from .text import read_text
        text, _, _ = read_text(args.path, encoding=args.encoding)
        if args.json:
            print(json.dumps({"path": args.path,
                              "tokens": handover_mod.est_tokens(text),
                              "text": text}, ensure_ascii=False, indent=2))
        else:
            print(text)
            print(f"---\n[估算 {handover_mod.est_tokens(text)} token / "
                  f"{len(text.splitlines())} 行]", file=sys.stderr)
        return EXIT_OK
    except FileNotFoundError:
        print(f"找不到文件：{args.path}", file=sys.stderr)
        return EXIT_INPUT


def doctor_main(argv: list[str] | None = None) -> int:
    ap = _parser("tk-doctor", "检查安装状态与运行环境")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    result = doctor_mod.run()
    print(doctor_mod.dumps(result) if args.json else doctor_mod.render(result))
    return EXIT_OK if result["ok"] else EXIT_FAIL


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print("用法: python -m token_saver {compress|audit|pack|handover|doctor} ...")
        return EXIT_USAGE if not argv else EXIT_OK
    cmd, rest = argv[0], argv[1:]
    table = {"compress": compress_main, "tk": compress_main, "audit": audit_main,
             "pack": pack_main, "handover": handover_main, "doctor": doctor_main}
    if cmd not in table:
        print(f"未知子命令：{cmd}", file=sys.stderr)
        return EXIT_USAGE
    return table[cmd](rest)
