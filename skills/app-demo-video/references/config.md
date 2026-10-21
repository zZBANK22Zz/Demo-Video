# video.json — edit config for scripts/edit.py

Paths are relative to the config file. Template: `templates/video.json`. This is the mobile schema;
the web/screen-capture schema (`render_web.py`: captions, camera, click sounds, URL masking) is in
references/web.md. The pacing guide below applies to both.

| Key | Default | Meaning |
|---|---|---|
| `name` | `demo-final` | Outputs `<name>.mp4` (1080x1920) and `<name>-landscape.mp4` (1920x1080) next to the config |
| `raw_name` | `demo-raw` | Uncut, time-aligned side-by-side of all raw recordings |
| `fps` | 60 | Output frame rate. 60 keeps moving maps smooth |
| `card_seconds` | 3.0 | Intro/outro length |
| `transition` | 0.5 | Cross-fade between steps (0 = hard cuts, faster encode) |
| `marks` | `out/marks.txt` | Lines `NAME UNIX_TIME`, written by mark-server.py; repeated names keep the last |
| `work_dir` | `out/work` | Intermediate PNGs/clips (wiped each run) |
| `music` | `assets/music.mp3` | Mixed in if the file exists, else a silent AAC track |
| `music_volume` | 0.18 | |
| `brand.primary/deep/tint/muted` | green palette | Card gradient (deep→primary), titles (deep), subtitles (muted) |
| `brand.background` | light green | Gradient behind the phones |
| `brand.logo` | none | Square app icon; corners rounded like an iOS icon |
| `brand.fonts.bold/semibold/regular` | system | `.ttf`/`.otf` paths or PostScript names. Use the app's own font (often in `node_modules/@expo-google-fonts/...`). System font falls back per glyph, so any script renders |

## devices (1–3)

```json
{ "key": "p", "label": "Passenger app", "color": "#0A7A4A", "raw": "out/p-raw.mp4", "rec_mark": "rec_p" }
```
- `key`: short id used by segments (`focus`) and by marks naming
- `label`: chip text in portrait, heading above the phone in landscape
- `color`: chip colour and landscape focus ring
- `rec_mark`: the mark written when this device's recording started (make-video.sh writes `rec_<key>`)

## segments

```json
{ "focus": "d", "from": ["d_nav_pickup", 0.5], "to": ["d_nav_pickup", 8.5], "speed": 1.0,
  "title": "Navigate to pickup", "subtitle": "Map turns with the car, time and distance left" }
```
- Cut window = `marks[from[0]] + from[1]` → `marks[to[0]] + to[1]`, applied to every device's recording
  (they share one clock), so a step can show device A at a moment device B caused.
- Prefer windows around ONE mark (`X -2 → X +6.5`) for steps whose surroundings vary in length;
  spanning two marks inherits every slow tap in between.
- `speed` > 1 fast-forwards. Keep ≤ 1.25 for "easy to follow" videos; trim waiting instead.
- `title` + `subtitle`: one short title, one plain sentence of what is happening and why it matters.
  Numbering (`3/14`) and the device chip are added automatically.

## Pacing guide (what viewers found easy to follow)

- 3 s intro with a one-line "what you are about to watch" note; 3 s outro with a CTA pill.
- 4–10 s per step, 12–16 steps → 80–110 s. Short social cut: fewer steps, not faster steps.
- Show the cause on one device and the effect on the other as consecutive steps
  (driver taps "arrived" → passenger sees "driver has arrived").
