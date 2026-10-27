"""Storyboard schema and its semantic checks.

The schema (pydantic -> JSON Schema) is what Claude must emit; `problems()`
returns human-readable violations that are fed back for a retry:
  * every sentence covered exactly once, scenes in order and contiguous
  * the first scene is a `hook` and covers at least the first 3 seconds
  * no component used more than twice in a row
  * params validate against the component's own model, in both languages
  * zh params are Chinese, en params contain no Chinese
  * data red line: every number shown must appear in that scene's sentences;
    chart values need a source sentence that contains them
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from ..render.components import REGISTRY
from ..render.icons import names as icon_names

ComponentName = Literal[tuple(REGISTRY)]  # type: ignore[valid-type]
HAN = re.compile(r"[一-鿿]")
NUMBER = re.compile(r"\d+(?:[.,]\d+)?%?")


class SceneModel(BaseModel):
    id: str = Field(description="s01, s02, ...")
    sentence_ids: list[int] = Field(min_length=1, description="consecutive sentence ids this scene covers")
    component: ComponentName
    params_zh: dict = Field(description="parameters for the component, Chinese text")
    params_en: dict = Field(description="same parameters, English text from the English script")
    reveal_on: list[int] = Field(default_factory=list,
                                 description="for list-like components: sentence id that reveals each item, in order")
    why: str = Field("", description="one short phrase: why this visual fits these sentences")


class Disclaimer(BaseModel):
    on: bool
    reason: str


class Storyboard(BaseModel):
    content_type: Literal["investing", "crypto", "personal_finance", "mindset", "life", "other"]
    disclaimer: Disclaimer
    hook_sentence_id: int = Field(description="id of the most striking sentence, used for the opening hook")
    scenes: list[SceneModel] = Field(min_length=3)


NOT_SHOWN = ("icon", "icons")  # parameter names whose values are identifiers, never drawn as text


def _texts(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for k, v in value.items() if k not in NOT_SHOWN for t in _texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in _texts(v)]
    return []


def _numbers(value) -> list[str]:
    found = []
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        found.append(f"{value:g}")
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in ("layout", "value_source_sentence", *NOT_SHOWN):
                continue
            found.extend(_numbers(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_numbers(item))
    elif isinstance(value, str):
        found.extend(NUMBER.findall(value))
    return found


def _normal(number: str) -> str:
    return number.replace(",", "").rstrip("%")


EN_NUMBERS = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split())}
EN_NUMBERS.update({"thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70", "eighty": "80",
                   "ninety": "90", "hundred": "100", "thousand": "1000", "million": "1000000", "half": "50"})


def source_numbers(text: str) -> set[str]:
    """Numbers stated in the sentences, whether written as digits or as words (三/十年/three/ten)."""
    found = {_normal(n) for n in NUMBER.findall(text.replace(",", ""))}
    if HAN.search(text):
        try:
            import cn2an

            found |= {_normal(n) for n in NUMBER.findall(cn2an.transform(text, "cn2an"))}
        except Exception:
            pass
    for word in re.findall(r"[a-z]+", text.lower()):
        if word in EN_NUMBERS:
            found.add(EN_NUMBERS[word])
    return found


def _icon_names(params) -> list[str]:
    """Every non-empty icon name in a params tree ("icon" values and "icons" lists)."""
    found: list[str] = []
    if isinstance(params, dict):
        for key, value in params.items():
            if key == "icon" and isinstance(value, str) and value:
                found.append(value)
            elif key == "icons" and isinstance(value, list):
                found.extend(v for v in value if isinstance(v, str) and v)
            else:
                found.extend(_icon_names(value))
    elif isinstance(params, list):
        for value in params:
            found.extend(_icon_names(value))
    return found


def problems(board: Storyboard, zh: dict[int, str], en: dict[int, str], timings: dict[int, tuple[float, float]]) -> list[str]:
    out: list[str] = []
    ids = sorted(zh)
    covered = [i for scene in board.scenes for i in scene.sentence_ids]
    if covered != ids:
        missing = sorted(set(ids) - set(covered))
        dupes = sorted({i for i in covered if covered.count(i) > 1})
        out.append(f"scenes must cover sentence ids {ids[0]}..{ids[-1]} exactly once, in order"
                   + (f"; missing {missing}" if missing else "") + (f"; repeated {dupes}" if dupes else ""))
    for scene in board.scenes:
        if scene.sentence_ids != list(range(scene.sentence_ids[0], scene.sentence_ids[0] + len(scene.sentence_ids))):
            out.append(f"{scene.id}: sentence_ids must be consecutive")
    if board.hook_sentence_id not in zh:
        out.append("hook_sentence_id is not a sentence id")
    first = board.scenes[0]
    if first.component != "hook":
        out.append("the first scene must use the 'hook' component")
    elif timings:
        span = timings[first.sentence_ids[-1]][1]
        if span < 3.0:
            out.append(f"the hook scene covers only {span:.1f}s; include the next sentence(s) so it lasts >= 3s")
    run = 1
    for prev, scene in zip(board.scenes, board.scenes[1:]):
        run = run + 1 if scene.component == prev.component else 1
        if run > 2:
            out.append(f"{scene.id}: '{scene.component}' used 3 times in a row; vary the visuals")
    for scene in board.scenes:
        _, model = REGISTRY[scene.component]
        for lang, params in (("zh", scene.params_zh), ("en", scene.params_en)):
            try:
                model.model_validate(params)
            except ValidationError as exc:
                out.append(f"{scene.id} params_{lang} invalid for {scene.component}: "
                           + "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:4]))
                continue
            texts = " ".join(_texts(params))
            if lang == "zh" and "..." in texts:
                out.append(f"{scene.id}: params_zh uses '...'; the Chinese ellipsis is '……'")
            if lang == "en" and HAN.search(texts):
                out.append(f"{scene.id}: params_en contains Chinese text")
            if lang == "zh" and texts and not HAN.search(texts):
                out.append(f"{scene.id}: params_zh has no Chinese text")
            source = " ".join((zh if lang == "zh" else en).get(i, "") for i in scene.sentence_ids)
            stated = source_numbers(source)
            for number in _numbers(params):
                if _normal(number) not in stated:
                    out.append(f"{scene.id} params_{lang}: the number {number} does not appear in this scene's "
                               "sentences (data red line: show only numbers stated in the script)")
            for name in _icon_names(params):
                if name not in icon_names():
                    out.append(f"{scene.id} params_{lang}: unknown icon '{name}'; use a name from the icon list or ''")
            if scene.component == "bars" and any(item.get("value") is None for item in params["items"]):
                out.append(f"{scene.id} params_{lang}: bars need a value stated in the script for every item; "
                           "without stated values use another component (bar heights read as data)")
            sid = params.get("value_source_sentence")
            if sid is not None and sid not in scene.sentence_ids:
                out.append(f"{scene.id}: value_source_sentence {sid} is not one of this scene's sentences")
        if scene.reveal_on and any(i not in scene.sentence_ids for i in scene.reveal_on):
            out.append(f"{scene.id}: reveal_on must use this scene's sentence ids")
    return out
