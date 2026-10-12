#!/usr/bin/env python3
"""synth.py out.wav [seconds] -> deterministic 44.1 kHz stereo test track for `lactea --audio-wav`.

128 bpm: kick on every beat, snare on 2 and 4, noise hats on the off-beats, a 4-bar bass/arpeggio
chord loop, and a breakdown (no kick) every 8 bars so presets see both loud and quiet passages."""
import array, math, random, sys, wave

out = sys.argv[1]
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 40.0
sr = 44100
n = int(sr * dur)
beat = 60 / 128
rng = random.Random(7)
L = array.array("h", bytes(2 * n))
R = array.array("h", bytes(2 * n))
chords = [(55.0, [220.0, 261.63, 329.63]), (43.65, [174.61, 220.0, 261.63]),
          (65.41, [261.63, 329.63, 392.0]), (49.0, [196.0, 246.94, 293.66])]
for i in range(n):
    t = i / sr
    b = t / beat
    ph = (t % beat)
    bar = int(b // 4)
    breakdown = (bar % 8) >= 6
    k = 0.0
    if not breakdown:
        k = 0.75 * math.sin(2 * math.pi * (45 * ph + 2 * (1 - math.exp(-30 * ph)))) * math.exp(-7 * ph)
    beat_i = int(b)
    sn = 0.0
    if beat_i % 2 == 1:
        sn = 0.35 * (rng.random() * 2 - 1) * math.exp(-14 * ph)
    hp = (t + beat / 2) % beat
    hat = 0.12 * (rng.random() * 2 - 1) * math.exp(-45 * hp)
    root, notes = chords[bar % 4]
    bass = 0.28 * math.sin(2 * math.pi * root * t) * (0.7 + 0.3 * math.sin(2 * math.pi * 2 * t))
    step = int((b * 2) % 6)
    f = notes[step % 3] * (2 if step > 2 else 1)
    sp = (b * 2) % 1 * beat / 2
    arp = 0.16 * math.sin(2 * math.pi * f * t) * math.exp(-5 * sp)
    pad = 0.07 * sum(math.sin(2 * math.pi * fq * t) for fq in notes)
    l = k + sn + hat + bass + arp + pad
    r = k + sn * 0.9 + hat * 1.1 + bass + arp * 0.8 + pad * 0.9
    L[i] = int(max(-1, min(1, l)) * 30000)
    R[i] = int(max(-1, min(1, r)) * 30000)
st = array.array("h", bytes(4 * n))
st[0::2] = L
st[1::2] = R
w = wave.open(out, "wb")
w.setnchannels(2)
w.setsampwidth(2)
w.setframerate(sr)
w.writeframes(st.tobytes())
w.close()
