"""Render a small, self-contained Mia and the Lost Kite animation.

This is deliberately local-only: Pillow draws the frames, macOS ``say`` creates
English narration, and ffmpeg produces the H.264/AAC MP4.  It never uploads or
publishes media.  The scene data is fixed and the command accepts only a
sample/full selection, not shell fragments or review text.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT, FPS = 1920, 1080, 30
VOICE = "Samantha"
VOICE_RATE = "145"
PAUSE = 0.45


@dataclass(frozen=True)
class Scene:
    narration: str
    title: str
    kind: str


SCENES = (
    Scene("Mia loved flying her bright red kite in the sunny park.", "A sunny park", "fly"),
    Scene("She ran across the grass while Pip, her cheerful puppy, raced beside her.", "A happy run", "run"),
    Scene("Then a strong wind lifted the kite high and carried it toward a tall tree.", "The wind rises", "wind"),
    Scene("The kite caught on a branch. Mia stopped and looked up, but she did not climb.", "Safe hands stay safe", "tree"),
    Scene("Pip tugged the string gently, yet the kite stayed out of reach.", "Pip has an idea", "tug"),
    Scene("Mia waved to a park helper and explained the problem with a calm voice.", "Ask for help", "ask"),
    Scene("The helper brought a long safety pole, and Mia held the kite string far away.", "A safe plan", "helper"),
    Scene("Pip wagged his tail as the pole lifted the branch, slowly and carefully.", "Slow and careful", "reach"),
    Scene("The wind softened. The kite slipped free and floated down into Mia's hands.", "The kite comes home", "free"),
    Scene("Mia thanked the helper, and Pip danced around the kite in a happy circle.", "Thank you", "dance"),
    Scene("Together they chose a wide open field, far from trees, for the next flight.", "Choose an open place", "field"),
    Scene("Mia smiled. When a problem comes, stay safe, ask for help, and try again.", "Try again safely", "close"),
)


def run(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def duration(path: Path) -> float:
    result = run(["ffprobe", "-v", "error", "-show_entries", "stream=duration:format=duration",
                  "-of", "default=noprint_wrappers=1:nokey=1", str(path)]).stdout.splitlines()
    values = [float(value) for value in result if value.strip() and value.strip() != "N/A"]
    if not values:
        raise RuntimeError(f"ffprobe could not read duration for {path}")
    return max(values)


def make_audio(scenes: tuple[Scene, ...], root: Path) -> tuple[Path, list[tuple[float, float]]]:
    files: list[Path] = []
    timeline: list[tuple[float, float]] = []
    silence = root / "silence.wav"
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(PAUSE),
         "-c:a", "pcm_s16le", str(silence)])
    for index, scene in enumerate(scenes, 1):
        path = root / f"voice_{index:02d}.aiff"
        run(["say", "-v", VOICE, "-r", VOICE_RATE, "-o", str(path), scene.narration])
        files.append(path)
    cursor = 0.0
    concat = root / "audio.concat.txt"
    rows = []
    for index, path in enumerate(files):
        seconds = duration(path)
        timeline.append((cursor, cursor + seconds))
        rows.append(f"file '{path.as_posix()}'")
        cursor += seconds
        if index != len(files) - 1:
            rows.append(f"file '{silence.as_posix()}'")
            cursor += PAUSE
    minimum = 60.0 if len(scenes) == len(SCENES) else 0.0
    if cursor < minimum:
        tail = root / "tail_silence.wav"
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
             "-t", str(minimum - cursor + 0.1), "-c:a", "pcm_s16le", str(tail)])
        rows.append(f"file '{tail.as_posix()}'")
    concat.write_text("\n".join(rows) + "\n", encoding="utf-8")
    audio = root / "narration.wav"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-c:a", "pcm_s16le", str(audio)])
    return audio, timeline


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf"
    return ImageFont.truetype(path, size)


def draw_scene(t: float, scene: Scene, subtitle: str, scene_index: int) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), (131, 201, 235))
    draw = ImageDraw.Draw(image)
    horizon = int(650 + 22 * __import__("math").sin(t * 0.7))
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        color = (int(105 + 55 * ratio), int(190 + 30 * ratio), int(235 - 25 * ratio))
        draw.line((0, y, WIDTH, y), fill=color)
    draw.ellipse((1540, 85, 1740, 285), fill=(255, 230, 126), outline=(255, 244, 185), width=8)
    draw.rectangle((0, horizon, WIDTH, HEIGHT), fill=(92, 177, 93))
    draw.line((0, horizon + 60, WIDTH, horizon + 20), fill=(58, 144, 73), width=12)
    # Tree and moving branches.
    tree_x = 1450
    draw.rectangle((tree_x - 65, 330, tree_x + 20, horizon + 30), fill=(112, 73, 42))
    sway = int(28 * __import__("math").sin(t * 2.7 + scene_index))
    draw.line((tree_x, 420, tree_x - 270 + sway, 300), fill=(112, 73, 42), width=30)
    draw.line((tree_x - 80, 390, tree_x + 230 + sway, 265), fill=(112, 73, 42), width=25)
    for cx, cy, rx, ry in [(1230+sway, 280, 220, 120), (1510+sway, 220, 240, 130), (1720+sway, 330, 230, 145)]:
        draw.ellipse((cx-rx, cy-ry, cx+rx, cy+ry), fill=(48, 145, 78), outline=(29, 119, 65), width=8)
    # Park bench.
    draw.rectangle((290, horizon - 40, 650, horizon + 5), fill=(145, 91, 48))
    draw.rectangle((305, horizon + 8, 330, horizon + 100), fill=(96, 65, 42))
    draw.rectangle((610, horizon + 8, 635, horizon + 100), fill=(96, 65, 42))

    progress = min(1.0, max(0.0, t / 7.0))
    mia_x = 280 + 180 * __import__("math").sin(t * 0.75)
    if scene.kind in {"run", "wind", "tree", "tug", "ask", "helper", "reach", "free", "dance", "field", "close"}:
        mia_x += 80 * progress
    mia_y = horizon - 190
    # Mia: head, hair, dress, moving arms/legs.
    draw.ellipse((mia_x-42, mia_y-110, mia_x+42, mia_y-26), fill=(255, 210, 170), outline=(65, 45, 40), width=6)
    draw.pieslice((mia_x-48, mia_y-120, mia_x+48, mia_y-35), 180, 355, fill=(91, 53, 38))
    draw.polygon([(mia_x-64, mia_y-25), (mia_x+64, mia_y-25), (mia_x+92, mia_y+125), (mia_x-92, mia_y+125)], fill=(225, 89, 113), outline=(115, 48, 75))
    arm_wave = 45 * __import__("math").sin(t * 3.0)
    draw.line((mia_x-38, mia_y+5, mia_x-100, mia_y+55+arm_wave), fill=(255, 210, 170), width=20)
    draw.line((mia_x+38, mia_y+5, mia_x+105, mia_y+45-arm_wave), fill=(255, 210, 170), width=20)
    draw.line((mia_x-30, mia_y+120, mia_x-62, horizon+35), fill=(52, 61, 92), width=24)
    draw.line((mia_x+30, mia_y+120, mia_x+65, horizon+35), fill=(52, 61, 92), width=24)
    # Pip moves and jumps during the retrieval scenes.
    pip_x = mia_x + 150 + 45 * __import__("math").sin(t * 2.0)
    jump = 55 * abs(__import__("math").sin(t * 2.5)) if scene.kind in {"tug", "reach", "dance"} else 0
    pip_y = horizon - 70 - jump
    draw.ellipse((pip_x-75, pip_y-55, pip_x+75, pip_y+45), fill=(201, 145, 83), outline=(90, 57, 35), width=7)
    draw.ellipse((pip_x+45, pip_y-95, pip_x+125, pip_y-10), fill=(201, 145, 83), outline=(90, 57, 35), width=7)
    draw.polygon([(pip_x+55, pip_y-80), (pip_x+20, pip_y-145), (pip_x+82, pip_y-105)], fill=(160, 102, 60))
    draw.ellipse((pip_x+95, pip_y-62, pip_x+108, pip_y-49), fill=(20, 20, 20))
    draw.line((pip_x-45, pip_y+35, pip_x-65, horizon+40), fill=(90, 57, 35), width=16)
    draw.line((pip_x+40, pip_y+35, pip_x+55, horizon+40), fill=(90, 57, 35), width=16)
    # Kite and string animate by scene.
    if scene.kind in {"tree", "tug", "ask", "helper", "reach"}:
        kite_x, kite_y = tree_x - 145 + sway, 315 + 20 * __import__("math").sin(t * 2.2)
    elif scene.kind in {"free", "dance", "field", "close"}:
        kite_x, kite_y = mia_x + 120, mia_y - 210 - 45 * __import__("math").sin(t * 2.0)
    else:
        kite_x, kite_y = mia_x + 160 + 160 * __import__("math").sin(t * 0.8), mia_y - 230 - 45 * __import__("math").sin(t * 2.0)
    kite = [(kite_x, kite_y-65), (kite_x+65, kite_y), (kite_x, kite_y+65), (kite_x-65, kite_y)]
    draw.polygon(kite, fill=(235, 66, 75), outline=(120, 34, 48))
    draw.line((kite_x, kite_y-65, kite_x, kite_y+65), fill=(255, 226, 115), width=8)
    draw.line((kite_x-65, kite_y, kite_x+65, kite_y), fill=(255, 226, 115), width=8)
    draw.arc((kite_x-55, kite_y+45, kite_x+100, kite_y+180), 180, 350, fill=(255, 226, 115), width=6)
    draw.line((mia_x+70, mia_y+8, kite_x, kite_y+70), fill=(45, 45, 55), width=4)
    if scene.kind in {"helper", "reach"}:
        helper_x = 1030
        helper_y = horizon - 190
        draw.ellipse((helper_x-38, helper_y-92, helper_x+38, helper_y-16), fill=(248, 197, 154), outline=(65, 45, 40), width=6)
        draw.rectangle((helper_x-55, helper_y-8, helper_x+55, helper_y+120), fill=(47, 123, 160), outline=(35, 75, 100), width=6)
        draw.line((helper_x-35, helper_y+120, helper_x-55, horizon+35), fill=(45, 52, 75), width=18)
        draw.line((helper_x+35, helper_y+120, helper_x+55, horizon+35), fill=(45, 52, 75), width=18)
        draw.line((helper_x-30, helper_y+22, helper_x-80, helper_y+65), fill=(248, 197, 154), width=16)
        draw.line((helper_x+30, helper_y+22, helper_x+68, helper_y+58), fill=(248, 197, 154), width=16)
        draw.line((helper_x+45, helper_y+55, kite_x, kite_y+25), fill=(112, 73, 42), width=13)
    # Distinct shot transition marker: colored circle wipes at scene boundaries.
    if t < 0.6:
        alpha = int(180 * (1 - t / 0.6))
        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, alpha))
        image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(image)
    if subtitle:
        panel_top = HEIGHT - 180
        draw.rounded_rectangle((100, panel_top, WIDTH-100, HEIGHT-45), radius=28, fill=(15, 34, 57), outline=(250, 230, 150), width=3)
        wrapped = subtitle
        draw.text((WIDTH//2, panel_top+68), wrapped, font=font(42, bold=True), fill=(255,255,255), anchor="mm", align="center")
    return image


def write_srt(scenes: tuple[Scene, ...], timeline: list[tuple[float, float]], path: Path) -> None:
    lines = []
    for index, (scene, (start, end)) in enumerate(zip(scenes, timeline), 1):
        def stamp(value: float) -> str:
            ms = int(round(value * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
        lines += [str(index), f"{stamp(start)} --> {stamp(end)}", scene.narration, ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def render_video(scenes: tuple[Scene, ...], timeline: list[tuple[float, float]], audio: Path, srt: Path, output: Path, root: Path) -> None:
    total = duration(audio)
    process = subprocess.Popen(["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS), "-i", "-",
                                "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                                "-pix_fmt", "yuv420p", str(root / "video_only.mp4")], stdin=subprocess.PIPE)
    assert process.stdin is not None
    frame_count = int(total * FPS)
    for frame in range(frame_count):
        current = frame / FPS
        index = next((i for i, (_, end) in enumerate(timeline) if current <= end + PAUSE), len(scenes)-1)
        start = timeline[index][0]
        image = draw_scene(current - start, scenes[index], scenes[index].narration if current <= timeline[index][1] else "", index)
        process.stdin.write(image.tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("video frame encoding failed")
    command = ["ffmpeg", "-y", "-i", str(root / "video_only.mp4"), "-i", str(audio), "-i", str(srt),
               "-map", "0:v:0", "-map", "1:a:0", "-map", "2:0", "-c:v", "copy", "-c:a", "aac",
               "-b:a", "128k", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng"]
    if len(scenes) == len(SCENES):
        command += ["-af", "apad=pad_dur=60", "-t", "60.2"]
    else:
        command += ["-shortest"]
    run(command + [str(output)])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sample", action="store_true", help="render the first two scenes only")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    selected = SCENES[:3] if args.sample else SCENES
    with tempfile.TemporaryDirectory(prefix="mia-kite-") as temporary:
        root = Path(temporary)
        audio, timeline = make_audio(selected, root)
        srt = args.output_dir / ("mia_lost_kite_sample.srt" if args.sample else "mia_lost_kite.srt")
        write_srt(selected, timeline, srt)
        output = args.output_dir / ("mia_lost_kite_sample.mp4" if args.sample else "mia_lost_kite.mp4")
        render_video(selected, timeline, audio, srt, output, root)
        report = args.output_dir / ("sample_validation.txt" if args.sample else "validation.txt")
        report.write_text(f"output={output}\nduration_seconds={duration(output):.3f}\nsize=1920x1080\nframerate=30\ncodec=h264/aac\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
