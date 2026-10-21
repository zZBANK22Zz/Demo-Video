#!/usr/bin/env python3
"""Turn a plain screen capture (desktop app, CLI, anything) into render_web.py input.

  python3 import_capture.py capture.mp4 --marks out/marks.txt --rec-mark rec_x --label "My App" \
      [--out out] [--crop W:H:X:Y] [--scale 2] [--fps 30]

capture.mp4 comes from e.g. `ffmpeg -f avfoundation -capture_cursor 1 -framerate 30 -i "<screen>:none"`,
and marks.txt from scripts/mark-server.py (`NAME UNIX_TIME` lines). `--rec-mark` is the mark posted when
the capture started, so frame times line up with the other marks. `--crop` cuts the app's window out of
the full screen (pixels). `--scale` = capture pixels per CSS pixel (2 on Retina).

Writes <out>/frames/*.jpg, frames.jsonl and events.json (marks + one page). The capture already shows
the real cursor, so set "draw_cursor": false in video.json. Camera moves: add
{"type": "cam", "t": ..., "mode": "fixed", "z": 1.5, "at": [x, y]} lines to events.json by hand.
"""
import argparse, json, shutil, subprocess
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("capture")
ap.add_argument("--marks", required=True)
ap.add_argument("--rec-mark", required=True)
ap.add_argument("--label", default="")
ap.add_argument("--out", default="out")
ap.add_argument("--crop")
ap.add_argument("--scale", type=float, default=2.0)
ap.add_argument("--fps", type=int, default=30)
a = ap.parse_args()

out = Path(a.out)
marks = {}
for line in open(a.marks):
    name, t = line.split()
    marks[name] = float(t)                               # repeated names keep the last, like edit.py
if a.rec_mark not in marks:
    raise SystemExit(f"import_capture: no '{a.rec_mark}' mark in {a.marks}")
t0 = marks[a.rec_mark]

frames = out / "frames"
shutil.rmtree(frames, ignore_errors=True)
frames.mkdir(parents=True)
vf = (f"crop={a.crop}," if a.crop else "") + f"fps={a.fps}"
subprocess.run(["ffmpeg", "-v", "error", "-i", a.capture, "-vf", vf, "-q:v", "3", str(frames / "%06d.jpg")], check=True)
files = sorted(frames.glob("*.jpg"))
if not files:
    raise SystemExit("import_capture: ffmpeg wrote no frames")
w, h = map(int, subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                                str(files[0])], capture_output=True, text=True, check=True).stdout.split(","))
with open(out / "frames.jsonl", "w") as f:
    for i, p in enumerate(files):
        f.write(json.dumps({"ts": t0 + i / a.fps, "file": p.name, "page": 1,
                            "css_w": w / a.scale, "css_h": h / a.scale}) + "\n")
events = [{"type": "page", "t": t0, "page": 1, "label": a.label}] + \
         [{"type": "mark", "t": t, "name": n} for n, t in sorted(marks.items(), key=lambda kv: kv[1])]
(out / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=1))
print(f"import_capture: {len(files)} frames, {len(marks)} marks -> {out}")
