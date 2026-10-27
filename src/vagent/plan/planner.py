"""LLM storyboard planning: sentences -> scenes from the component library."""
from __future__ import annotations

import json

from .. import cache as cachemod
from ..llm.client import structured
from ..render.components import REGISTRY
from ..render.icons import names as icon_names
from .schema import Storyboard, problems

PROMPT_VERSION = 6

PURPOSE = {
    "hook": "opening title: the single most striking line, big. ALWAYS the first scene",
    "keyword": "one key term or idea, very big, with a short caption",
    "compare_cards": "two contrasting options or views; mark the good one 'check' and the risky one 'warn'",
    "trend": "a line going up/down/volatile over time; schematic unless the script states numbers",
    "short_vs_long": "short-term noise versus long-term direction",
    "timeline": "2-5 ordered steps or stages",
    "bars": "2-5 quantities side by side; ONLY when the script states every value",
    "big_number": "one number stated in the script, very big",
    "quote": "a sentence worth quoting as a quote card",
    "checklist": "2-5 short parallel items (rules, do's and don'ts); mode 'ticks' ticks each one off as it is said",
    "strike": "an old/wrong belief crossed out, replaced by the new view",
    "three_things": "exactly three numbered points (first/second/third) revealed one by one",
    "question_stack": "2-5 consecutive questions popping in one by one",
    "choice_consequence": "choices on top, an arrow, and their consequence below",
    "punchline": "the key sentence enlarged, one phrase highlighted in gold",
    "balance": "two things weighed against each other (a trade-off); the beam tips to the heavier side",
    "cycle": "3-4 steps that repeat as a loop (do -> check -> adjust -> do again)",
    "dialogue": "2-4 short spoken lines: a conversation, or the narrator's inner voice ('me')",
}

SYSTEM = """You are the storyboard planner for a vertical short video (9:16). The voice-over and full
subtitles already carry every word; your visuals must ADD meaning, not repeat the subtitle.

Assign every sentence id to exactly one scene, in order, scenes covering consecutive sentences.
Pick each scene's component from the catalog and fill its parameters twice: params_zh in Chinese
(from the Chinese sentences) and params_en in English (from the English lines with the same ids).

Rules:
- Scene 1 is ALWAYS `hook` and must cover the first sentences until at least 3 seconds have passed.
  Its text is the most striking line of the whole script (hook_sentence_id), shortened if needed.
- Visual text is short: titles and labels, not full sentences (except quote/punchline/hook).
- Visual text condenses what the script says; it never adds a verdict, conclusion or claim the script
  does not make (if the script only asks "is it worth it?", do not answer it on screen).
- Chinese visual text uses Chinese punctuation: the ellipsis is "……", never "...".
- ICONS make the video less text-heavy: set `icon` / `icons` (same names in params_zh and params_en)
  wherever a concrete, literal object fits the line - a house for renting, a wallet for money, a clock
  for time, an eye for seeing clearly, a scale for weighing a trade-off. Aim for icons in about half the
  scenes; leave them out when only a far-fetched metaphor would fit. Use only names from the icon list.
- Match structure: enumerations ("第一/第二/第三") -> three_things or checklist; several questions in a
  row -> question_stack; "A is a choice, B is a choice, you can't escape the consequence" ->
  choice_consequence; "you think X, actually Y" -> strike; the thesis sentence -> punchline;
  weighing two sides or a trade-off -> balance; a repeated improve-and-retry process -> cycle;
  quoted speech or what someone says to themselves -> dialogue; things to check off -> checklist ticks.
- For list-like components set reveal_on: the sentence id at which each item should appear.
- Never use the same component three times in a row; use the `layout` variants where available.
- Typical scene length 4-12 seconds; do not create scenes shorter than about 2.5 seconds.
- DATA RED LINE: never show a number that is not in the script. A trend without stated numbers is
  schematic (leave values empty); bars and big_number need values the script states.
- content_type: classify the whole script. Disclaimer "on" only for investing / crypto / personal
  finance content; mindset or life advice gets no disclaimer. Give a short reason.
Return JSON only."""


def catalog() -> str:
    rows = []
    for name, (_, model) in REGISTRY.items():
        schema = model.model_json_schema()
        rows.append(f"## {name}: {PURPOSE[name]}\nparams schema: {json.dumps(schema, ensure_ascii=False)}")
    rows.append("# Icon list (line icons drawn on stroke by stroke)\n\n" + ", ".join(sorted(icon_names())))
    return "\n\n".join(rows)


def plan(zh_lines: dict[int, str], en_lines: dict[int, str], timings: dict[int, tuple[float, float]], config: dict,
         log=None) -> Storyboard:
    sentences = "\n".join(
        f"{i}. [{timings[i][0]:.1f}-{timings[i][1]:.1f}s] ZH: {zh_lines[i]}\n    EN: {en_lines.get(i, '')}"
        for i in sorted(zh_lines))
    user = f"# Component catalog\n\n{catalog()}\n\n# Script (id, Chinese timing, zh, en)\n\n{sentences}"
    store = cachemod.Cache(config["paths"]["cache"], "llm/storyboard")
    digest = cachemod.key(PROMPT_VERSION, SYSTEM, user, config["llm"]["model"])
    cached = store.get_json(digest)
    if cached is not None:
        board = Storyboard.model_validate(cached)
        if not problems(board, zh_lines, en_lines, timings):
            if log:
                log.event("plan", "storyboard from cache")
            return board
    board = structured(Storyboard, SYSTEM, user, config, log,
                       validate=lambda b: problems(b, zh_lines, en_lines, timings))
    store.put_json(digest, board.model_dump())
    return board
