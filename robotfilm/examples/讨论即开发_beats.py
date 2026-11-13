"""《讨论即开发，对话即交付》机器人版：机器人和它的 AI 同事（一颗会发光的球）边走边聊，
聊着聊着，想法就变成了能跑的软件。由 robotfilm/robot_story.py 读取。"""
import math

import cairo

from robotfilm.fx import (BOW, GIVE, HOLD, L, LOOK_UP, P, POINT, SHRUG, STAND, THINK, WORK, anchor, anchor_shot,
                          appear, label, sky)
from robotfilm.robot_story import ICE, glow_line, orb, smooth
from story.stage import GOLD, WHITE, ramp, text

PROPS = ["desk", "docs", "calendar", "laptop", "bulb", "clipboard", "sapling", "books", "drafting"]
MACHINE = None
RED = (1.0, 0.36, 0.36)
TALK = lambda lt, d: P(ua_f=40 + 18 * math.sin(lt * 4), la_f=70 + 20 * math.sin(lt * 4 + 1), head=-4)
TYPE = lambda lt, d: P(lean=10, ua_f=42, la_f=86 + 10 * math.sin(lt * 14), ua_b=38, la_b=84 + 10 * math.sin(lt * 14 + 2),
                       head=16)
WAIT = P(ua_f=30, la_f=110, ua_b=24, la_b=104, head=12)          # arms folded, waiting


# ---------- the AI companion and chat bubbles ----------
def ai_pos(film, t):
    """The AI floats a little ahead of the robot, at head height, bobbing."""
    return (film.hip_x + film.W * (0.30 if film.portrait else 0.16),
            film.ground - film.height * 1.15 + 10 * film.u * math.sin(t * 1.6))


def ai(film, cr, t, a=1.0, glow=1.0):
    if a <= 0:
        return
    x, y = ai_pos(film, t)
    u = film.u
    r = 22 * u
    orb(cr, x, y, r * (1 + 0.08 * math.sin(t * 3)) * glow, a)
    for k in range(2):
        cr.save()
        cr.translate(x, y)
        cr.rotate(t * (0.8 if k else -0.6) + k)
        cr.scale(1, 0.32)
        cr.arc(0, 0, r * (2.0 + 0.5 * k), 0, 2 * math.pi)
        cr.restore()
        cr.set_line_width(1.6 * u)
        cr.set_source_rgba(*ICE, 0.7 * a)
        cr.stroke()


def bubble(film, cr, cx, cy, s, a, mine=True, size=32):
    """A chat bubble with a short line of text (or dots); the robot's are white, the AI's ice-blue."""
    if a <= 0:
        return
    u = film.u
    cr.select_font_face("PingFang SC", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(size * u)
    w = max(80 * u, cr.text_extents(s).x_advance + 40 * u) if s else 90 * u
    h = 58 * u
    x, y = cx - w / 2, cy - h / 2
    r = 18 * u
    cr.new_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    tail = x + (w * 0.25 if mine else w * 0.75)
    cr.line_to(tail + 10 * u, y + h)
    cr.line_to(tail - (8 * u if mine else -18 * u), y + h + 16 * u)
    cr.line_to(tail - 8 * u, y + h)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.close_path()
    col = WHITE if mine else (*ICE, 1.0)
    cr.set_source_rgba(0.03, 0.05, 0.1, 0.75 * a)
    cr.fill_preserve()
    cr.set_line_width(2.4 * u)
    cr.set_source_rgba(*col[:3], 0.95 * a)
    cr.stroke()
    if s:
        text(cr, s, size * u, cx, cy, col, a=a, shadow=False)
    else:
        for k in range(3):
            cr.arc(cx - 20 * u + k * 20 * u, cy, 4 * u, 0, 2 * math.pi)
            cr.set_source_rgba(*col[:3], a * (0.5 + 0.5 * math.sin(film_t[0] * 6 - k)))
            cr.fill()


film_t = [0.0]


def chat(film, cr, ctx, lines, start=0.1, end=None):
    """Bubbles appearing in turn over the voice: lines = [(text, mine)]; older ones rise and fade."""
    film_t[0] = ctx["t"]
    end = end or ctx["voice"]
    n = len(lines)
    head_y = film.ground - film.height * 1.25
    ax, ay = ai_pos(film, ctx["t"])
    for k, (s, mine) in enumerate(lines):
        t0 = start + (end - start) * k / n
        a = ramp(ctx["lt"], t0, t0 + 0.3) * (1 - ramp(ctx["lt"], ctx["dur"] - 0.3, ctx["dur"]))
        newer = sum(1 for j in range(k + 1, n) if ctx["lt"] > start + (end - start) * j / n)
        a *= max(0.0, 1 - 0.35 * newer)
        lift = newer * 70 * film.u
        if mine:
            bubble(film, cr, film.hip_x + 40 * film.u, head_y - 50 * film.u - lift, s, a, True)
        else:
            bubble(film, cr, ax, ay - 90 * film.u - lift, s, a, False)


def with_ai(fx=None, a_in=None):
    """Shot effect that also draws the AI companion (fading in on the shot where it first appears)."""
    def run(film, cr, ctx):
        a = 1.0 if a_in is None else ramp(ctx["lt"], a_in, a_in + 0.8)
        ai(film, cr, ctx["t"], a)
        if fx:
            return fx(film, cr, ctx)
    return run


def laptop_screen(film, ctx, station_fx, height=170):
    """Screen rectangle (x0, y0, x1, y1) of the laptop prop standing at station_fx of this shot's arrival."""
    sp = film.props["laptop"]
    h = height * film.u
    w = h * sp.w / sp.h
    cx = anchor(film, ctx, station_fx)
    left, top = cx - w / 2, film.ground - h
    return left + w * 0.15, top + h * 0.07, left + w * 0.80, top + h * 0.58


def app(film, cr, box, version, a):
    """The little expense app on the laptop: v1 bars, v2 + a monthly trend line, v3 + overspending marked red."""
    x0, y0, x1, y1 = box
    u = film.u
    vals = [0.45, 0.6, 0.5, 0.82, 0.55, 0.7]
    bw = (x1 - x0) / (len(vals) * 1.6)
    for k, v in enumerate(vals):
        bx = x0 + (k + 0.5) * (x1 - x0) / len(vals) - bw / 2
        by = y1 - 8 * u - v * (y1 - y0 - 20 * u)
        red = version >= 3 and v > 0.75
        col = RED if red else (0.9, 0.97, 1.0)
        cr.rectangle(bx, by, bw, y1 - 8 * u - by)
        cr.set_source_rgba(*col, 0.85 * a)
        cr.fill()
    if version >= 2:
        pts = [(x0 + (k + 0.5) * (x1 - x0) / len(vals), y1 - 8 * u - v * (y1 - y0 - 20 * u) - 10 * u)
               for k, v in enumerate(vals)]
        glow_line(cr, pts, 2.5 * u, (*ICE, 1), a, glow=False)


# ---------- shot effects ----------
def fx_typing(film, cr, ctx):
    cx = anchor(film, ctx, 0.62)
    for k in range(6):                       # code keeps streaming up from the screen
        ph = (ctx["t"] * 0.6 + k / 6) % 1.0
        y = film.ground - 260 * film.u - ph * 260 * film.u
        x = cx - 60 * film.u + (k % 3) * 40 * film.u
        glow_line(cr, [(x, y), (x + (30 + 20 * (k % 2)) * film.u, y)], 3 * film.u, (*ICE, 1), 0.6 * math.sin(ph * math.pi), glow=False)


def fx_meet(film, cr, ctx):
    ai(film, cr, ctx["t"], ramp(ctx["lt"], ctx["walk"], ctx["walk"] + 0.8))


def fx_chat3(film, cr, ctx):
    ai(film, cr, ctx["t"])
    chat(film, cr, ctx, [(L(ctx, "想法", "idea"), True), ("", False), (L(ctx, "哪儿不对", "what's wrong"), True), ("", False),
                         (L(ctx, "再补充", "one more"), True), ("", False)])


def fx_no_typing(film, cr, ctx):
    ai(film, cr, ctx["t"])
    ax, ay = ai_pos(film, ctx["t"])
    box = laptop_screen(film, ctx, 0.66)
    for k in range(5):                       # code flows from the AI into the laptop by itself
        f = ((ctx["lt"] * 0.7) + k / 5) % 1.0
        x = ax + ((box[0] + box[2]) / 2 - ax) * f
        y = ay + ((box[1] + box[3]) / 2 - ay) * f
        glow_line(cr, [(x - 14 * film.u, y), (x + 14 * film.u, y)], 3 * film.u, (*ICE, 1), 0.8 * math.sin(f * math.pi), glow=False)
    rows = int(1 + 5 * ramp(ctx["lt"], 0.3, ctx["voice"]))
    for r in range(rows):
        y = box[1] + 12 * film.u + r * 14 * film.u
        glow_line(cr, [(box[0] + 10 * film.u, y), (box[0] + (40 + (r * 37) % 70) * film.u, y)], 2.5 * film.u, (*ICE, 1), 0.9, glow=False)


def fx_title(zh, en):
    def run(film, cr, ctx):
        ai(film, cr, ctx["t"])
        film.cr = cr
        x, y = sky(film, 0.5, 0.45)
        a = ramp(ctx["lt"], 0.2, 0.7) * (1 - ramp(ctx["lt"], ctx["dur"] - 0.3, ctx["dur"]))
        label(film, L(ctx, zh, en), x, y, a, 72 if ctx["lang"] == "zh" else 58, GOLD)
    return run


def fx_translate(film, cr, ctx):
    film.cr = cr
    ai(film, cr, ctx["t"])
    a = appear(ctx)
    k = ramp(ctx["lt"], 0.5, ctx["voice"])
    (lx, ly), (rx, ry) = sky(film, 0.22, 0.5), sky(film, 0.78, 0.5)
    for j in range(6):                       # the vague request: a soft cloud
        g = cairo.RadialGradient(lx + 30 * math.sin(j * 2.1) * film.u, ly + 20 * math.cos(j * 1.7) * film.u, 0,
                                 lx, ly, 90 * film.u)
        g.add_color_stop_rgba(0, 1, 1, 1, 0.10 * a)
        g.add_color_stop_rgba(1, 1, 1, 1, 0)
        cr.set_source(g)
        cr.arc(lx, ly, 90 * film.u, 0, 2 * math.pi)
        cr.fill()
    label(film, L(ctx, "模糊的需求", "vague request"), lx, ly + 110 * film.u, a, 34)
    glow_line(cr, [(lx + 100 * film.u, ly), (lx + 100 * film.u + (rx - lx - 200 * film.u) * k, ly)], 3 * film.u, WHITE, a)
    for r in range(int(6 * ramp(k, 0.6, 1.0)) + (1 if k > 0.6 else 0)):
        y = ry - 50 * film.u + r * 18 * film.u
        glow_line(cr, [(rx - 60 * film.u, y), (rx - 60 * film.u + (50 + (r * 41) % 70) * film.u, y)], 3 * film.u, (*ICE, 1), a, glow=False)
    label(film, L(ctx, "精确的代码", "precise code"), rx, ry + 110 * film.u, a * ramp(k, 0.6, 1.0), 34)


def fx_ai_takes(film, cr, ctx):
    film.cr = cr
    ai(film, cr, ctx["t"], glow=1 + 0.4 * ramp(ctx["lt"], 0.5, 1.5))
    ax, ay = ai_pos(film, ctx["t"])
    a = appear(ctx, 0.0)
    for r in range(6):
        f = smooth(ramp(ctx["lt"], 0.4 + r * 0.15, 1.2 + r * 0.15))
        y = ay - 120 * film.u + r * 16 * film.u
        glow_line(cr, [(ax - 50 * film.u, y), (ax - 50 * film.u + f * (40 + (r * 29) % 60) * film.u, y)], 3 * film.u, (*ICE, 1), a, glow=False)


def fx_what(film, cr, ctx):
    film.cr = cr
    ai(film, cr, ctx["t"])
    a = appear(ctx)
    k = ramp(ctx["lt"], 0.2, ctx["voice"])
    x0, y0 = sky(film, 0.5, 0.25)
    x1, y1 = sky(film, 0.5, 0.65)
    label(film, L(ctx, "怎么写", "how to write it"), x0, y0, a * (1 - 0.6 * ramp(k, 0.4, 0.6)), 48)
    if k > 0.4:
        w = 150 * film.u
        glow_line(cr, [(x0 - w / 2, y0), (x0 - w / 2 + w * ramp(k, 0.4, 0.55), y0)], 3 * film.u, RED, a, glow=False)
    label(film, L(ctx, "到底要什么", "what we actually want"), x1, y1, a * ramp(k, 0.5, 0.7), 56, GOLD)


def fx_grow(film, cr, ctx):
    ai(film, cr, ctx["t"])


def sapling_h(t, film):
    return 1.0


def fx_req(text_zh, text_en, version):
    def run(film, cr, ctx):
        ai(film, cr, ctx["t"])
        chat(film, cr, ctx, [(L(ctx, text_zh, text_en), True), ("", False)], 0.1, ctx["voice"] * 0.6)
        a = ramp(ctx["lt"], ctx["voice"] * 0.55, ctx["voice"] * 0.55 + 0.4)
        box = laptop_screen(film, {**ctx, "i": film.shot_index(11), "walk": 1.2}, 0.68)
        if version > 1:
            app(film, cr, box, version - 1, 1 - a)
        app(film, cr, box, version, a)
    return run


def fx_steps(film, cr, ctx):
    film.cr = cr
    ai(film, cr, ctx["t"])
    a = appear(ctx)
    k = ramp(ctx["lt"], 0.2, ctx["voice"])
    n = 6
    x0, y = sky(film, 0.12, 0.5)
    x1 = sky(film, 0.88, 0.5)[0]
    for j in range(n):
        f = ramp(k, j / n, (j + 0.6) / n)
        x = x0 + (x1 - x0) * j / (n - 1)
        bubble(film, cr, x, y - 70 * film.u, "", a * f, j % 2 == 0)
        cr.rectangle(x - 22 * film.u, y + 10 * film.u, 44 * film.u, 30 * film.u)
        cr.set_source_rgba(*ICE, 0.7 * a * f)
        cr.fill()
    label(film, L(ctx, "需求更清楚 · 代码往前走", "clearer needs · code moves on"), (x0 + x1) / 2, y + 90 * film.u, a, 34)


def fx_is_dev(film, cr, ctx):
    ai(film, cr, ctx["t"], glow=1.3)
    chat(film, cr, ctx, [("", True), ("", False), ("", True)])


def clock_hands(film, cr, ctx, station_fx, height=300):
    sp = film.props["calendar"]
    h = height * film.u
    cx = anchor(film, ctx, station_fx)
    cy = film.ground - h * 0.86
    r = h * 0.09
    for speed, length in ((4.0, 0.8), (0.5, 0.55)):
        ang = ctx["t"] * speed
        glow_line(cr, [(cx, cy), (cx + r * length * math.sin(ang), cy - r * length * math.cos(ang))], 2.5 * film.u, WHITE, 1.0, glow=False)


def fx_wait(film, cr, ctx):
    ai(film, cr, ctx["t"], 0.5)
    clock_hands(film, cr, ctx, 0.62)


def fx_instant(film, cr, ctx):
    ai(film, cr, ctx["t"])
    chat(film, cr, ctx, [(L(ctx, "改一下", "change it"), True)], 0.1, 0.5)
    box = laptop_screen(film, ctx, 0.68)
    a = ramp(ctx["lt"], ctx["walk"] + 0.9, ctx["walk"] + 1.1)
    app(film, cr, box, 3, a)
    flash = 1 - min(1.0, abs(ctx["lt"] - ctx["walk"] - 1.0) / 0.25)
    if flash > 0:
        orb(cr, (box[0] + box[2]) / 2, (box[1] + box[3]) / 2, 30 * film.u, flash)


def fx_draft(film, cr, ctx):
    ai(film, cr, ctx["t"])
    chat(film, cr, ctx, [("", True), ("", False), ("", True), ("", False)])
    box = laptop_screen(film, {**ctx, "i": film.shot_index(18), "walk": 1.0}, 0.68)
    app(film, cr, box, 3, 0.5 + 0.5 * ramp(ctx["lt"], 0.5, ctx["voice"]))


def package(film, cr, cx, cy, s, a):
    """A glowing cube outline: the deliverable."""
    if a <= 0:
        return
    u = film.u * s
    f = [(-40, -10), (20, -10), (20, 50), (-40, 50)]
    b = [(x + 22, y - 22) for x, y in f]
    to = lambda p: (cx + p[0] * u, cy + p[1] * u)
    for face in (f, b):
        glow_line(cr, [to(p) for p in face + face[:1]], 2.5 * film.u, (*ICE, 1), a)
    for p, q in zip(f, b):
        glow_line(cr, [to(p), to(q)], 2.5 * film.u, (*ICE, 1), a)


def fx_deliver(film, cr, ctx):
    film.cr = cr
    ai(film, cr, ctx["t"])
    k = smooth(ramp(ctx["lt"], 0.5, ctx["voice"]))
    a = appear(ctx)
    tx, ty = sky(film, 0.62, 0.55)
    for j in range(5):                       # the bubbles of the whole conversation gather into one package
        sx, sy = sky(film, 0.15 + 0.17 * j, 0.15 + 0.2 * (j % 2))
        x, y = sx + (tx - sx) * k, sy + (ty - sy) * k
        bubble(film, cr, x, y, "", a * (1 - k * 0.9), j % 2 == 0)
    package(film, cr, tx, ty, 1.3, a * k)


def fx_three_words(film, cr, ctx):
    film.cr = cr
    ai(film, cr, ctx["t"])
    a = appear(ctx)
    words = [(L(ctx, "最初的想法", "first idea"), True), (L(ctx, "中途的纠偏", "corrections"), False),
             (L(ctx, "达成的共识", "agreement"), True)]
    for j, (s, mine) in enumerate(words):
        x, y = sky(film, 0.5, 0.15 + 0.32 * j)
        f = ramp(ctx["lt"], 0.2 + j * ctx["voice"] / 3, 0.5 + j * ctx["voice"] / 3)
        bubble(film, cr, x, y, s, a * f, mine, 34)


def card(film, cr, cx, cy, s, a, gold=False):
    u = film.u
    w, h = 230 * u, 120 * u
    cr.rectangle(cx - w / 2, cy - h / 2, w, h)
    cr.set_source_rgba(0.03, 0.05, 0.1, 0.7 * a)
    cr.fill_preserve()
    cr.set_line_width(2.4 * u)
    cr.set_source_rgba(*(GOLD if gold else WHITE)[:3], a)
    cr.stroke()
    for r in range(3):
        glow_line(cr, [(cx - w / 2 + 20 * u, cy - h / 2 + 22 * u + r * 16 * u),
                       (cx - w / 2 + (100 + 30 * r) * u, cy - h / 2 + 22 * u + r * 16 * u)], 2 * u, WHITE, 0.5 * a, glow=False)
    text(cr, s, 34 * u, cx, cy + 26 * u, GOLD if gold else WHITE, a=a)


def fx_two_cards(film, cr, ctx):
    film.cr = cr
    ai(film, cr, ctx["t"])
    a = appear(ctx)
    tx, ty = sky(film, 0.5, 0.2)
    package(film, cr, tx, ty, 1.0, a)
    for j, (zh, en) in enumerate((("需求文档", "requirements"), ("实现方案", "plan"))):
        x, y = sky(film, 0.3 + 0.4 * j, 0.7)
        f = ramp(ctx["lt"], 0.3 + j * 0.8, 0.8 + j * 0.8)
        card(film, cr, x, y, L(ctx, zh, en), a * f, j == 1)


def fx_deliverable(film, cr, ctx):
    ai(film, cr, ctx["t"], glow=1.2)
    x, y = sky(film, 0.62, 0.55)
    package(film, cr, x, y, 1.5 + 0.1 * math.sin(ctx["t"] * 2), appear(ctx, 0.0))


def fx_question(film, cr, ctx):
    film.cr = cr
    ai(film, cr, ctx["t"])
    x, y = film.hip_x + 10 * film.u, film.ground - film.height * 1.45
    label(film, "?", x, y, appear(ctx), 80, GOLD)


def fx_bar(film, cr, ctx):
    film.cr = cr
    ai(film, cr, ctx["t"])
    a = appear(ctx)
    k = ramp(ctx["lt"], 0.5, ctx["voice"])
    x0, y0 = sky(film, 0.5, 0.25)
    x1, y1 = sky(film, 0.5, 0.65)
    label(film, L(ctx, "会不会写代码", "can you code"), x0, y0, a * (1 - 0.6 * ramp(k, 0.4, 0.6)), 46)
    if k > 0.4:
        w = 260 * film.u if ctx["lang"] == "zh" else 280 * film.u
        glow_line(cr, [(x0 - w / 2, y0), (x0 - w / 2 + w * ramp(k, 0.4, 0.55), y0)], 3 * film.u, RED, a, glow=False)
    label(film, L(ctx, "能不能把问题说清楚", "can you explain it clearly"), x1, y1, a * ramp(k, 0.5, 0.7), 52, GOLD)


def books_dim(t, film):
    i = film.shot_index(26)
    s = film.shots[i]
    return 0.8 * smooth(ramp(t, s["start"] + 1.6, s["voice_end"]))


def fx_need(film, cr, ctx):
    ai(film, cr, ctx["t"])
    chat(film, cr, ctx, [(L(ctx, "要什么", "what I want"), True), (L(ctx, "哪儿不对", "what's wrong"), True),
                         (L(ctx, "这样改", "change it so"), True)])


def fx_judge(film, cr, ctx):
    film.cr = cr
    ai(film, cr, ctx["t"])
    a = appear(ctx)
    (x0, y), (x1, _) = sky(film, 0.3, 0.4), sky(film, 0.7, 0.4)
    label(film, L(ctx, "表达", "expression"), x0, y, a * ramp(ctx["lt"], 0.3, 0.8), 56, GOLD)
    label(film, L(ctx, "判断", "judgment"), x1, y, a * ramp(ctx["lt"], 0.8, 1.3), 56, GOLD)
    label(film, L(ctx, "技术", "technical skill"), (x0 + x1) / 2, sky(film, 0.5, 0.8)[1], 0.45 * a * ramp(ctx["lt"], 1.5, 2.0), 40)


def fx_designer(film, cr, ctx):
    ai(film, cr, ctx["t"])
    x = anchor(film, ctx, 0.92)
    film.robot(cr, x, film.ground, TYPE(ctx["lt"], ctx["dur"]), alpha=ramp(ctx["lt"], ctx["walk"] - 0.6, ctx["walk"]), flip=True)


def fx_idea(film, cr, ctx):
    ai(film, cr, ctx["t"])
    bx = anchor(film, ctx, 0.48)
    by = film.ground - 150 * film.u
    box = laptop_screen(film, ctx, 0.82, 150)
    k = smooth(ramp(ctx["lt"], ctx["walk"] + 0.5, ctx["voice"]))
    n = 40
    pts = [(bx + ((box[0] + box[2]) / 2 - bx) * j / n, by + ((box[1] + box[3]) / 2 - by) * j / n - math.sin(j / n * math.pi) * 60 * film.u)
           for j in range(n + 1)]
    glow_line(cr, pts[: max(2, int(n * k) + 1)], 3 * film.u, (*ICE, 1), 0.9)
    app(film, cr, box, 3, ramp(k, 0.9, 1.0))


def fx_summary(film, cr, ctx):
    film.cr = cr
    ai(film, cr, ctx["t"])
    a = appear(ctx)
    k = ramp(ctx["lt"], 0.5, ctx["voice"])
    x0, y0 = sky(film, 0.5, 0.25)
    x1, y1 = sky(film, 0.5, 0.65)
    label(film, L(ctx, "把想法翻译成代码", "ideas into code"), x0, y0, a * (1 - 0.5 * ramp(k, 0.45, 0.6)), 46)
    label(film, L(ctx, "把想法聊成现实", "ideas into reality"), x1, y1, a * ramp(k, 0.5, 0.7), 56, GOLD)


def fx_motto(film, cr, ctx):
    film.cr = cr
    ai(film, cr, ctx["t"])
    a = appear(ctx, 0.0)
    for j, (zh, en) in enumerate((("讨论即开发", "discussion is development"), ("对话即交付", "conversation is delivery"))):
        x, y = sky(film, 0.5, 0.3 + 0.4 * j)
        label(film, L(ctx, zh, en), x, y, a * ramp(ctx["lt"], 0.2 + j * 0.8, 0.7 + j * 0.8), 54 if ctx["lang"] == "zh" else 46, GOLD)


def fx_say_it(film, cr, ctx):
    ai(film, cr, ctx["t"])
    chat(film, cr, ctx, [(L(ctx, "我有个点子", "I have an idea"), True), ("", False)], 0.4, ctx["voice"])
    bx = film.hip_x + 40 * film.u
    by = film.ground - film.height * 1.25 - 50 * film.u - 70 * film.u
    orb(cr, bx, by - 50 * film.u, 10 * film.u, ramp(ctx["lt"], 0.2, 0.6) * (1 - ramp(ctx["lt"], ctx["dur"] - 0.3, ctx["dur"])))


def fx_end(film, cr, ctx):
    ai(film, cr, ctx["t"], glow=1.2)


BEATS = {
    1: dict(pose=TYPE, stations=[("desk", 0.66, 260, {"out": 2})], fx=fx_typing),
    2: dict(walk=1.6, pose=STAND, fx=lambda f, c, x: ai(f, c, x["t"], ramp(x["lt"], x["walk"] - 0.3, x["walk"] + 0.6))),
    3: dict(pose=TALK, fx=fx_chat3),
    4: dict(walk=1.2, pose=STAND, stations=[("laptop", 0.66, 170, {"out": 6})], fx=fx_no_typing),
    5: dict(pose=STAND, fx=with_ai()),
    6: dict(walk=1.6, pose=LOOK_UP, fx=fx_title("讨论即开发", "discussion is development")),
    7: dict(pose=THINK, fx=fx_translate),
    8: dict(pose=STAND, fx=fx_ai_takes),
    9: dict(pose=THINK, fx=fx_what),
    10: dict(walk=1.4, pose=STAND, stations=[("docs", 0.58, 230, {"dim": lambda t, f: 0.7 * smooth(ramp(t, f.shots[f.shot_index(10)]["start"] + 2.5, f.shots[f.shot_index(10)]["start"] + 3.5))}),
                                             ("sapling", 0.85, 160, {"grow": True})], fx=fx_grow),
    11: dict(walk=1.2, pose=TALK, stations=[("laptop", 0.68, 170)], fx=fx_req("我想做个记账工具", "an expense tracker", 1)),
    12: dict(pose=TALK, fx=fx_req("要能按月看趋势", "monthly trends", 2)),
    13: dict(pose=TALK, fx=fx_req("超支要标红", "overspending in red", 3)),
    14: dict(pose=STAND, fx=fx_steps),
    15: dict(pose=STAND, fx=fx_is_dev),
    16: dict(walk=1.6, pose=LOOK_UP, fx=fx_title("对话即交付", "conversation is delivery")),
    17: dict(walk=1.2, pose=WAIT, stations=[("calendar", 0.62, 300), ("clipboard", 0.88, 180)], fx=fx_wait),
    18: dict(walk=1.0, pose=TALK, stations=[("laptop", 0.68, 170, {"out": 20})], fx=fx_instant),
    19: dict(pose=TALK, fx=fx_draft),
    20: dict(pose=STAND, fx=fx_deliver),
    21: dict(pose=STAND, fx=fx_three_words),
    22: dict(pose=STAND, fx=fx_two_cards),
    23: dict(pose=STAND, fx=fx_deliverable),
    24: dict(walk=1.4, pose=SHRUG, fx=fx_question),
    25: dict(pose=THINK, fx=fx_bar),
    26: dict(walk=1.2, pose=STAND, stations=[("books", 0.62, 200, {"dim": books_dim})], fx=with_ai()),
    27: dict(pose=TALK, fx=fx_need),
    28: dict(pose=STAND, fx=fx_judge),
    29: dict(walk=1.4, pose=STAND, stations=[("drafting", 0.66, 220)], fx=fx_designer),
    30: dict(walk=1.4, pose=STAND, stations=[("bulb", 0.48, 150, {"out": 32}), ("laptop", 0.82, 150, {"out": 32})], fx=fx_idea),
    31: dict(pose=STAND, fx=fx_summary),
    32: dict(walk=2.0, pose=LOOK_UP, fx=fx_motto),
    33: dict(pose=TALK, fx=fx_say_it),
    34: dict(walk=0.0, pose=STAND, fx=fx_end, front=(0.6, (0.95, 1.35))),
}
