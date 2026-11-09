#!/usr/bin/env python3
"""
Venu2328 profile — asset generator
==================================

Builds every animated SVG in ../assets from ONE content config and ONE design
system, so the whole profile stays visually consistent and is easy to edit.

    pip install fonttools brotli pillow
    npm i @fontsource/anton @fontsource/permanent-marker @fontsource/space-mono \
          @fontsource/space-grotesk @fontsource/instrument-serif
    python3 tools/build_assets.py --fonts <folder with the .ttf files> --out assets

Fonts are subset to only the glyphs each SVG uses and embedded as base64 WOFF2,
because GitHub renders README images in a sandbox that blocks external fonts.
All fonts are SIL Open Font License; tech logos in icons.json are from
Simple Icons (CC0).

Every animation respects `prefers-reduced-motion`: the resting state of each
element is its final, fully visible state.
"""
from __future__ import annotations

import argparse
import base64
import html
import io
import json
import math
import random
from collections import defaultdict
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

# ─────────────────────────────────────────────────────────────── design tokens
C = {
    "ink": "#170D0D",
    "ink2": "#24171A",
    "red": "#B4212A",
    "red_deep": "#7C161D",
    "red_hot": "#E04A3F",
    "paper": "#F1E2CC",
    "paper2": "#E7D3B8",
    "cream": "#FBF2E4",
    "muted": "#6E5A52",
    "muted_ink": "#A8968A",
    "rule": "#DCC6A8",
}
W = 1200          # every full-width asset is designed on a 1200-unit grid
R = 18            # corner radius shared by all panels

FONT_FILES = {
    "anton": "anton-latin-400-normal.ttf",
    "marker": "permanent-marker-latin-400-normal.ttf",
    "mono": "space-mono-latin-400-normal.ttf",
    "monob": "space-mono-latin-700-normal.ttf",
    "sg": "space-grotesk-latin-500-normal.ttf",
    "sgb": "space-grotesk-latin-700-normal.ttf",
    "serif": "instrument-serif-latin-400-italic.ttf",
}

# ─────────────────────────────────────────────────────────────── content
LINKS = {
    "sciphylabs": "https://sciphylabs.com",
    "website": "https://sreeramvenugopal.com",
    "doi": "https://doi.org/10.5281/zenodo.20113496",
    "orcid": "https://orcid.org/0009-0009-2916-7633",
    "paper": "https://sreeramvenugopal.com/Research-Whitepaper.pdf",
}

TICKER_TOP = ["SREERAM VENUGOPAL", "FOUNDER @ SCIPHYLABS", "RESEARCHER", "AUTHOR",
              "DEVELOPER", "PUDUCHERRY, INDIA"]
TICKER_BOTTOM = ["PHYSICS, REBUILT FROM SCRATCH", ("dream. build. repeat.", "marker"),
                 "400+ INTERACTIVE SIMULATIONS", ("making things that matter", "marker"),
                 "EST. 2023"]

HEADERS = [
    # file-id, index, title, kicker, scribble
    ("about", "01", "HEY, INTERNET.", "/ ABOUT — THE PERSON BEHIND THE PIXELS", "hi, i'm sreeram"),
    ("work", "02", "SELECTED WORK.", "/ WORK — IDEAS OUT OF THE NOTES APP", "actually shipped"),
    ("research", "03", "RESEARCH DESK.", "/ RESEARCH & WRITING — MORE THAN CODE", "nerd mode: on"),
    ("toolbox", "04", "THE TOOLBOX.", "/ STACK — ALWAYS LEARNING, ALWAYS SHIPPING", "wip forever"),
    ("signal", "05", "GITHUB SIGNAL.", "/ LIVE — REAL ACTIVITY, NO MADE-UP NUMBERS", "touch grass? later"),
    ("connect", "06", "OKAY, YOUR TURN.", "/ CONNECT — GOOD IDEAS ARE BETTER SHARED", "say hi"),
]

TERMINAL = [
    ("$", "whoami"),
    (">", "sreeram venugopal · founder @ sciphylabs · student · researcher"),
    ("$", "cat now_building.txt"),
    (">", "sciphylabs — 400+ interactive physics simulations, notes & PYQs"),
    (">", "  for class 11–12 · jee · neet · cuet · ap · sat"),
    ("$", "ls ./exploring"),
    (">", "ai-ml/  llm-apps/  scientific-computing/  software-architecture/"),
    ("$", "cat on_my_desk.txt"),
    (">", "physics masterbook (11 & 12) · the g.o.a.t. series   [writing]"),
    ("$", "./status --vibe"),
    (">", "dream. build. repeat."),
]

EXPLORING = ["ARTIFICIAL INTELLIGENCE", "MACHINE LEARNING", "LLM APPLICATIONS",
             "SCIENTIFIC COMPUTING", "INTERACTIVE SIMULATION", "SOFTWARE ARCHITECTURE",
             "DATA SCIENCE", "EDTECH"]

BUTTONS = {
    # file-id: (label, variant)
    "sciphylabs": ("SCIPHYLABS", "red"),
    "website": ("WEBSITE", "ink"),
    "doi": ("ZENODO DOI", "paper"),
    "orcid": ("ORCID", "paper"),
    "linkedin": ("LINKEDIN", "red"),
    "x": ("X / TWITTER", "ink"),
    "youtube": ("YOUTUBE", "paper"),
    "medium": ("MEDIUM", "ink"),
    "email": ("EMAIL ME", "red"),
}
NAV = [("about", "01", "ABOUT"), ("work", "02", "WORK"), ("research", "03", "RESEARCH"),
       ("toolbox", "04", "STACK"), ("signal", "05", "SIGNAL"), ("connect", "06", "CONNECT")]


# ─────────────────────────────────────────────────────────────── font engine
class Font:
    def __init__(self, path: Path):
        self.path = path
        self.tt = TTFont(path)
        self.upm = self.tt["head"].unitsPerEm
        self.cmap = self.tt.getBestCmap()
        self.hmtx = self.tt["hmtx"]
        self.cap = self.tt["OS/2"].sCapHeight / self.upm

    def width(self, text: str, size: float, ls: float = 0.0) -> float:
        total = 0
        for ch in text:
            g = self.cmap.get(ord(ch))
            if g is None:
                raise ValueError(f"glyph {ch!r} missing from {self.path.name}")
            total += self.hmtx[g][0]
        return total * size / self.upm + ls * max(len(text) - 1, 0)

    def woff2_b64(self, chars: set[str]) -> str:
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.layout_features = ["kern", "liga", "calt"]
        opts.notdef_outline = True
        sub = subset.Subsetter(options=opts)
        font = TTFont(self.path)
        sub.populate(text="".join(sorted(chars | {" "})))
        sub.subset(font)
        buf = io.BytesIO()
        font.flavor = "woff2"
        font.save(buf)
        return base64.b64encode(buf.getvalue()).decode()


FONTS: dict[str, Font] = {}


def esc(s: str) -> str:
    return html.escape(s, quote=True)


# ─────────────────────────────────────────────────────────────── svg builder
BASE_CSS = """
.draw{stroke-dasharray:1;stroke-dashoffset:0;animation:draw 1.1s cubic-bezier(.6,0,.2,1) .5s backwards}
@keyframes draw{from{stroke-dashoffset:1}}
.rise{animation:rise .8s cubic-bezier(.2,.8,.2,1) backwards}
@keyframes rise{from{opacity:0;transform:translateY(18px)}}
.pop{transform-box:fill-box;transform-origin:center;animation:pop .55s cubic-bezier(.3,1.6,.5,1) backwards}
@keyframes pop{from{opacity:0;transform:scale(.6)}}
.tw{transform-box:fill-box;transform-origin:center;animation:tw 2.8s ease-in-out infinite}
@keyframes tw{0%,100%{opacity:.25;transform:scale(.7)}50%{opacity:1;transform:scale(1)}}
.spin{transform-box:fill-box;transform-origin:center;animation:spin 26s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""


class SVG:
    def __init__(self, w: float, h: float, title: str):
        self.w, self.h, self.title = w, h, title
        self.defs: list[str] = []
        self.css: list[str] = [BASE_CSS]
        self.body: list[str] = []
        self.used: dict[str, set] = defaultdict(set)

    # text helper — records glyph usage for subsetting
    def text(self, x, y, s, font, size, fill, ls=0, anchor="start", cls="", style="", extra=""):
        self.used[font].update(s)
        a = [f'x="{x:.1f}"', f'y="{y:.1f}"', f'font-size="{size}"', f'fill="{fill}"',
             f'class="{("f-" + font + " " + cls).strip()}"']
        if ls:
            a.append(f'letter-spacing="{ls}"')
        if anchor != "start":
            a.append(f'text-anchor="{anchor}"')
        if style:
            a.append(f'style="{style}"')
        if extra:
            a.append(extra)
        return f'<text {" ".join(a)}>{esc(s)}</text>'

    def add(self, *parts: str):
        self.body.extend(parts)

    def render(self) -> str:
        font_css = []
        for key, chars in self.used.items():
            f = FONTS[key]
            font_css.append(
                f"@font-face{{font-family:'{key}';src:url(data:font/woff2;base64,{f.woff2_b64(chars)}) format('woff2')}}"
                f".f-{key}{{font-family:'{key}'}}"
            )
        style = "text{white-space:pre}" + "".join(font_css) + "".join(self.css)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{self.w:.0f}" height="{self.h:.0f}" viewBox="0 0 {self.w:.0f} {self.h:.0f}" '
            f'role="img" aria-label="{esc(self.title)}">'
            f"<title>{esc(self.title)}</title>"
            f"<style>{style}</style>"
            f"<defs>{''.join(self.defs)}</defs>"
            + "".join(self.body)
            + "</svg>"
        )


# ─────────────────────────────────────────────────────────────── primitives
def sparkle(cx, cy, r, fill, cls="", style="", pinch=0.16):
    p = pinch * r
    d = (f"M{cx:.1f} {cy - r:.1f}Q{cx + p:.1f} {cy - p:.1f} {cx + r:.1f} {cy:.1f}"
         f"Q{cx + p:.1f} {cy + p:.1f} {cx:.1f} {cy + r:.1f}"
         f"Q{cx - p:.1f} {cy + p:.1f} {cx - r:.1f} {cy:.1f}"
         f"Q{cx - p:.1f} {cy - p:.1f} {cx:.1f} {cy - r:.1f}Z")
    s = f' style="{style}"' if style else ""
    c = f' class="{cls}"' if cls else ""
    return f'<path d="{d}" fill="{fill}"{c}{s}/>'


def arrow_out(x, y, s, stroke, sw=2.6):
    """↗ icon whose bounding box starts at (x, y-s)."""
    return (f'<path d="M{x:.1f} {y:.1f}L{x + s:.1f} {y - s:.1f}M{x + s * .32:.1f} {y - s:.1f}'
            f'H{x + s:.1f}V{y - s * .68:.1f}" fill="none" stroke="{stroke}" stroke-width="{sw}" '
            f'stroke-linecap="square"/>')


def halftone(svg: SVG, pid, color, x, y, w, h, cx, cy, radius, opacity=.5, step=12, r=2.3):
    svg.defs.append(
        f'<pattern id="{pid}p" width="{step}" height="{step}" patternUnits="userSpaceOnUse">'
        f'<circle cx="{step / 2}" cy="{step / 2}" r="{r}" fill="{color}"/></pattern>'
        f'<radialGradient id="{pid}g" cx="{cx}" cy="{cy}" r="{radius}" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#000"/></radialGradient>'
        f'<mask id="{pid}m"><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#{pid}g)"/></mask>'
    )
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#{pid}p)" '
            f'mask="url(#{pid}m)" opacity="{opacity}"/>')


def clip_round(svg: SVG, cid, w, h, r=R):
    svg.defs.append(f'<clipPath id="{cid}"><rect width="{w}" height="{h}" rx="{r}"/></clipPath>')
    return f'clip-path="url(#{cid})"'


def scribble_under(x, y, w, color, sw=6, amp=4, delay=.5):
    """Hand-drawn marker underline that draws itself on load."""
    n = max(int(w / 46), 3)
    seg = w / n
    d = f"M{x:.1f} {y:.1f}"
    for i in range(n):
        cx = x + seg * (i + .5)
        cy = y + (amp * 2 if i % 2 else -amp * 2)
        d += f"Q{cx:.1f} {cy:.1f} {x + seg * (i + 1):.1f} {y + (1 if i % 2 else -1) * amp * .3:.1f}"
    return (f'<path d="{d}" pathLength="1" class="draw" style="animation-delay:{delay}s" '
            f'fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" '
            f'stroke-linejoin="round" opacity=".9"/>')


# ─────────────────────────────────────────────────────────────── ticker
def ticker_layer(svg: SVG, items, y0, h, fg, star, accent, direction, speed, size, tid):
    anton = FONTS["anton"]
    marker = FONTS["marker"]
    gap, star_r = 30, 11
    layout, x = [], 0.0
    for it in items:
        txt, kind = (it, "anton") if isinstance(it, str) else it
        f = anton if kind == "anton" else marker
        fs = size if kind == "anton" else size * .92
        wdt = f.width(txt, fs, 1.5 if kind == "anton" else 0)
        layout.append((x, txt, kind, fs))
        x += wdt + gap
        layout.append((x + star_r, None, "star", 0))
        x += star_r * 2 + gap
    period = x
    base = y0 + h / 2 + anton.cap * size / 2
    copies = math.ceil((W + period) / period) + 1
    parts = []
    for k in range(copies):
        off = k * period
        for lx, txt, kind, fs in layout:
            if kind == "star":
                parts.append(sparkle(off + lx, y0 + h / 2, star_r, star))
            elif kind == "anton":
                parts.append(svg.text(off + lx, base, txt, "anton", fs, fg, ls=1.5))
            else:
                parts.append(svg.text(off + lx, base + 2, txt, "marker", fs, accent))
    dur = period / speed
    frm, to = ("0", f"-{period:.1f}") if direction == "left" else (f"-{period:.1f}", "0")
    svg.css.append(
        f".{tid}{{animation:{tid}k {dur:.2f}s linear infinite}}"
        f"@keyframes {tid}k{{from{{transform:translateX({frm}px)}}to{{transform:translateX({to}px)}}}}"
    )
    return f'<g class="{tid}">{"".join(parts)}</g>'


# ─────────────────────────────────────────────────────────────── hero
def build_hero(poster_jpg: Path) -> str:
    th = 66
    pw, ph = 1159, 1358
    s = W / pw
    img_h = ph * s
    H = th * 2 + img_h
    svg = SVG(W, H, "Sreeram Venugopal — Founder of SciPhyLabs, researcher, author, developer. "
                    "Poster: Making things that matter.")
    raw = poster_jpg.read_bytes()
    try:  # re-encode lighter for embedding (the hero must stay one self-contained file)
        from PIL import Image
        buf = io.BytesIO()
        Image.open(io.BytesIO(raw)).convert("RGB").save(buf, "JPEG", quality=80, optimize=True, progressive=True)
        raw = buf.getvalue()
    except ImportError:
        pass
    b64 = base64.b64encode(raw).decode()
    svg.defs.append('<clipPath id="tt"><rect width="1200" height="66"/></clipPath>')
    svg.defs.append(f'<clipPath id="tb"><rect y="{th + img_h:.1f}" width="1200" height="66"/></clipPath>')
    # top tape
    svg.add(f'<rect width="{W}" height="{th}" fill="{C["red"]}"/>')
    svg.add(f'<g clip-path="url(#tt)">' + ticker_layer(
        svg, TICKER_TOP, 0, th, C["cream"], C["cream"], C["cream"], "left", 70, 34, "tka") + "</g>")
    svg.add(f'<rect y="{th - 3}" width="{W}" height="3" fill="{C["ink"]}"/>')
    # poster
    svg.add(f'<image x="0" y="{th}" width="{W}" height="{img_h:.1f}" preserveAspectRatio="none" '
            f'href="data:image/jpeg;base64,{b64}"/>')

    def P(x, y):
        return x * s, th + y * s

    # live glints on the poster's own sparkles
    svg.defs.append(
        f'<radialGradient id="glow"><stop offset="0" stop-color="{C["cream"]}" stop-opacity=".9"/>'
        f'<stop offset="1" stop-color="{C["cream"]}" stop-opacity="0"/></radialGradient>')
    for i, (x, y, r) in enumerate([(302, 81, 30), (392, 619, 26), (554, 519, 18)]):
        cx, cy = P(x, y)
        d = f"animation-delay:{i * .9:.1f}s"
        svg.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 1.5:.0f}" fill="url(#glow)" class="tw" style="{d}"/>')
        svg.add(sparkle(cx, cy, r * 1.15, C["cream"], "tw", d + ";animation-duration:2.8s"))
    # "● ONLINE" status pulse
    cx, cy = P(970.4, 43.7)
    svg.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="none" stroke="{C["red"]}" stroke-width="2.5">'
            '<animate attributeName="r" values="5;24" dur="1.8s" repeatCount="indefinite"/>'
            '<animate attributeName="opacity" values=".9;0" dur="1.8s" repeatCount="indefinite"/></circle>')
    # bottom tape
    y0 = th + img_h
    svg.add(f'<rect y="{y0:.1f}" width="{W}" height="{th}" fill="{C["paper"]}"/>')
    svg.add(f'<rect y="{y0:.1f}" width="{W}" height="3" fill="{C["ink"]}"/>')
    svg.add(f'<g clip-path="url(#tb)">' + ticker_layer(
        svg, TICKER_BOTTOM, y0, th, C["ink"], C["red"], C["red"], "right", 60, 32, "tkb") + "</g>")
    return svg.render()


# ─────────────────────────────────────────────────────────────── section header
def build_header(idx, title, kicker, note) -> str:
    H = 186
    svg = SVG(W, H, f"{idx} — {title} {kicker}")
    anton, mono, mk = FONTS["anton"], FONTS["mono"], FONTS["marker"]
    cp = clip_round(svg, "c", W, H)
    svg.add(f'<g {cp}>')
    svg.add(f'<rect width="{W}" height="{H}" fill="{C["paper"]}"/>')
    svg.add(halftone(svg, "h", C["red"], 700, 0, 500, H, 1200, 0, 430, .42))
    # oversized outline index
    nsize = 168
    nbase = H / 2 + anton.cap * nsize / 2
    svg.add(svg.text(40, nbase, idx, "anton", nsize, "none", cls="rise",
                     extra=f'stroke="{C["red"]}" stroke-width="2.4"'))
    nx = 40 + anton.width(idx, nsize) + 36
    svg.add(f'<rect x="{nx - 18}" y="40" width="2" height="{H - 80}" fill="{C["ink"]}" opacity=".18"/>')
    # title + kicker
    tsize = 78
    svg.add(svg.text(nx, 106, title, "anton", tsize, C["ink"], ls=1, cls="rise",
                     style="animation-delay:.1s"))
    tw = anton.width(title, tsize, 1)
    svg.add(scribble_under(nx + 2, 127, min(tw * .58, 380), C["red"], sw=5.5, amp=2.6, delay=.55))
    svg.add(svg.text(nx, 160, kicker, "mono", 17, C["muted"], ls=2.4, cls="rise",
                     style="animation-delay:.25s"))
    # marker note + hand-drawn arrow, top-right
    msize = 33
    mw = mk.width(note, msize)
    mx = W - 52 - mw
    mx = max(mx, nx + tw + 40)
    svg.add(f'<g transform="rotate(-6 {mx + mw / 2:.0f} 70)">'
            + svg.text(mx, 80, note, "marker", msize, C["red"], cls="pop", style="animation-delay:.9s")
            + "</g>")
    ax = mx + mw * .35
    svg.add(f'<path d="M{ax:.0f} 104 C{ax - 10:.0f} 140 {ax - 50:.0f} 150 {ax - 92:.0f} 142" '
            f'pathLength="1" class="draw" style="animation-delay:1.2s;animation-duration:.7s" '
            f'fill="none" stroke="{C["red"]}" stroke-width="3.4" stroke-linecap="round"/>')
    svg.add(f'<path d="M{ax - 78:.0f} 130 L{ax - 93:.0f} 142 L{ax - 77:.0f} 153" pathLength="1" '
            f'class="draw" style="animation-delay:1.75s;animation-duration:.3s" fill="none" '
            f'stroke="{C["red"]}" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/>')
    svg.add(sparkle(W - 40, 150, 13, C["ink"], "tw"))
    svg.add(sparkle(W - 70, 166, 6, C["red"], "tw", "animation-delay:1.3s"))
    svg.add("</g>")
    return svg.render()


# ─────────────────────────────────────────────────────────────── terminal
def build_terminal() -> str:
    fs, lh, pad = 22, 40, 56
    mono = FONTS["mono"]
    cw = mono.width("M", fs)
    top = 112
    H = top + lh * (len(TERMINAL) + 1) + 34
    svg = SVG(W, H, "Terminal: whoami — Sreeram Venugopal, founder of SciPhyLabs. "
                    + " ".join(t for _, t in TERMINAL))
    svg.add(f'<rect width="{W}" height="{H}" rx="{R}" fill="{C["ink"]}"/>')
    svg.add(f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="{R}" fill="none" '
            f'stroke="{C["red"]}" stroke-opacity=".55" stroke-width="2"/>')
    # window chrome
    for i, col in enumerate([C["red_hot"], "#D9915F", C["paper2"]]):
        svg.add(f'<circle cx="{pad + i * 28}" cy="46" r="8" fill="{col}"/>')
    svg.add(svg.text(W / 2, 53, "sreeram@sciphylabs: ~/lab", "mono", 18, C["muted_ink"], anchor="middle"))
    svg.add(svg.text(W - pad, 53, "zsh", "mono", 16, C["muted_ink"], anchor="end"))
    svg.add(f'<rect x="0" y="80" width="{W}" height="1.5" fill="{C["paper"]}" opacity=".12"/>')
    svg.defs.append(f'<clipPath id="tc"><rect x="20" y="84" width="{W - 40}" height="{H - 100}"/></clipPath>')
    svg.css.append(".cv{animation-fill-mode:backwards}"
                   ".car{opacity:0;animation-fill-mode:none}"
                   "@keyframes caretOn{0%,100%{opacity:1}}"
                   "@keyframes blink{50%{opacity:0}}")
    t = 0.5
    body = []
    rows = TERMINAL + [("$", "")]
    for i, (kind, txt) in enumerate(rows):
        y = top + i * lh
        x = pad
        if kind == "$":
            body.append(svg.text(x, y, "$", "monob", fs, C["red_hot"]))
            body.append(svg.text(x + cw * 2, y, txt, "monob" if txt else "mono", fs, C["cream"])
                        if txt else "")
        else:
            body.append(svg.text(x, y, "›", "mono", fs, C["muted_ink"]))
            col = C["paper"] if i != len(rows) - 2 else C["red_hot"]
            body.append(svg.text(x + cw * 2, y, txt, "mono", fs, col))
        tx = x + cw * 2
        n = len(txt)
        last = i == len(rows) - 1
        if last:
            body.append(f'<rect x="{tx:.1f}" y="{y - fs * .78:.1f}" width="{cw * .9:.1f}" '
                        f'height="{fs * .98:.1f}" fill="{C["red_hot"]}" '
                        f'style="animation:blink 1.05s steps(1) infinite"/>')
        # cover that slides right to "type" the line
        if kind == "$" and n:
            dur = n * 0.042
            dist = n * cw
            kf = f"ty{i}"
            svg.css.append(f"@keyframes {kf}{{from{{transform:translateX(0)}}to{{transform:translateX({dist:.1f}px)}}}}")
            body.append(
                f'<g class="cv" style="animation-timing-function:steps({n},end);transform:translateX({dist:.1f}px);'
                f'animation-name:{kf};animation-duration:{dur:.2f}s;animation-delay:{t:.2f}s">'
                f'<rect x="{tx - 2:.1f}" y="{y - lh * .74:.1f}" width="{W:.0f}" height="{lh}" fill="{C["ink"]}"/>'
                f'<rect x="{tx:.1f}" y="{y - fs * .78:.1f}" width="{cw * .9:.1f}" height="{fs * .98:.1f}" '
                f'fill="{C["red_hot"]}" class="car" style="animation-name:caretOn;'
                f'animation-duration:{dur:.2f}s;animation-delay:{t:.2f}s"/></g>')
            # hide the "$" too until the line starts
            body.append(
                f'<rect x="{x - 4:.1f}" y="{y - lh * .74:.1f}" width="{cw * 2:.1f}" height="{lh}" '
                f'fill="{C["ink"]}" style="opacity:0;animation:hide{i} .01s {t - .3:.2f}s backwards"/>')
            svg.css.append(f"@keyframes hide{i}{{from{{opacity:1}}to{{opacity:0}}}}")
            t += dur + 0.28
        else:
            body.append(
                f'<rect x="{x - 4:.1f}" y="{y - lh * .74:.1f}" width="{W:.0f}" height="{lh}" '
                f'fill="{C["ink"]}" style="opacity:0;animation:hide{i} .01s {t:.2f}s backwards"/>')
            svg.css.append(f"@keyframes hide{i}{{from{{opacity:1}}to{{opacity:0}}}}")
            t += 0.12 if kind == ">" else 0.3
            if kind == ">" and (i + 1 < len(rows) and rows[i + 1][0] == "$"):
                t += 0.32
    svg.add('<g clip-path="url(#tc)">' + "".join(body) + "</g>")
    return svg.render()


# ─────────────────────────────────────────────────────────────── cards
def pill_button(svg, x, y, label, bg, fg, shadow, border, size=18, h=50, pad=24):
    mono = FONTS["monob"]
    tw = mono.width(label, size, 2)
    w = pad + tw + 14 + 16 + pad
    out = [f'<rect x="{x + 5}" y="{y + 5}" width="{w:.1f}" height="{h}" rx="{h / 2}" fill="{shadow}"/>',
           f'<rect x="{x}" y="{y}" width="{w:.1f}" height="{h}" rx="{h / 2}" fill="{bg}" '
           f'stroke="{border}" stroke-width="2"/>',
           svg.text(x + pad, y + h / 2 + size * .35, label, "monob", size, fg, ls=2),
           arrow_out(x + pad + tw + 14, y + h / 2 + 8, 16, fg)]
    return "".join(out), w


def build_feature() -> str:
    H = 480
    svg = SVG(W, H, "SciPhyLabs — Physics, rebuilt from scratch. 400+ interactive simulations, notes, "
                    "formulas and PYQs for Class 11–12, JEE, NEET, CUET, AP and SAT. Visit sciphylabs.com")
    anton = FONTS["anton"]
    cp = clip_round(svg, "c", W, H)
    svg.add(f'<g {cp}>')
    svg.add(f'<rect width="{W}" height="{H}" fill="{C["red"]}"/>')
    svg.add(halftone(svg, "h", C["red_deep"], 560, 0, 640, H, 960, 220, 420, .9, step=13, r=2.8))
    svg.add(svg.text(56, 72, "001 / FEATURED · FOUNDER · EST. 2023", "mono", 16, C["cream"], ls=3,
                     cls="rise", style="opacity:.85"))
    tsize = 142
    svg.add(svg.text(50, 222, "SCIPHYLABS", "anton", tsize, C["cream"], ls=1, cls="rise",
                     style="animation-delay:.1s"))
    tw = anton.width("SCIPHYLABS", tsize, 1)
    svg.add(svg.text(58, 284, "Physics, rebuilt from scratch.", "serif", 46, C["cream"], cls="rise",
                     style="animation-delay:.2s"))
    for j, line in enumerate(["400+ interactive simulations, chapter notes, formulas & PYQs",
                              "for Class 11–12, JEE, NEET, CUET, AP & SAT — built for schools."]):
        svg.add(svg.text(58, 336 + j * 32, line, "sg", 23, C["cream"], cls="rise",
                         style=f"opacity:.9;animation-delay:{.3 + j * .08:.2f}s"))
    btn, _ = pill_button(svg, 58, 396, "VISIT SCIPHYLABS.COM", C["paper"], C["ink"], C["ink"], C["ink"])
    svg.add(f'<g class="rise" style="animation-delay:.45s">{btn}</g>')
    # atom — orbiting electrons
    ax, ay = max(948, 50 + tw + 230), 206
    rx, ry = 168, 58
    atom = []
    for k, ang in enumerate([0, 60, -60]):
        pid = f"o{k}"
        d = f"M{ax - rx} {ay}a{rx} {ry} 0 1 0 {2 * rx} 0a{rx} {ry} 0 1 0 {-2 * rx} 0"
        atom.append(f'<g transform="rotate({ang} {ax} {ay})">'
                    f'<path id="{pid}" d="{d}" fill="none" stroke="{C["cream"]}" stroke-opacity=".6" stroke-width="2"/>'
                    f'<circle r="7" fill="{C["cream"]}"><animateMotion dur="{4.2 + k * 1.3:.1f}s" '
                    f'repeatCount="indefinite" begin="{-k * 1.1:.1f}s"><mpath href="#{pid}" xlink:href="#{pid}"/></animateMotion></circle>'
                    f'</g>')
    atom.append(f'<circle cx="{ax}" cy="{ay}" r="24" fill="{C["cream"]}"/>')
    atom.append(f'<circle cx="{ax}" cy="{ay}" r="11" fill="{C["red"]}"/>')
    svg.add("".join(atom))
    # rotating stamp
    sx, sy, sr = 1090, 398, 50
    stamp_txt = "EST · 2023 · PUDUCHERRY · INDIA · "
    svg.defs.append(f'<path id="sp" d="M{sx - sr + 10} {sy}a{sr - 10} {sr - 10} 0 1 1 {2 * (sr - 10)} 0'
                    f'a{sr - 10} {sr - 10} 0 1 1 {-2 * (sr - 10)} 0"/>')
    circ = 2 * math.pi * (sr - 10)
    svg.used["monob"].update(stamp_txt)
    svg.add(f'<circle cx="{sx}" cy="{sy}" r="{sr + 6}" fill="{C["ink"]}"/>'
            f'<g class="spin" style="animation-duration:18s">'
            f'<circle cx="{sx}" cy="{sy}" r="{sr + 6}" fill="none"/>'
            f'<text class="f-monob" font-size="11.5" fill="{C["cream"]}" letter-spacing="0">'
            f'<textPath href="#sp" xlink:href="#sp" textLength="{circ - 2:.1f}" lengthAdjust="spacing">{esc(stamp_txt)}</textPath></text></g>'
            + sparkle(sx, sy, 14, C["red_hot"], "tw"))
    svg.add(sparkle(1150, 60, 12, C["cream"], "tw"))
    svg.add(sparkle(760, 420, 7, C["cream"], "tw", "animation-delay:1.1s"))
    svg.add("</g>")
    return svg.render()


def build_repo_card(num, name, desc_lines, chip, dark) -> str:
    w, H = 590, 330
    bg, fg = (C["ink"], C["cream"]) if dark else (C["paper"], C["ink"])
    sub = C["muted_ink"] if dark else C["muted"]
    svg = SVG(w, H, f"Repository {name}: {' '.join(desc_lines)} View source on GitHub")
    anton = FONTS["anton"]
    cp = clip_round(svg, "c", w, H)
    svg.add(f'<g {cp}><rect width="{w}" height="{H}" fill="{bg}"/>')
    svg.add(svg.text(w + 30, H + 48, num, "anton", 300, "none", anchor="end",
                     extra=f'stroke="{C["red"] if not dark else C["red_hot"]}" stroke-width="2" opacity=".35"'))
    svg.add(svg.text(38, 62, f"{num} / REPOSITORY", "mono", 15, sub, ls=3))
    tsize = 56 if anton.width(name, 56, 1) < w - 76 else 48
    svg.add(svg.text(36, 136, name.upper(), "anton", tsize, fg, ls=1, cls="rise"))
    for j, line in enumerate(desc_lines):
        svg.add(svg.text(38, 184 + j * 30, line, "sg", 21, fg, style="opacity:.85"))
    # chip
    mono = FONTS["mono"]
    cwid = mono.width(chip, 13, 2) + 30 + (16 if dark else 0)
    svg.add(f'<rect x="38" y="262" width="{cwid:.0f}" height="32" rx="16" fill="none" stroke="{fg}" '
            f'stroke-opacity=".5" stroke-width="1.5"/>')
    cx = 53
    if dark:
        svg.add(f'<circle cx="{cx + 2}" cy="278" r="5" fill="#3178C6"/>')
        cx += 16
    svg.add(svg.text(cx, 283, chip, "mono", 13, fg, ls=2))
    link_col = C["red_hot"] if dark else C["red"]
    lw = FONTS["monob"].width("VIEW SOURCE", 16, 2)
    svg.add(svg.text(w - 38 - 26 - lw, 284, "VIEW SOURCE", "monob", 16, link_col, ls=2))
    svg.add(arrow_out(w - 38 - 14, 286, 14, link_col, 2.4))
    svg.add(sparkle(w - 46, 52, 11, link_col, "tw"))
    svg.add("</g>")
    if dark:
        svg.add(f'<rect x="1" y="1" width="{w - 2}" height="{H - 2}" rx="{R}" fill="none" '
                f'stroke="{C["red"]}" stroke-opacity=".55" stroke-width="2"/>')
    return svg.render()


def build_research() -> str:
    H = 410
    svg = SVG(W, H, "White paper (preprint, Sept 2026): Where Virtual Laboratories Cannot Reach. "
                    "Finding: at least 537,486 Indian schools cannot run a cloud-connected virtual "
                    "science lab. UDISE+ 2024–25 data.")
    anton = FONTS["anton"]
    cp = clip_round(svg, "c", W, H)
    svg.add(f'<g {cp}><rect width="{W}" height="{H}" fill="{C["paper"]}"/>')
    for y in range(92, H, 40):
        svg.add(f'<rect x="0" y="{y}" width="{W}" height="1.2" fill="{C["rule"]}"/>')
    svg.add(f'<rect x="92" y="0" width="1.6" height="{H}" fill="{C["red"]}" opacity=".55"/>')
    for y in (90, 205, 320):
        svg.add(f'<circle cx="46" cy="{y}" r="13" fill="{C["paper2"]}" stroke="{C["rule"]}" stroke-width="1.5"/>')
    svg.add(svg.text(122, 68, "WHITE PAPER · PREPRINT · SEPT 2026", "mono", 15, C["red"], ls=3))
    svg.add(svg.text(120, 146, "Where Virtual Laboratories", "serif", 62, C["ink"], cls="rise"))
    svg.add(svg.text(120, 206, "Cannot Reach.", "serif", 62, C["ink"], cls="rise", style="animation-delay:.1s"))
    for j, line in enumerate(["Which Indian schools can actually run a cloud-connected",
                              "virtual science lab? A nationwide look at UDISE+ 2024–25 data."]):
        svg.add(svg.text(122, 254 + j * 30, line, "sg", 21, C["ink"], style="opacity:.85"))
    btn, _ = pill_button(svg, 122, 322, "READ THE PAPER (PDF)", C["ink"], C["cream"], C["red"], C["ink"],
                         size=16, h=46)
    svg.add(btn)
    # stat panel
    px = 800
    svg.add(f'<rect x="{px}" y="96" width="340" height="250" rx="14" fill="{C["cream"]}" '
            f'stroke="{C["ink"]}" stroke-width="2"/>')
    svg.add(f'<rect x="{px + 7}" y="103" width="340" height="250" rx="14" fill="none" '
            f'stroke="{C["ink"]}" stroke-width="2" opacity=".18"/>')
    svg.add(svg.text(px + 28, 138, "AT LEAST", "mono", 14, C["muted"], ls=3))
    svg.add(svg.text(px + 26, 224, "537,486", "anton", 80, C["red"], ls=1, cls="pop",
                     style="animation-delay:.4s"))
    for j, line in enumerate(["INDIAN SCHOOLS CAN'T RUN", "A CLOUD-CONNECTED", "VIRTUAL SCIENCE LAB"]):
        svg.add(svg.text(px + 28, 276 + j * 22, line, "monob", 14, C["ink"], ls=1.6))
    svg.add(f'<g transform="rotate(-6 1010 70)">'
            + svg.text(880, 76, "the gap is real.", "marker", 30, C["red"], cls="pop",
                       style="animation-delay:1s") + "</g>")
    svg.add(scribble_under(px + 28, 242, 240, C["red"], sw=4, amp=2.2, delay=.9))
    svg.add("</g>")
    return svg.render()


def build_exploring() -> str:
    mono = FONTS["monob"]
    fs, h, gx, gy = 17, 52, 16, 20
    styles = [(C["red"], C["cream"], C["ink"]), (C["ink"], C["cream"], C["red"]),
              (C["paper"], C["ink"], C["ink"])]
    rots = [-3, 2, -1.5, 3, -2, 1.2, -2.6, 2.2]
    rows, row, x = [], [], 0
    for lab in EXPLORING:
        w = mono.width(lab, fs, 2) + 48
        if x + w > W - 40 and row:
            rows.append((row, x - gx))
            row, x = [], 0
        row.append((lab, w))
        x += w + gx
    rows.append((row, x - gx))
    H = len(rows) * (h + gy) + 24
    svg = SVG(W, H, "Currently exploring: " + ", ".join(EXPLORING))
    k = 0
    for r, (items, rw) in enumerate(rows):
        x = (W - rw) / 2
        y = 16 + r * (h + gy)
        for lab, w in items:
            bg, fg, sh = styles[k % 3]
            rot = rots[k % len(rots)]
            cx, cy = x + w / 2, y + h / 2
            svg.add(f'<g transform="rotate({rot} {cx:.0f} {cy:.0f})"><g class="pop" '
                    f'style="animation-delay:{.1 + k * .09:.2f}s">'
                    f'<rect x="{x + 4:.1f}" y="{y + 4}" width="{w:.1f}" height="{h}" rx="10" fill="{sh}"/>'
                    f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{h}" rx="10" fill="{bg}" '
                    f'stroke="{"#5A4440" if bg == C["ink"] else C["ink"]}" stroke-width="2"/>'
                    + svg.text(x + 24, y + h / 2 + fs * .36, lab, "monob", fs, fg, ls=2)
                    + "</g></g>")
            x += w + gx
            k += 1
    return svg.render()


TOOLBOX = [
    ("01 / LANGUAGES", ["python", "typescript", "javascript"]),
    ("02 / FRONTEND", ["react", "nextjs", "html5", "css"]),
    ("03 / BACKEND", ["nodejs", "supabase"]),
    ("04 / SHIP IT", ["git", "github", "vercel"]),
]


def build_toolbox(icons: dict) -> str:
    tile, gap, colgap = 72, 18, 36
    widths = [len(t) * tile + (len(t) - 1) * gap for _, t in TOOLBOX]
    total = sum(widths) + colgap * (len(TOOLBOX) - 1)
    x0 = (W - total) / 2
    H = 226
    names = [icons[k]["title"].upper() for _, t in TOOLBOX for k in t]
    svg = SVG(W, H, "Toolbox: " + ", ".join(icons[k]["title"] for _, t in TOOLBOX for k in t))
    cp = clip_round(svg, "c", W, H)
    svg.add(f'<g {cp}><rect width="{W}" height="{H}" fill="{C["paper"]}"/>')
    svg.add(halftone(svg, "h", C["red"], 0, 0, 420, H, 0, H, 380, .3))
    x = x0
    k = 0
    for (label, tools), cw in zip(TOOLBOX, widths):
        svg.add(svg.text(x, 52, label, "monob", 14, C["red"], ls=2))
        svg.add(f'<rect x="{x}" y="62" width="34" height="3" fill="{C["ink"]}"/>')
        for j, key in enumerate(tools):
            tx = x + j * (tile + gap)
            ty = 82
            ic = icons[key]
            sc = 34 / 24
            svg.add(f'<g class="pop" style="animation-delay:{.15 + k * .07:.2f}s">'
                    f'<rect x="{tx + 4}" y="{ty + 4}" width="{tile}" height="{tile}" rx="16" fill="{C["red"]}"/>'
                    f'<rect x="{tx}" y="{ty}" width="{tile}" height="{tile}" rx="16" fill="{C["ink"]}"/>'
                    f'<path d="{ic["path"]}" fill="{C["cream"]}" transform="translate({tx + (tile - 34) / 2} '
                    f'{ty + (tile - 34) / 2}) scale({sc})"/></g>')
            svg.add(svg.text(tx + tile / 2, ty + tile + 32, ic["title"].upper(), "mono", 13, C["muted"],
                             ls=.2, anchor="middle"))
            k += 1
        x += cw + colgap
        if x < x0 + total:
            svg.add(f'<rect x="{x - colgap / 2 - .75:.1f}" y="40" width="1.5" height="{H - 80}" fill="{C["ink"]}" opacity=".12"/>')
    svg.add(sparkle(W - 30, 34, 10, C["ink"], "tw"))
    svg.add("</g>")
    return svg.render()


def build_footer() -> str:
    H = 450
    svg = SVG(W, H, "Make things that matter. — Sreeram Venugopal, Venu2328, Puducherry, India.")
    cp = clip_round(svg, "c", W, H)
    svg.add(f'<g {cp}><rect width="{W}" height="{H}" fill="{C["ink"]}"/>')
    rnd = random.Random(2328)
    stars = []
    for i in range(70):
        x, y = rnd.uniform(10, W - 10), rnd.uniform(10, H - 10)
        r = rnd.choice([.8, 1, 1.2, 1.5, 2])
        stars.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r}" fill="{C["cream"]}" class="tw" '
                     f'style="animation-delay:{rnd.uniform(0, 3):.2f}s;animation-duration:{rnd.uniform(2, 4.5):.1f}s"/>')
    svg.add("".join(stars))
    # planet
    px, py = 1010, 150
    svg.add(f'<g transform="rotate(-16 {px} {py})">'
            f'<ellipse cx="{px}" cy="{py}" rx="128" ry="26" fill="none" stroke="{C["cream"]}" stroke-width="2" opacity=".7"/>'
            f'<circle cx="{px}" cy="{py}" r="66" fill="{C["red"]}"/>'
            f'<circle cx="{px}" cy="{py}" r="66" fill="url(#hp)" opacity=".5"/>'
            f'<ellipse cx="{px}" cy="{py}" rx="128" ry="26" fill="none" stroke="{C["cream"]}" '
            f'stroke-width="2" clip-path="url(#pf2)"/></g>')
    svg.defs.append(f'<clipPath id="pf2"><rect x="{px - 140}" y="{py}" width="280" height="60"/></clipPath>'
                    f'<pattern id="hp" width="9" height="9" patternUnits="userSpaceOnUse">'
                    f'<circle cx="4.5" cy="4.5" r="1.6" fill="{C["ink"]}"/></pattern>')
    svg.add(svg.text(52, 196, "MAKE THINGS", "anton", 134, C["cream"], ls=2, cls="rise"))
    svg.add(svg.text(52, 330, "THAT MATTER.", "anton", 134, C["red_hot"], ls=2, cls="rise",
                     style="animation-delay:.15s"))
    tw = FONTS["anton"].width("THAT MATTER.", 134, 2)
    svg.add(f'<g transform="rotate(-8 {52 + tw + 120:.0f} 300)">'
            + svg.text(52 + tw + 40, 316, "— sreeram", "marker", 44, C["cream"], cls="pop",
                       style="animation-delay:.9s") + "</g>")
    svg.add(f'<rect x="52" y="372" width="{W - 104}" height="1.5" fill="{C["cream"]}" opacity=".15"/>')
    svg.add(svg.text(52, 412, "VENU2328 · PUDUCHERRY, INDIA · BUILT WITH CURIOSITY", "mono", 15,
                     C["muted_ink"], ls=3))
    svg.add(svg.text(W - 52, 412, "© 2026", "mono", 15, C["muted_ink"], ls=3, anchor="end"))
    svg.add(sparkle(860, 70, 16, C["cream"], "tw"))
    svg.add(sparkle(1140, 300, 10, C["red_hot"], "tw", "animation-delay:.8s"))
    svg.add("</g>")
    svg.add(f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="{R}" fill="none" '
            f'stroke="{C["red"]}" stroke-opacity=".55" stroke-width="2"/>')
    return svg.render()


def build_button(label, variant) -> str:
    mono = FONTS["monob"]
    fs, h, pad = 17, 56, 22
    tw = mono.width(label, fs, 2.4)
    w = pad + tw + 12 + 14 + pad
    bg, fg, sh = {"red": (C["red"], C["cream"], C["ink"]),
                  "ink": (C["ink"], C["cream"], C["red"]),
                  "paper": (C["paper"], C["ink"], C["ink"])}[variant]
    svg = SVG(w + 6, h + 6, label.title())
    svg.css = []
    svg.add(f'<rect x="6" y="6" width="{w:.1f}" height="{h}" rx="9" fill="{sh}"/>')
    svg.add(f'<rect x="1" y="1" width="{w - 2:.1f}" height="{h - 2}" rx="9" fill="{bg}" '
            f'stroke="{"#5A4440" if variant == "ink" else C["ink"]}" stroke-width="2"/>')
    svg.add(svg.text(pad, h / 2 + fs * .36, label, "monob", fs, fg, ls=2.4))
    svg.add(arrow_out(pad + tw + 12, h / 2 + 7, 14, fg, 2.4))
    return svg.render()


def build_nav(idx, label) -> str:
    fs, h, pad = 15, 44, 16
    mono, monob = FONTS["mono"], FONTS["monob"]
    iw = mono.width(idx, fs, 1.5)
    lw = monob.width(label, fs, 2.2)
    w = pad + iw + 10 + lw + pad
    svg = SVG(w, h, f"{idx} {label}")
    svg.css = []
    svg.add(f'<rect x="1" y="1" width="{w - 2:.1f}" height="{h - 2}" rx="{(h - 2) / 2}" fill="{C["paper"]}" '
            f'stroke="{C["ink"]}" stroke-width="1.6"/>')
    svg.add(svg.text(pad, h / 2 + fs * .36, idx, "mono", fs, C["red"], ls=1.5))
    svg.add(svg.text(pad + iw + 10, h / 2 + fs * .36, label, "monob", fs, C["ink"], ls=2.2))
    return svg.render()


# ─────────────────────────────────────────────────────────────── main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--poster", type=Path, help="hero poster JPEG (default: <out>/hero-poster.jpg)")
    a = ap.parse_args()
    for k, f in FONT_FILES.items():
        FONTS[k] = Font(a.fonts / f)
    out: Path = a.out
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "hero.svg": build_hero(a.poster or out / "hero-poster.jpg"),
        "terminal.svg": build_terminal(),
        "card-sciphylabs.svg": build_feature(),
        "card-sciphylabs2026.svg": build_repo_card(
            "02", "SciPhyLabs2026", ["Development repository for the", "SciPhyLabs platform."], "PUBLIC", False),
        "card-devlab.svg": build_repo_card(
            "03", "SreeramVenugopal", ["Personal dev lab — experiments,", "prototypes, learning by building."],
            "TYPESCRIPT", True),
        "card-research.svg": build_research(),
        "exploring.svg": build_exploring(),
        "toolbox.svg": build_toolbox(json.loads((Path(__file__).parent / "icons.json").read_text())),
        "footer.svg": build_footer(),
    }
    for fid, idx, title, kicker, note in HEADERS:
        files[f"h-{fid}.svg"] = build_header(idx, title, kicker, note)
    for fid, (label, variant) in BUTTONS.items():
        files[f"btn-{fid}.svg"] = build_button(label, variant)
    for fid, idx, label in NAV:
        files[f"nav-{fid}.svg"] = build_nav(idx, label)
    for name, content in files.items():
        (out / name).write_text(content, encoding="utf-8")
        print(f"{name:28s} {len(content.encode()) / 1024:7.1f} KB")


if __name__ == "__main__":
    main()
