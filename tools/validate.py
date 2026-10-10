#!/usr/bin/env python3
"""validate.py preset.milk -> checks warp/comp shaders actually compile in projectM.
projectM silently falls back on shader errors, so we inject `ret = magenta` at the end
of each shader body and verify the rendered output turns magenta."""
import re, subprocess, sys, os, tempfile

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "render")
W, H = 64, 36


def lines(src, key):
    return [l for l in src.splitlines() if re.match(rf"{key}_\d+=", l)]


def inject(src, key):
    ls = src.splitlines()
    idx = [i for i, l in enumerate(ls) if re.match(rf"{key}_\d+=", l)]
    last = idx[-1]
    body = ls[last]
    k = body.rfind("}")
    ls[last] = body[:k] + " ret = float3(1,0,1); " + body[k:]
    return "\n".join(ls) + "\n"


def render_mean(src):
    with tempfile.NamedTemporaryFile("w", suffix=".milk", delete=False) as f:
        f.write(src)
    p = subprocess.run([R, f.name, str(W), str(H), "60"], capture_output=True)
    os.unlink(f.name)
    if p.returncode:
        return None, p.stderr.decode()
    fr = p.stdout[-W * H * 3:]
    n = W * H
    return tuple(sum(fr[c::3]) / n for c in range(3)), ""


def magenta(m):
    return m and m[0] > 200 and m[2] > 200 and m[1] < 60


src = open(sys.argv[1]).read()
ok = True
m, err = render_mean(src)
if m is None:
    print("LOAD FAIL", err); sys.exit(1)
print(f"base render mean rgb={tuple(round(x) for x in m)}")
if lines(src, "comp"):
    m, _ = render_mean(inject(src, "comp"))
    good = magenta(m); ok &= good
    print("comp shader:", "OK" if good else f"FAILED TO COMPILE (mean={m})")
if lines(src, "warp"):
    s2 = "\n".join(l for l in src.splitlines() if not re.match(r"comp_\d+=", l)) + "\n"
    m, _ = render_mean(inject(s2, "warp"))
    good = magenta(m); ok &= good
    print("warp shader:", "OK" if good else f"FAILED TO COMPILE (mean={m})")
sys.exit(0 if ok else 1)
