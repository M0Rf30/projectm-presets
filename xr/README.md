# xr/ – stereoscopic presets

Presets in this folder are written for `lactea-xr` (lactea's OpenXR host, tested target: Meta Quest 3). The image is not a screen but an equirectangular dome around the viewer, and the preset has to raymarch a real 3D scene so that the two eyes see different pictures. They still run as plain mono images in projectM or desktop lactea.

## Stereo contract

`lactea-xr` renders every frame twice with two identical engines (same seed, audio and clock) and appends one last line to the preset's `per_frame` code that sets

| var | meaning |
|---|---|
| `q32` | eye: `-1` left, `+1` right, `0` mono (any non-XR player) |
| `q31` | horizontal arc covered by the image, radians (`0` → default 220° = 3.839724) |
| `q30` | vertical half-angle, radians (`0` → `0.5 * arc * texsize.y / texsize.x`, square pixels) |

Because that line runs after the preset's own code, **read `q30`–`q32` only in the shaders** (never in `per_frame` / per-vertex code) and never write them; use `q1`…`q29` for your own data.

Pixel `uv` (u right, v down) maps to longitude `th = (uv.x - 0.5) * arc` and latitude `ph = (0.5 - uv.y) * 2 * halfV`; the view direction is `d = (cos ph sin th, sin ph, cos ph cos th)` and the omnidirectional-stereo ray origin is `ro = q32 * 0.032 * (cos th, 0, -sin th)` (64 mm IPD). Units are metres: depth reads strongly between 0.6 and 15 m and flat beyond ~30 m.

Comfort rules: no camera roll, no world rotation, no fast or accelerating camera motion (constant drift ≤ 0.3 m/s at most), no full-field flashes; beat accents are emissive pulses.

## Presets

* `M0Rf30 - Orbital Garden.milk` – you float (0.2 m/s drift) in an infinite lattice of glass orbs and crystals with orbiting moons, three beaded rings orbit at 2–5 m, and a field of glowing motes gives near parallax. The scene is raymarched in the warp shader (so the blur chain bloom the composite adds comes from it); the composite only blurs, tone maps and grades.

## Viewing

* Quest 3: run `lactea-xr` with the preset.
* Anything else (mono): `lactea --preset "xr/M0Rf30 - Orbital Garden.milk" --compat milkdrop3`. You see the whole 220° × ±55° dome as one equirectangular panorama.
* Quick stereo check without a headset: append `per_frame_N=q32 = -1; q31 = 3.839724; q30 = 0.959931;` (and the same with `q32 = 1`) to two copies, render the same frame of both and merge them as a red-cyan anaglyph (left image in the red channel). Near objects must sit further right in the left image than in the right one.
