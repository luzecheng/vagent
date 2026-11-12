"""Tidy finished episode folders: keep one Chinese video, one English video and publish_notes.md at the top of
each folder; move what the pipeline itself generated (storyboard, voice, frames, covers, logs, check images, extra
versions) to the Trash.  Any file it does not recognise as generated (a photo the user dropped in, say) is left
where it is and listed, never thrown away.

    python3 clean_output.py <output folder or one episode folder>        # show the plan
    python3 clean_output.py <output folder or one episode folder> --go   # do it
"""
import fnmatch
import subprocess
import sys
from pathlib import Path

ZH = ["robot2/robot2_portrait.mp4", "robot2_portrait.mp4", "story_portrait.mp4", "zh_shipinhao.mp4", "story_landscape.mp4"]
EN = ["robot2/robot2_en_landscape.mp4", "robot2_en_landscape.mp4", "story_en_landscape.mp4", "en_x_9x16.mp4", "story_en_portrait.mp4"]


# what vagent writes into an episode folder (paths relative to it); anything else belongs to the user
GENERATED = [
    "storyboard.json", "timeline*.json", "qa*.md", "*.log", "report.md", "run.log.jsonl", "questions.md",
    "draft*.png", "contact_sheet*.png", "cover*.png", "*.mp4", ".DS_Store", "build/*", "part*/*",
    "robot2/beats.py", "robot2/__pycache__/*", "robot2/*.log", "robot2/cover*.png", "robot2/*.mp4",
    "robot2/frames/*",
    "robot2/review/sheet*.png", "robot2/review/shotlist.md", "robot2/review/props_prompt.txt",
    "robot2/review/codex.log", "robot2/.DS_Store", "robot2/review/.DS_Store",
    "robot2/review/f*.png", "robot2/review/g*.png", "robot2/review/frames*.png",
    "robot2/review/crop*.png", "robot2/review/*预览*.png", "robot2/review/*对比*.png", "robot2/review/*试听*",
]


def generated(rel: str) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in GENERATED)


def is_episode(d: Path) -> bool:
    return any((d / c).exists() for c in ZH + EN + ["publish_notes.md"])


def clean(d: Path, go: bool) -> None:
    keep = [next((d / c for c in cands if (d / c).exists()), None) for cands in (ZH, EN)]
    keep = [k for k in keep if k] + ([d / "publish_notes.md"] if (d / "publish_notes.md").exists() else [])
    names = {k.name for k in keep}
    print(f"{d.name}: 保留 {[k.relative_to(d).as_posix() for k in keep]}")
    if not go:
        return
    for k in keep:                        # videos inside robot2/ come up to the folder's top level
        if k.parent != d:
            k.rename(d / k.name)
    files = [p for p in d.rglob("*") if p.is_file() and not (p.parent == d and p.name in names)]
    junk = [p for p in files if generated(p.relative_to(d).as_posix())]
    mine = [p for p in files if p not in junk]
    if junk:
        subprocess.run(["trash", *map(str, junk)], check=True)
    for sub in sorted((p for p in d.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(sub.iterdir()):        # folders left empty go too
            sub.rmdir()
    for p in mine:
        print(f"   未识别、已保留：{p.relative_to(d).as_posix()}")

if __name__ == "__main__":
    target, go = Path(sys.argv[1]), "--go" in sys.argv
    folders = [target] if is_episode(target) else sorted(p for p in target.iterdir() if p.is_dir() and is_episode(p))
    for d in folders:
        clean(d, go)
