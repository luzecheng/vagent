"""Per-script settings and episode breaks written inside the script file itself.

A script may start with a small settings block (handy for inbox files, where
there is no command line):

    ---
    allow_long: true
    landscape: true
    disclaimer: off
    ---
    正文……

and a line holding only `---` anywhere in the body splits it into episodes.
"""
from __future__ import annotations

import re

import yaml

OPTIONS = ("allow_long", "landscape", "disclaimer")
BREAK = re.compile(r"^[ \t]*-{3,}[ \t]*$", re.M)


class FrontMatterError(ValueError):
    pass


def split_front_matter(raw: str) -> tuple[dict, str]:
    """(options, body). Text that merely begins with an episode break is not a settings block."""
    lines = raw.lstrip("﻿").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, raw
    end = next((i for i in range(1, min(len(lines), 10)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, raw
    try:
        data = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError:
        return {}, raw
    if not isinstance(data, dict):
        return {}, raw
    unknown = sorted(set(data) - set(OPTIONS))
    if unknown:
        raise FrontMatterError(f"开头设置里有不认识的项：{', '.join(map(str, unknown))}（可用：{', '.join(OPTIONS)}）")
    options = {}
    for key in ("allow_long", "landscape"):
        if key in data:
            if not isinstance(data[key], bool):
                raise FrontMatterError(f"{key} 只能写 true 或 false")
            options[key] = data[key]
    if "disclaimer" in data:
        value = data["disclaimer"]
        # YAML reads bare on/off as booleans
        value = {True: "on", False: "off"}.get(value, value) if isinstance(value, bool) else str(value).lower()
        if value not in ("on", "off"):
            raise FrontMatterError("disclaimer 只能写 on 或 off")
        options["disclaimer"] = value
    return options, "\n".join(lines[end + 1:])


def overrides(options: dict) -> dict:
    """Same shape as the command-line overrides."""
    out: dict = {}
    if options.get("allow_long"):
        out.setdefault("duration", {})["allow_long"] = True
    if options.get("disclaimer"):
        out["disclaimer_override"] = options["disclaimer"]
    if options.get("landscape"):
        out.setdefault("video", {})["landscape_16x9"] = True
    return out


def episodes(body: str) -> list[str]:
    """Split on lines holding only `---`; empty parts are dropped."""
    return [part.strip() for part in BREAK.split(body) if part.strip()]
