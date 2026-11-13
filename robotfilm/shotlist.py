"""Shot list of a robot film, read back from the episode's beats: per shot its size, what the camera does, what
moves in it and how it hands over to the next, plus warnings for the things a good film avoids (three shots of
the same size in a row, a shot where nothing moves).

    .venv/bin/python -m robotfilm.shotlist <episode folder>      # writes robot2/review/shotlist.md
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .compose import merged_timeline
from .robot_story import FORMATS, Film, load_beats

SIZE_ZH = {"full": "全景", "medium": "中景", "close": "近景"}
ANGLE_ZH = {"side": "侧面", "front": "正面", "back": "背后", "three_quarter": "斜前方", "low": "仰拍", "high": "俯拍",
            "over_shoulder": "过肩"}
MAX_ANGLES = 2                   # other camera angles per film: once or twice, never more (the user, 2026-11-12)
MAX_SHOT_S = 14.0                # longer shots need explicit micro-actions or a split
CAMERA_ZH = {"follow": "跟拍", "hold": "固定", "push in": "推近", "pull out": "拉远", "wait": "固定等它走进来"}


def rows(film: Film) -> list[dict]:
    out = []
    for i, s in enumerate(film.shots):
        b = film.beat(i)
        dur = s["end"] - s["start"]
        w = min(b.get("walk", 0.0), dur)
        if b.get("enter") and w > 0:
            camera = "wait"
        elif w > 0:
            camera = "follow"
        else:
            z0, z1 = film.camera(s["start"] + 1e-3)[0], film.camera(s["end"] - 1e-3)[0]
            camera = "push in" if z1 > z0 * 1.03 else "pull out" if z1 < z0 / 1.03 else "hold"
        moves = []
        if b.get("enter") and w > 0:
            moves.append("walks in")
        elif w > 0:
            moves.append("walks")
        if b.get("leave"):
            moves.append("walks out")
        if b.get("hold"):
            moves.append(f"holds {b['hold'][0]}")
        if b.get("drift"):
            moves.append(f"{b['drift']} drift by")
        if callable(b.get("pose")):
            moves.append("gestures")
        if b.get("actions"):
            moves.append(" / ".join(str(a.get("pose", "stand")) for a in b["actions"]))
        mid = s["start"] + dur / 2
        for st in film.stations:
            if st["t_in"] <= mid <= st["t_out"]:
                for key, word in (("sway", "sways"), ("smoke", "smokes"), ("flicker", "flickers"), ("grow", "grows")):
                    if st.get(key):
                        moves.append(f"{st['name']} {word}")
        if camera in ("push in", "pull out"):
            moves.append("camera")
        nxt = film.beat(i + 1) if i + 1 < len(film.shots) else {}
        cut = b.get("leave") or nxt.get("enter")
        stations = [st for st in film.stations if st["i"] == i]
        overlaps = []
        for left, right in zip(stations, stations[1:]):
            if abs(left["x"] - right["x"]) < (left["w"] + right["w"]) * 0.42:
                overlaps.append(f"{left['name']} / {right['name']}")
        out.append({"id": s["id"], "dur": round(dur, 1), "size": film.shot_size(i), "camera": camera,
                    "angle": b.get("angle") or ("front" if b.get("front") else "side"),
                    "moves": moves, "station_overlaps": overlaps, "words": bool(b.get("fx")),
                    "to_next": "cut" if cut else "continuous",
                    "text": s.get("narration", "")})
    return out


def warnings(rs: list[dict]) -> list[str]:
    w = []
    if rs and not any(m.startswith("walks") or "drift" in m for m in rs[0]["moves"]):
        w.append(f"shot {rs[0]['id']}: the opening only stands there — start moving in the first 2 seconds")
    for a, b, c in zip(rs, rs[1:], rs[2:]):
        same = lambda k: a.get(k, "side") == b.get(k, "side") == c.get(k, "side")
        if same("size") and same("angle"):        # a new angle is a new picture even at the same size
            w.append(f"shots {a['id']}–{c['id']}: three {a['size']} shots in a row")
    others = [r["id"] for r in rs if r.get("angle", "side") not in ("side", "front")]
    if len(others) > MAX_ANGLES:
        w.append(f"shots {', '.join(map(str, others))}: {len(others)} angle changes — keep at most {MAX_ANGLES}, "
                 "at the strongest lines (the user finds more unnatural)")
    for r in rs:
        if not r["moves"]:
            w.append(f"shot {r['id']}: nothing moves (camera holds, no walk, no moving prop)")
        if float(r.get("dur", 0.0)) > MAX_SHOT_S and not any(" / " in move for move in r["moves"]):
            w.append(f"shot {r['id']}: {r['dur']}s is long — split the narration or add a timed actions sequence")
        if r.get("station_overlaps"):
            w.append(f"shot {r['id']}: props overlap ({', '.join(r['station_overlaps'])}) — separate their anchors")
        for move in (move for move in r["moves"] if " / " in move):
            poses = [p.strip() for p in move.split("/")]
            if any(a == b for a, b in zip(poses, poses[1:])):
                w.append(f"shot {r['id']}: repeated adjacent pose in actions — vary the robot's gesture")
    return w


def markdown(rs: list[dict], ws: list[str]) -> str:
    lines = ["# 分镜表（机器人版，自动生成）", "", "| 镜 | 秒 | 景别 | 角度 | 运镜 | 什么在动 | 转场 | 旁白 |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rs:
        moves = "、".join(r["moves"]) or "（无）"
        lines.append(f"| {r['id']} | {r['dur']} | {SIZE_ZH[r['size']]} | {ANGLE_ZH[r['angle']]} | "
                     f"{CAMERA_ZH[r['camera']]} | {moves} | "
                     f"{'切' if r['to_next'] == 'cut' else '连续'} | {r['text'][:18]} |")
    lines += ["", "## 提醒", ""] + ([f"- {x}" for x in ws] or ["- 没有问题"])
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    folder = ap.parse_args(argv).folder.resolve()
    _, W, H = FORMATS["zh"]
    film = Film(folder, merged_timeline(folder, "zh"), W, H, load_beats(folder), "zh", "color")
    rs = rows(film)
    ws = warnings(rs)
    out = folder / "robot2/review/shotlist.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown(rs, ws), encoding="utf-8")
    print(f"wrote {out}")
    for x in ws:
        print("!", x)


if __name__ == "__main__":
    main()
