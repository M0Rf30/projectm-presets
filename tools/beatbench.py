#!/usr/bin/env python3
"""beatbench.py AUDIO preset.milk [preset.milk ...]  -- how visibly does a preset react to real music?

Renders each preset headlessly with tools/render (real time, so a 60 s clip takes 60 s) while
feeding it the audio the way a frontend would, then compares the rendered frames against the
musical onsets found in the audio itself:

  flash%   mean brightness rise in the 7 frames after an onset, relative to the 6 frames before
  motion x peak frame-to-frame change after an onset, relative to the 8 frames before
  chance   the same two numbers for onsets shifted by random offsets (what "no reaction"
           looks like for that preset); z = how many standard deviations obs is above chance

  --probe  instead prints the bass/mid/treb/att ranges projectM actually delivers for the clip
           (uses tools/probe.milk, which encodes the per-frame audio values in the pixels)

Needs numpy, scipy and ffmpeg.  Example, emulating Aulos (30 fps, default mesh):

    tools/beatbench.py song.mp3 --start 60 --dur 60 --fps 30 presets/*.milk
"""
import argparse, os, subprocess, sys, tempfile
import numpy as np
import scipy.signal as sg

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 44100


def decode(path, start, dur):
    cmd = ["ffmpeg", "-loglevel", "error", "-ss", str(start), "-t", str(dur), "-i", path,
           "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def onsets(stereo, hop=441):
    """Musical onset times (s): log-band spectral flux with an adaptive peak threshold."""
    x = stereo.reshape(-1, 2).mean(axis=1)
    f, t, Z = sg.stft(x, fs=SR, nperseg=2048, noverlap=2048 - hop, boundary=None, padded=False)
    S = np.abs(Z)
    edges = np.geomspace(30, 11000, 25)
    B = np.array([S[(f >= edges[i]) & (f < edges[i + 1])].sum(axis=0) for i in range(24)])
    L = np.log1p(B * 20)
    env = np.maximum(L[:, 1:] - L[:, :-1], 0).sum(axis=0)
    t = t[1:]
    fs = SR / hop
    w = int(1.5 * fs) | 1
    mu = sg.convolve(env, np.ones(w) / w, mode="same")
    sd = np.sqrt(np.maximum(sg.convolve((env - mu) ** 2, np.ones(w) / w, mode="same"), 0))
    pk, _ = sg.find_peaks(env, height=mu + 0.9 * sd + 1e-6, distance=int(0.18 * fs))
    t_on, e_on = t[pk], env[pk]
    return t_on[e_on >= np.quantile(e_on, 0.4)]  # strongest 60 %


def render(preset, audio_path, args, w, h, nframes, probe=False):
    """Run tools/render, return per-frame (lum, motion) or probe values."""
    env = dict(os.environ, AUDIO=audio_path, FPS=str(args.fps), FEED=args.feed, GAIN=str(args.gain))
    if not args.small_mesh:
        env["MESH"] = "default"
    p = subprocess.Popen([args.render, preset, str(w), str(h), str(nframes)],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    fs = w * h * 3
    lum, mot, pv, prev = [], [], [], None
    while True:
        b = p.stdout.read(fs)
        while b and len(b) < fs:
            more = p.stdout.read(fs - len(b))
            if not more:
                break
            b += more
        if len(b) < fs:
            break
        f = np.frombuffer(b, np.uint8).reshape(h, w, 3)
        if probe:
            cw = w // 8
            pv.append([round(f[h // 4:3 * h // 4, i * cw + cw // 4:i * cw + 3 * cw // 4, 0].mean() * 32 / 255)
                       + f[h // 4:3 * h // 4, i * cw + cw // 4:i * cw + 3 * cw // 4, 1].mean() / 255
                       for i in range(8)])
        s = f[::4, ::4].astype(np.float32) / 255
        L = s[..., 0] * 0.2126 + s[..., 1] * 0.7152 + s[..., 2] * 0.0722
        lum.append(L.mean())
        mot.append(0.0 if prev is None else np.abs(L - prev).mean())
        prev = L
    p.wait()
    return np.array(lum), np.array(mot), np.array(pv)


def kick_stats(lum, mot, kt, fps, skip, nshuf=300, seed=3):
    T = len(lum) / fps

    def stat(k):
        idx = np.round(k * fps).astype(int)
        idx = idx[(idx > 8) & (idx < len(lum) - 8) & (idx > skip)]
        fl = np.mean([(lum[i:i + 7].max() - lum[i - 6:i].mean()) / lum[i - 6:i].mean() for i in idx]) * 100
        mr = np.mean([mot[i:i + 5].max() / (mot[i - 8:i].mean() + 1e-9) for i in idx])
        return np.array([fl, mr])

    obs = stat(kt)
    rng = np.random.default_rng(seed)
    sh = np.array([stat((kt + rng.uniform(0.7, T - 1.5)) % T) for _ in range(nshuf)])
    z = (obs - sh.mean(axis=0)) / (sh.std(axis=0) + 1e-12)
    return obs, sh.mean(axis=0), z


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio")
    ap.add_argument("presets", nargs="*")
    ap.add_argument("--start", type=float, default=30)
    ap.add_argument("--dur", type=float, default=45)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--feed", default="full", choices=["full", "aulos_old", "last576"])
    ap.add_argument("--gain", type=float, default=1.0)
    ap.add_argument("--size", default="480x270")
    ap.add_argument("--small-mesh", action="store_true", help="use tools/render's 96x72 mesh instead of projectM's default (Aulos)")
    ap.add_argument("--render", default=os.path.join(HERE, "render"))
    ap.add_argument("--probe", action="store_true", help="print projectM's bass/mid/treb ranges for the clip")
    args = ap.parse_args()
    if not args.probe and not args.presets:
        ap.error("give at least one preset (or --probe)")
    w, h = map(int, args.size.split("x"))
    pcm = decode(args.audio, args.start, args.dur)
    n = int(len(pcm) / 2 / SR * args.fps)
    with tempfile.NamedTemporaryFile(suffix=".f32", delete=False) as tf:
        tf.write(pcm.tobytes())
    try:
        if args.probe:
            _, _, pv = render(os.path.join(HERE, "probe.milk"), tf.name, args, 160, 90, n, probe=True)
            names = ["bass", "bass_att", "mid", "mid_att", "treb", "treb_att"]
            print(f"{'':9s} {'mean':>6s} {'p5':>6s} {'p50':>6s} {'p95':>6s} {'p99':>6s} {'max':>6s}")
            for i, nm in enumerate(names):
                x = pv[min(100, len(pv) // 4):, i]
                print(f"{nm:9s} " + " ".join(f"{v:6.2f}" for v in [x.mean(), *np.percentile(x, [5, 50, 95, 99]), x.max()]))
            return
        kt = onsets(pcm)
        print(f"{len(kt)} strong onsets in {args.dur:.0f}s ({len(kt) / args.dur:.1f}/s); fps={args.fps} feed={args.feed} gain={args.gain}")
        print(f"{'preset':44s} {'flash%':>7s} {'chance':>7s} {'z':>5s} | {'motion x':>8s} {'chance':>7s} {'z':>5s}")
        for p in args.presets:
            lum, mot, _ = render(p, tf.name, args, w, h, n)
            if len(lum) < n * 0.9:
                print(f"{p[-44:]:44s} render failed")
                continue
            o, c, z = kick_stats(lum, mot, kt, args.fps, skip=int(3 * args.fps))
            print(f"{p[-44:]:44s} {o[0]:7.2f} {c[0]:7.2f} {z[0]:5.1f} | {o[1]:8.2f} {c[1]:7.2f} {z[1]:5.1f}")
    finally:
        os.unlink(tf.name)


if __name__ == "__main__":
    main()
