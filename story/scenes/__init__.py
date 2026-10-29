"""Scene library: one module per scene, looked up by the `scene` name in storyboard.json.

Every scene module provides
  TITLE                      the Chinese name used in the storyboard table
  MIN_S                      the shortest time the action needs (a shot is padded with silence up to it)
  camera(params) -> dict     where the camera should be: {"lift": 0..1, "zoom": 1, "ease": seconds}
  speed(p, d, params)        walking speed 0..1 at progress p (drives the parallax scroll), optional
  hero(st, p, d, params)     the hero's state: {"x", "pose", "facing", "light", "alpha", "lamp"}
  draw(cr, st, p, d, a, params)            what sits behind the hero
  front(cr, st, p, d, a, params, joints)   what sits in front of the hero, optional
p is the shot's progress 0..1, d its length in seconds, a the fade-in/out alpha of the shot.
"""
from __future__ import annotations

from importlib import import_module

NAMES = ["walk", "look_up", "stumble", "loop_path", "cloud", "constellation", "forecast", "companions",
         "pass_lamp", "reflect_light", "question", "writing", "signpost", "face_camera",
         "spiral", "cycle5", "gears", "fork", "mirror", "council", "wall", "cart", "countdown"]


def get(name: str):
    if name not in NAMES:
        raise KeyError(f"unknown scene '{name}'; known: {', '.join(NAMES)}")
    return import_module(f"{__name__}.{name}")
