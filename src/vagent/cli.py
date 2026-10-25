"""vagent command line: run | check | watch | audition | doctor | demo."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from . import config as configmod
from .log import RunLog


def load_env_file() -> None:
    """Machine-local settings (e.g. VAGENT_CLAUDE_PROXY) from <project>/.env; real env vars win."""
    path = configmod.PROJECT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            os.environ.setdefault(name.strip(), value.strip())


def read_script(args) -> tuple[str, str]:
    if args.text:
        return args.text, "text"
    if args.file and args.file != "-":
        path = Path(args.file)
        return path.read_text(encoding="utf-8"), path.stem
    if not sys.stdin.isatty():
        return sys.stdin.read(), "stdin"
    raise SystemExit("no script: give a file, --text \"...\", or pipe text on stdin")


def overrides(args) -> dict:
    out: dict = {}
    if getattr(args, "allow_long", False):
        out.setdefault("duration", {})["allow_long"] = True
    if getattr(args, "disclaimer", None):
        out["disclaimer_override"] = args.disclaimer
    if getattr(args, "landscape", False):
        out.setdefault("video", {})["landscape_16x9"] = True
    return out


def main(argv=None) -> int:
    load_env_file()
    parser = argparse.ArgumentParser(prog="vagent", description="Chinese script in, zh + en short videos out.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="produce videos for one script")
    run.add_argument("file", nargs="?", help="script .txt/.md, or - for stdin")
    run.add_argument("--text", help="script text inline")
    run.add_argument("--out", help="output directory (default output/YYYY-MM-DD_<slug>)")
    run.add_argument("--allow-long", action="store_true", help="render past the 140s hard cap instead of pausing")
    run.add_argument("--disclaimer", choices=["on", "off"], help="force the disclaimer on or off")
    run.add_argument("--landscape", action="store_true", help="also render en_x_16x9.mp4")
    run.add_argument("--stage", choices=["audio", "plan", "all"], default="all", help="stop after this stage")
    chk = sub.add_parser("check", help="rerun the automatic checks on an output folder and rewrite its report.md")
    chk.add_argument("folder")
    wat = sub.add_parser("watch", help="make videos for every script dropped into the inbox folder")
    wat.add_argument("--once", action="store_true", help="process what is in the inbox now, then exit")
    wat.add_argument("--interval", type=float, default=5.0, help="seconds between scans")
    aud = sub.add_parser("audition", help="blind Chinese voice samples")
    aud.add_argument("--out", default="output/audition")
    sub.add_parser("doctor", help="check dependencies")
    dem = sub.add_parser("demo", help="render the component gallery reel and safe-area images")
    dem.add_argument("--out", default="output/phase2_demo/gallery")
    dem.add_argument("--narrated", help="a phase-1 run directory: render its first sentences with real narration")
    args = parser.parse_args(argv)
    config = configmod.load(overrides(args))

    if args.command == "doctor":
        from .doctor import check

        return check(config)
    if args.command == "demo":
        from .render import demo

        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        if args.narrated:
            print(demo.narrated_demo(Path(args.narrated), out / "narrated_zh.mp4", config, RunLog()))
            return 0
        for lang in ("zh", "en"):
            print(demo.gallery_reel(lang, out / f"gallery_{lang}.mp4", config, RunLog()))
            print(demo.safe_area_overlay(lang, out / f"safe_area_{lang}.png", config))
        return 0
    if args.command == "check":
        from .qa import report

        folder = Path(args.folder)
        data = report.write(folder, config, report.title_of(folder), RunLog(folder / "run.log.jsonl"))
        marks = report.attention(data)
        for level, text in marks:
            print(f"{report.ICON[level]} {text}")
        errors = sum(1 for level, _ in marks if level == "error")
        print(f"{folder / 'report.md'}: {errors} must-fix, {len(marks) - errors} to review")
        return 1 if errors else 0
    if args.command == "watch":
        from .inbox import AlreadyRunning, Lock, Watcher

        inbox = Path(config["paths"]["inbox"])
        log = RunLog(Path(config["paths"]["output"]) / "watch.log.jsonl")
        try:
            with Lock(inbox):
                outcomes = Watcher(inbox, Path(config["paths"]["output"]), log=log).run(args.interval, args.once)
        except AlreadyRunning as exc:
            print(exc, file=sys.stderr)
            return 1
        return 1 if any(o.status == "failed" for o in outcomes) else 0
    if args.command == "audition":
        from . import audition

        out = audition.run(Path(args.out), config, RunLog())
        print(f"samples written to {out}")
        return 0
    from .pipeline import run_script
    from .script import frontmatter

    text, origin = read_script(args)
    try:
        options, text = frontmatter.split_front_matter(text)
    except frontmatter.FrontMatterError as exc:
        print(f"script settings: {exc}", file=sys.stderr)
        return 2
    if options:  # settings written in the file; command-line flags still win
        config = configmod.load(configmod._merge(frontmatter.overrides(options), overrides(args)))
    return run_script(text, origin, config, stage=args.stage, out_dir=Path(args.out) if args.out else None)


if __name__ == "__main__":
    sys.exit(main())
