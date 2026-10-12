#!/usr/bin/env python3
"""mkmilk2.py milk2/src/<slug> [...] -> milk2/<title>.milk2

A source directory holds a.milk, b.milk (two ordinary MilkDrop 2 presets) and milk2.json:

  {"title": "Event Horizon",              # file becomes "M0Rf30 - Event Horizon.milk2"
   "name1": "Event Horizon A - Singularity",
   "name2": "Event Horizon B - Supernova",
   "pattern": "cercle",                    # one of the 30 MD3 blend patterns
   "progress": 0.55,                       # 0..1, where the frozen blend sits (PRESET2 share)
   "direction": -1,                        # -1 or 1 (cercle/triangle/corner/patches use it)
   "random": [0.58, 0.33, 0.94, 0.29, 0.53]}

The writer follows MilkDrop 3.37's saver (lactea-preset `write_milk2`). It also rejects what the
MD3 loader mis-reads: it scans in fgets(255)/fgets(256) chunks, so a line of >= 250 bytes shifts
every later marker, and header keys are matched by substring anywhere in the file.
"""
import json, os, re, sys, time

PATTERNS = """zoom side plasma plasma2 plasma3 cercle square snail snail2 snail3 triangle donuts corner
patches checkerboard bubbles stars stars2 clock nuclear arrow cisor wave curtain vertical horizontal
linesvertical lineshorizontal cross cross2""".split()
KEYS = ["blending_pattern", "blending_progress", "blending_direction", "sprite=1",
        "random_1", "random_2", "random_3", "random_4", "random_5",
        "[PRESET1_", "[PRESET2_", "[SPRITE1_"]
MAXLINE = 250


def half(path):
    raw = open(path, "rb").read().replace(b"\r\n", b"\n")
    if not raw.endswith(b"\n"):
        raw += b"\n"
    for n, line in enumerate(raw.split(b"\n"), 1):
        if len(line) >= MAXLINE:
            sys.exit(f"{path}:{n}: line is {len(line)} bytes (limit {MAXLINE - 1}); split it")
        for k in KEYS:
            if k.encode() in line:
                sys.exit(f"{path}:{n}: contains {k!r}, which the .milk2 header scanner would match")
    if b"[preset00]" not in raw:
        sys.exit(f"{path}: no [preset00] section")
    return raw


def build(src):
    cfg = json.load(open(os.path.join(src, "milk2.json")))
    if cfg["pattern"] not in PATTERNS:
        sys.exit(f"{src}: unknown pattern {cfg['pattern']!r}")
    rnd = cfg.get("random", [0.5] * 5)
    assert len(rnd) == 5
    a, b = half(os.path.join(src, "a.milk")), half(os.path.join(src, "b.milk"))
    out = bytearray()
    ln = lambda s: out.extend(s.encode() + b"\n")
    ln("Created with MILKDROP 3.37 on " + time.strftime("%d/%m/%Y at %H:%M:%S"))
    ln("github.com/M0Rf30/lactea")
    ln("")
    ln(f"blending_pattern={cfg['pattern']}")
    ln(f"blending_progress={float(cfg['progress']):.2f}")
    ln(f"blending_direction={int(cfg.get('direction', 1))}")
    for i, r in enumerate(rnd, 1):
        ln(f"random_{i}={float(r):.6f}")
    ln("")
    ln("[PRESET1_BEGIN]")
    ln("NAME=" + cfg["name1"])
    out += a
    ln("[PRESET1_END]")
    ln("")
    ln("[PRESET2_BEGIN]")
    ln("NAME=" + cfg["name2"])
    out += b
    ln("[PRESET2_END]")
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(src))),
                       f"M0Rf30 - {cfg['title']}.milk2")
    open(dst, "wb").write(out)
    print(dst)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for s in sys.argv[1:]:
        build(s.rstrip("/"))
