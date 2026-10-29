"""Narration for a storyboard: synthesize sentence by sentence (vagent's TTS cache and voice settings), then
time every shot, subtitle and quote from the real audio.

A sentence may run across two shots (e.g. "...会崩溃，" / "结果判断错了。"): it is spoken as one sentence, and the
shot boundary inside it is placed at the time the voice reaches that character (from the per-character
timings Whisper alignment gives each cached sentence).

lang "zh" reads each shot's `narration` / `quote`; lang "en" reads `narration_en` / `quote_en` (the English
version: same shots and scenes, its own voice and timing).  Timing units are Han characters (zh) or words (en).
"""
from __future__ import annotations

import re

import numpy as np
import soundfile as sf

from vagent import cache as cachemod
from vagent.audio.narration import _synth_cached
from vagent.script.parse import spoken_text
from vagent.tts import get_provider
from vagent.tts.base import EN_WORD, HAN, SR, Speech, proportional_timings

from . import scenes

LEAD_IN = 1.6      # seconds of walking before the first word
TAIL = 1.8         # after the last word (plus the last shot's `hold`), before the end
VISUAL_LEAD = 0.25 # a shot starts this long before its first word, so the picture leads the voice
SENTENCE_END = {"zh": re.compile(r"[。！？!?；;：:…]+[”’」』）)]*"),
                "en": re.compile(r"[.!?;:…]+[\"'”’)]*(?=\s|$)")}
CLAUSE = {"zh": re.compile(r"[，、,；;：:。！？!?…]+[”’」』）)]*"),
          "en": re.compile(r"[,;:.!?…—]+[\"'”’)]*(?=\s|$)")}
STRIP = "，、,；;：:。…"
DRAFT_RATE = {"zh": 4.3, "en": 2.6}   # Han characters / words per second, for draft timing
FIELDS = {"zh": ("narration", "quote"), "en": ("narration_en", "quote_en")}


def _units_in(text: str, lang: str) -> int:
    """How many timing units (Han characters / words) the voice says for this text."""
    return len((HAN if lang == "zh" else EN_WORD).findall(spoken_text(text, lang)))


def sentence_spans(text: str, lang: str = "zh") -> list[tuple[int, int]]:
    spans, start = [], 0
    for m in SENTENCE_END[lang].finditer(text):
        spans.append((start, m.end()))
        start = m.end()
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


def _pause(sentence: str, pauses: dict, paragraph: bool) -> float:
    if paragraph:
        return pauses["paragraph"]
    end = sentence.rstrip("”’」』）) ")[-1:]
    if end in "？?！!":
        return pauses["question"]
    if end in "：:":
        return pauses["colon"]
    return pauses["sentence"]


def check_script(storyboard: dict, script_text: str) -> None:
    """The narration must be the script, word for word and in order: shots only split it, never edit it."""
    flat = lambda s: re.sub(r"\s+", "", s)
    said, wrote = flat("".join(s["narration"] for s in storyboard["shots"])), flat(script_text)
    if said == wrote:
        return
    at = next((i for i, (x, y) in enumerate(zip(said, wrote)) if x != y), min(len(said), len(wrote)))
    raise ValueError(f"storyboard narration differs from the script at character {at}: "
                     f"storyboard '…{said[max(0, at - 8):at + 12]}…' vs script '…{wrote[max(0, at - 8):at + 12]}…'")


def _draft_speech(text: str, lang: str) -> Speech:
    """Silent stand-in for a sentence, timed by its length: lets the storyboard be previewed before TTS."""
    n = max(1, _units_in(text, lang))
    duration = n / DRAFT_RATE[lang] + 0.1
    return Speech(np.zeros(int(duration * SR), np.float32), proportional_timings(text, lang, 0.05, duration - 0.05),
                  False, engine="draft")


def has_lang(storyboard: dict, lang: str) -> bool:
    return all(s.get(FIELDS[lang][0], "").strip() for s in storyboard["shots"])


def narrate(storyboard: dict, config: dict, log=print, draft: bool = False,
            lang: str = "zh") -> tuple[np.ndarray, dict]:
    """Return (mono voice track at vagent's SR, timeline).  draft=True: no TTS, estimated timing, silent track."""
    shots = storyboard["shots"]
    field, quote_field = FIELDS[lang]
    joiner = "" if lang == "zh" else " "
    texts = [s[field].strip() + (joiner if i + 1 < len(shots) else "") for i, s in enumerate(shots)]
    full = "".join(texts)
    bounds, pos = [], 0                    # each shot's [start, end) character span in `full`
    for t in texts:
        bounds.append((pos, pos + len(t)))
        pos += len(t)
    shot_of = lambda c: next(i for i, (a, b) in enumerate(bounds) if a <= c < b)

    spec = config["tts"][lang]
    speed = float(spec.get("speed", 1.0))
    provider = None if draft else get_provider(spec, config["paths"]["models"])
    cache = cachemod.Cache(config["paths"]["cache"], f"tts/{lang}")
    spoken_sentences = []                   # (script text, audio) per sentence, for the listening check
    pauses = config["tts"]["pause_s"]

    pieces = [np.zeros(int(LEAD_IN * SR), np.float32)]
    cursor = LEAD_IN
    char_time = {}                          # character index in `full` -> time its sound starts
    spans = sentence_spans(full, lang)
    for n, (a, b) in enumerate(spans):
        text = full[a:b].strip()
        if draft:
            speech = _draft_speech(text, lang)
        else:
            speech = _synth_cached(provider, spoken_text(text, lang), lang, spec["voice"], speed, cache)
            spoken_sentences.append((text, speech.audio))
        units = speech.units
        for c in range(a, b):
            k = _units_in(full[a:c], lang) if c > a else 0
            u = units[min(k, len(units) - 1)]
            char_time[c] = cursor + (u.start if k < len(units) else u.end)
        char_time[b] = cursor + (units[-1].end if units else speech.duration)
        pieces.append(speech.audio)
        cursor += speech.duration
        if not draft:
            log(f"tts  {n + 1}/{len(spans)}  {speech.duration:4.1f}s  {text}")
        if n + 1 < len(spans):
            i_now, i_next = shot_of(b - 1), shot_of(b)
            new_act = i_next != i_now and shots[i_next].get("act") != shots[i_now].get("act")
            gap = _pause(text, pauses, new_act)
            if i_next != i_now:             # a shot ends here: give its action the time it needs
                begun = LEAD_IN if i_now == 0 else char_time[bounds[i_now][0]] - VISUAL_LEAD
                need = scenes.get(shots[i_now]["scene"]).MIN_S + float(shots[i_now].get("hold", 0))
                gap = max(gap, begun + need + VISUAL_LEAD - cursor)
            pieces.append(np.zeros(int(gap * SR), np.float32))
            cursor += gap
    last = shots[-1]
    end_pad = float(last.get("hold", 0)) + TAIL
    pieces.append(np.zeros(int(end_pad * SR), np.float32))
    audio = np.concatenate(pieces)
    duration = len(audio) / SR

    timeline = []
    for i, s in enumerate(shots):
        a, b = bounds[i]
        start = 0.0 if i == 0 else char_time[a] - VISUAL_LEAD
        timeline.append({**s, "start": round(start, 3), "voice_end": round(char_time[b], 3)})
    for i, t in enumerate(timeline):
        t["end"] = timeline[i + 1]["start"] if i + 1 < len(timeline) else round(duration, 3)
        a, b = bounds[i]
        t["narration"], t["quote"] = shots[i][field], shots[i].get(quote_field)   # this language's words
        t["subs"] = _subtitles(full, a, b, char_time, t["end"] if i + 1 == len(timeline) else None, lang)
        if t["quote"]:
            t["quote_at"] = _quote_time(full, a, b, t["quote"], char_time, t)
    subs = [sub for t in timeline for sub in t["subs"]]
    for this, after in zip(subs, subs[1:]):   # one line on screen at a time, also across shots
        this["end"] = round(min(this["end"], after["start"] - 0.05), 3)
    return audio, {"duration": round(duration, 3), "shots": timeline, "draft": draft, "lang": lang,
                   "_spoken": spoken_sentences}


def listen(spoken: list, lang: str = "zh", threshold: float = 0.12) -> list[dict]:
    """Whisper round trip per sentence (vagent's ASR check): sentences the voice may have misread or swallowed."""
    from vagent.qa.asr import error_rate, transcribe

    flagged = []
    for text, audio in spoken:
        heard = transcribe(audio, SR, lang)
        rate = error_rate(spoken_text(text, lang), heard, lang)   # "+" is said 加: compare with what was said
        if rate > threshold:
            flagged.append({"text": text, "heard": heard, "error": round(rate, 2)})
    return flagged


def _subtitles(full, a, b, char_time, last_end, lang="zh"):
    """Clause-sized subtitles for one shot's narration, each shown until the next begins."""
    chunks, start = [], a
    shortest = 5 if lang == "zh" else 14       # shorter clauses ride along with the next one
    for m in CLAUSE[lang].finditer(full, a, b):
        if m.end() > start:
            chunks.append((start, m.end()))
            start = m.end()
    if start < b:
        chunks.append((start, b))
    merged = []
    for c in chunks:
        if merged and len(full[merged[-1][0]:merged[-1][1]].strip(STRIP + " ")) < shortest:
            merged[-1] = (merged[-1][0], c[1])
        else:
            merged.append(c)
    if lang == "en":                        # long English clauses are shown in parts, split between words
        merged = [piece for c in merged for piece in _split_long(full, *c)]
    subs = []
    for j, (c0, c1) in enumerate(merged):
        text = full[c0:c1].strip().rstrip(STRIP)
        if lang == "zh":
            text = re.sub(r"[，、,；;]", " ", text)
        else:
            text = text.rstrip(".,;:")          # keep ? and ! at the end, drop the quiet marks
        end = char_time[c1] + 0.25
        if j + 1 < len(merged):                # ends just before the next one appears (0.1 s ahead of its words)
            end = char_time[merged[j + 1][0]] - 0.15
        elif last_end is not None:
            end = last_end              # the last line stays on screen to the final frame
        subs.append({"text": text, "start": round(char_time[c0] - 0.1, 3), "end": round(end, 3)})
    return subs


MAX_EN = 44   # characters per English subtitle before it is split (two short rows on the portrait frame)


def _split_long(full: str, c0: int, c1: int) -> list[tuple[int, int]]:
    """Split [c0, c1) at the space nearest its middle until every piece is at most MAX_EN characters."""
    if c1 - c0 <= MAX_EN or " " not in full[c0:c1].strip():
        return [(c0, c1)]
    mid = (c0 + c1) // 2
    spaces = [k for k in range(c0 + 1, c1 - 1) if full[k] == " "]
    k = min(spaces, key=lambda k: abs(k - mid))
    return _split_long(full, c0, k + 1) + _split_long(full, k + 1, c1)


def _quote_time(full, a, b, quote, char_time, shot):
    """When the gold quote appears: as the voice starts saying it, else in the shot's second half."""
    norm = lambda s: re.sub(r"[\s，、,。．.！!？?：:；;“”\"'’]", "", s).lower()
    target, flat, index = norm(quote), [], []
    for c in range(a, b):
        if norm(full[c]):
            flat.append(full[c])
            index.append(c)
    found = "".join(flat).find(target)
    if found >= 0:
        return round(char_time[index[found]] - 0.1, 3)
    return round((shot["start"] + shot["voice_end"]) / 2, 3)


def save(audio: np.ndarray, path) -> None:
    sf.write(path, audio, SR)
