from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .core.config import DEFAULTS, SECRET_KEYS, Store
from .ingest.bilibili import BiliError, BilibiliClient


def _debug(message: str) -> None:
    path = os.environ.get("VNOTE_DEBUG_LOG")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except OSError:
        pass


def _setup_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _fmt_duration(seconds: int) -> str:
    seconds = int(seconds or 0)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def cmd_config(args: argparse.Namespace) -> int:
    store = Store()
    if args.action == "list":
        merged = {"***" + k: "" for k in DEFAULTS}
        for key, value in sorted(store.all_settings().items()):
            print(f"{key} = {value}")
        for key in sorted(store.secret_keys()):
            print(f"{key} = ******** (已设置)")
    elif args.action == "get":
        if args.key in SECRET_KEYS:
            value = store.get_secret(args.key)
            print("********" if value else "(未设置)")
        else:
            print(store.get(args.key, ""))
    elif args.action == "set":
        if args.key in SECRET_KEYS:
            store.set_secret(args.key, args.value)
        else:
            store.set(args.key, args.value)
        print(f"已保存 {args.key}")
    elif args.action == "unset":
        store.delete_secret(args.key)
        print(f"已删除 {args.key}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from .core.config import Store
    from .pipeline.runner import BuildOptions, build

    store = Store()
    options = BuildOptions(
        out_root=Path(args.out) if args.out else None,
        index=args.index,
        keep_video=args.keep,
        title=args.title or None,
        force=args.force,
    )
    try:
        result = build(args.source, store, options, progress=lambda message: print(f"  {message}", flush=True))
    except Exception as exc:  # noqa: BLE001
        print(f"构建失败：{exc}", file=sys.stderr)
        return 2
    print("")
    print(f"笔记：{result.notes_path}")
    print(f"标题：{result.title}")
    if result.warnings:
        print("质检提示：" + "；".join(result.warnings))
    return 0


def cmd_bili(args: argparse.Namespace) -> int:
    store = Store()
    client = BilibiliClient(cookie=store.get_secret("bilibili_cookie") or "")
    try:
        if args.action == "parse":
            target = client.resolve(args.url)
            print(json.dumps(target.__dict__, ensure_ascii=False, indent=2))
            return 0

        season, refs = client.enumerate(args.url)
        if season and season.title:
            print(f"合集: {season.title} (season_id={season.season_id})")
        if season and season.intro:
            print(f"简介: {season.intro[:120]}")
        total = sum(ref.duration for ref in refs)
        print(f"共 {len(refs)} 个视频，总时长 {_fmt_duration(total)}")
        for index, ref in enumerate(refs, 1):
            print(f"{index:>3}. {ref.bvid}  {_fmt_duration(ref.duration):>7}  {ref.title}")
        if args.out:
            payload = {
                "season": season.__dict__ if season else None,
                "videos": [ref.to_dict() for ref in refs],
            }
            with open(args.out, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            print(f"已写入 {args.out}")
        return 0
    except (BiliError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    finally:
        client.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vnote", description="视频转学习笔记工具")
    sub = parser.add_subparsers(dest="command", required=True)

    config = sub.add_parser("config", help="配置管理")
    config_sub = config.add_subparsers(dest="action", required=True)
    config_sub.add_parser("list", help="列出配置")
    get_parser = config_sub.add_parser("get")
    get_parser.add_argument("key")
    set_parser = config_sub.add_parser("set")
    set_parser.add_argument("key")
    set_parser.add_argument("value")
    unset_parser = config_sub.add_parser("unset")
    unset_parser.add_argument("key")

    sub.add_parser("app", help="启动桌面界面")

    build_parser = sub.add_parser("build", help="从视频/链接生成一篇笔记")
    build_parser.add_argument("source", help="本地视频路径或 B 站链接")
    build_parser.add_argument("--out", default="", help="输出根目录")
    build_parser.add_argument("--index", type=int, default=0, help="合集里第几个视频（从 0 开始）")
    build_parser.add_argument("--keep", action="store_true", help="保留源视频和音频")
    build_parser.add_argument("--title", default="", help="指定视频标题")
    build_parser.add_argument("--force", action="store_true", help="忽略缓存，重新下载和转写")

    bili = sub.add_parser("bili", help="B 站链接处理")
    bili_sub = bili.add_subparsers(dest="action", required=True)
    parse_parser = bili_sub.add_parser("parse")
    parse_parser.add_argument("url")
    list_parser = bili_sub.add_parser("list")
    list_parser.add_argument("url")
    list_parser.add_argument("--out", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    _setup_stdio()
    _debug(f"main start argv={argv!r}")
    parser = build_parser()
    args = parser.parse_args(argv)
    _debug(f"parsed command={args.command}")
    if args.command == "config":
        return cmd_config(args)
    if args.command == "bili":
        return cmd_bili(args)
    if args.command == "build":
        return cmd_build(args)
    if args.command == "app":
        _debug("importing run")
        from .app.main import run

        _debug("calling run")
        code = run()
        _debug(f"run returned {code}")
        return code
    parser.print_help()
    return 1

if __name__ == "__main__":
    raise SystemExit(main())