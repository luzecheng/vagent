"""Storyboard + a narration timeline -> timed SceneSpecs for one language."""
from __future__ import annotations

from ..render.engine import SceneSpec
from ..script.text import zh_punct
from .schema import Storyboard

LEAD = 0.15  # a scene appears slightly before its first word
def scene_specs(board: Storyboard, timeline: dict, lang: str, intro: float = 0.0) -> list[SceneSpec]:
    """`intro`: seconds at the start that belong to the cover frame, before the first scene."""
    sentences = {s["id"]: s for s in timeline["sentences"]}
    ids = sorted(sentences)

    def sentence(i: int) -> dict:
        # the English script may fold a line into its neighbour; use the nearest earlier one
        if i in sentences:
            return sentences[i]
        earlier = [k for k in ids if k < i]
        return sentences[earlier[-1] if earlier else ids[0]]

    starts = []
    for index, scene in enumerate(board.scenes):
        starts.append(intro if index == 0 else max(0.0, sentence(scene.sentence_ids[0])["clip_start"] - LEAD))
    specs = []
    for index, scene in enumerate(board.scenes):
        start = starts[index]
        end = starts[index + 1] if index + 1 < len(starts) else timeline["duration"]
        if end <= start:  # folded English lines can collapse a scene; give it a minimal slot
            end = start + 0.5
        reveal_ids = scene.reveal_on or scene.sentence_ids
        reveals = [max(start, sentence(i)["start"] - 0.1) for i in reveal_ids]
        params = zh_punct(scene.params_zh) if lang == "zh" else scene.params_en
        specs.append(SceneSpec(scene.id, scene.component, params, round(start, 3), round(end, 3),
                               [round(r, 3) for r in reveals]))
    # keep scenes contiguous after any adjustment
    for current, following in zip(specs, specs[1:]):
        following.start = current.end
    return specs
