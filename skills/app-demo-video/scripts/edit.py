#!/usr/bin/env python3
"""Edits simulator/emulator recordings into finished demo videos.

Usage: edit.py <video.json>

Everything comes from the config (paths are relative to the config's folder):
  devices   1-3 recordings, each with the mark that says when it started
  segments  cuts between named marks (+ offsets), each with a step title/subtitle
  brand     colours, logo, fonts (any .ttf/.otf; system font if omitted)

Writes, next to the config:
  <name>.mp4            1080x1920 — one device at a time (the segment's focus)
  <name>-landscape.mp4  1920x1080 — all devices side by side, focus ringed, others dimmed
  <raw_name>.mp4        every raw recording side by side, uncut, aligned in time

Still layers are rendered by render.swift (macOS text engine: correct shaping for
Thai, Arabic, Indic, CJK — ffmpeg drawtext cannot do this). ffmpeg scales, cuts,
composites, cross-fades and muxes. See references/config.md for the schema.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PORTRAIT = (1080, 1920)
LANDSCAPE = (1920, 1080)

DEFAULT_BRAND = {
    "primary": "#0A7A4A", "deep": "#173F30", "tint": "#ECFDF3", "muted": "#475467",
    "ink": "#101828", "background": ["#E3F4EA", "#F7FBF8"],
    "logo": None, "fonts": {},
}


def run(cmd):
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"edit: command failed:\n{' '.join(cmd)}\n{res.stderr[-3000:]}")
    return res.stdout


def probe(path):
    data = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=width,height:format=duration", "-of", "json", path]))
    s = data["streams"][0]
    return s["width"], s["height"], float(data["format"]["duration"])


def even(n):
    return int(round(n / 2)) * 2


class Edit:
    def __init__(self, config_path):
        self.base = os.path.dirname(os.path.abspath(config_path))
        with open(config_path) as f:
            self.cfg = json.load(f)
        c = self.cfg
        self.brand = {**DEFAULT_BRAND, **c.get("brand", {})}
        self.fonts = {k: self.path(v) for k, v in self.brand.get("fonts", {}).items()}
        self.bold = self.fonts.get("bold", "")
        self.semi = self.fonts.get("semibold", self.bold)
        self.regular = self.fonts.get("regular", self.semi)
        self.logo = self.path(self.brand["logo"]) if self.brand.get("logo") else None
        self.fps = int(c.get("fps", 60))
        self.card_seconds = float(c.get("card_seconds", 3.0))
        self.fade = float(c.get("transition", 0.5))
        self.work = self.path(c.get("work_dir", "out/work"))
        self.devices = c["devices"]
        if not 1 <= len(self.devices) <= 3:
            sys.exit("edit: 1 to 3 devices are supported")
        self.keys = [d["key"] for d in self.devices]
        self.dev = {d["key"]: d for d in self.devices}
        self.marks = self.load_marks(self.path(c.get("marks", "out/marks.txt")))

    def path(self, p):
        return p if os.path.isabs(p) else os.path.join(self.base, p)

    @staticmethod
    def load_marks(path):
        marks = {}
        with open(path) as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2:
                    marks[parts[0]] = float(parts[1])  # a repeated name keeps its last moment
        return marks

    # ---- layout ---------------------------------------------------------------

    def layouts(self):
        port, land = {}, {}
        n = len(self.devices)
        ph_l = {1: 820, 2: 770, 3: 700}[n]
        gap = {1: 0, 2: 200, 3: 120}[n]
        widths = {k: even(ph_l * self.aspect[k]) for k in self.keys}
        total = sum(widths.values()) + gap * (n - 1)
        x = even((1920 - total) / 2)
        for k in self.keys:
            ph = 1530
            pw = even(ph * self.aspect[k])
            port[k] = (even((1080 - pw) / 2), 350, pw, ph)
            land[k] = (x, 92, widths[k], ph_l)
            x += widths[k] + gap
        return port, land

    def bezel(self, x, y, w, h, b):
        return {"type": "rect", "x": x - b, "y": y - b, "w": w + 2 * b, "h": h + 2 * b,
                "radius": w * 0.13 + b, "color": "#0B0F14", "shadow": True}

    def scenes(self, port, land):
        B = self.brand
        W, H = PORTRAIT
        out = []
        for k in self.keys:  # portrait background per device: its bezel fits its own size
            out.append({"path": f"{self.work}/bg-portrait-{k}.png", "width": W, "height": H,
                        "background": {"gradient": B["background"]}, "items": [self.bezel(*port[k], 16)]})
        W, H = LANDSCAPE
        items = []
        for k in self.keys:
            x, y, w, h = land[k]
            items.append(self.bezel(x, y, w, h, 10))
            if len(self.keys) > 1:
                items.append({"type": "text", "text": self.dev[k]["label"], "font": self.semi, "size": 32,
                              "color": self.dev[k].get("color", B["primary"]), "cx": x + w / 2, "cy": 50})
        out.append({"path": f"{self.work}/bg-landscape.png", "width": W, "height": H,
                    "background": {"gradient": B["background"]}, "items": items})
        for orient, lay in (("portrait", port), ("landscape", land)):
            for k in self.keys:
                _, _, w, h = lay[k]
                out.append({"path": f"{self.work}/mask-{orient}-{k}.png", "width": w, "height": h,
                            "background": {"solid": "#000000"},
                            "items": [{"type": "rect", "x": 0, "y": 0, "w": w, "h": h, "radius": w * 0.13,
                                       "color": "#FFFFFF"}]})
            out.append(self.card("intro", orient))
            out.append(self.card("outro", orient))
            n = len(self.cfg["segments"])
            for i, seg in enumerate(self.cfg["segments"], 1):
                out.append(self.step_overlay(orient, i, n, seg, lay))
        return out

    def step_overlay(self, orient, i, n, seg, lay):
        B = self.brand
        W, H = PORTRAIT if orient == "portrait" else LANDSCAPE
        k = seg["focus"]
        color = self.dev[k].get("color", B["primary"])
        title = seg.get("title", "")
        sub = seg.get("subtitle", "")
        items = []
        if orient == "portrait":
            chip = f"{self.dev[k]['label']}   {i}/{n}" if len(self.keys) > 1 else f"{i}/{n}"
            items += [
                {"type": "pill", "text": chip, "font": self.semi, "size": 30, "color": "#FFFFFF", "bg": color,
                 "cx": W / 2, "cy": 74, "padX": 28, "padY": 8},
                {"type": "rect", "x": 50, "y": 128, "w": W - 100, "h": 180, "radius": 40, "color": "#FFFFFF",
                 "shadow": True},
                {"type": "text", "text": title, "font": self.bold, "size": 52, "color": B["deep"],
                 "cx": W / 2, "cy": 190 if sub else 218},
            ]
            if sub:
                items.append({"type": "text", "text": sub, "font": self.regular, "size": 33, "color": B["muted"],
                              "cx": W / 2, "cy": 258})
        else:
            if len(self.keys) > 1:
                x, y, w, h = lay[k]
                r = 20
                items.append({"type": "rect", "x": x - r, "y": y - r, "w": w + 2 * r, "h": h + 2 * r,
                              "radius": w * 0.13 + r, "color": color, "stroke": 7})
            items += [
                {"type": "rect", "x": 330, "y": 902, "w": W - 660, "h": 150, "radius": 36, "color": "#FFFFFF",
                 "shadow": True},
                {"type": "text", "text": f"{i}.  {title}", "font": self.bold, "size": 44, "color": B["deep"],
                 "cx": W / 2, "cy": 948 if sub else 977},
            ]
            if sub:
                items.append({"type": "text", "text": sub, "font": self.regular, "size": 30, "color": B["muted"],
                              "cx": W / 2, "cy": 1008})
        return {"path": f"{self.work}/step-{orient}-{i}.png", "width": W, "height": H, "items": items}

    def card(self, kind, orient):
        B, c = self.brand, self.cfg.get(kind, {})
        W, H = PORTRAIT if orient == "portrait" else LANDSCAPE
        s = 1.0 if orient == "portrait" else 0.8
        cy = H / 2
        items = []
        logo = (300 if kind == "intro" else 210) * s
        if self.logo:
            items.append({"type": "image", "path": self.logo, "x": W / 2 - logo / 2,
                          "y": cy - logo - (70 if kind == "intro" else 90) * s, "w": logo, "h": logo,
                          "radius": logo * 0.225})
        if kind == "intro":
            items.append({"type": "text", "text": c.get("title", ""), "font": self.bold, "size": 124 * s,
                          "color": "#FFFFFF", "cx": W / 2, "cy": cy + 50 * s})
            if c.get("tagline"):
                items.append({"type": "text", "text": c["tagline"], "font": self.regular, "size": 50 * s,
                              "color": B["tint"], "cx": W / 2, "cy": cy + 165 * s})
            if c.get("note"):
                items.append({"type": "text", "text": c["note"], "font": self.regular, "size": 34 * s,
                              "color": B["tint"], "cx": W / 2, "cy": cy + 245 * s})
        else:
            items.append({"type": "text", "text": c.get("title", ""), "font": self.bold, "size": 84 * s,
                          "color": "#FFFFFF", "cx": W / 2, "cy": cy + 20 * s})
            if c.get("cta"):
                items.append({"type": "pill", "text": c["cta"], "font": self.semi, "size": 46 * s,
                              "color": B["deep"], "bg": "#FFFFFF", "cx": W / 2, "cy": cy + 150 * s,
                              "padX": 44 * s, "padY": 16 * s})
        return {"path": f"{self.work}/{kind}-{orient}.png", "width": W, "height": H,
                "background": {"gradient": [B["deep"], B["primary"]]}, "items": items}

    # ---- clips ----------------------------------------------------------------

    def enc(self):
        return ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
                "-r", str(self.fps), "-an"]

    def card_clip(self, png, out):
        run(["ffmpeg", "-y", "-loop", "1", "-t", f"{self.card_seconds}", "-i", png,
             "-vf", f"fps={self.fps},format=yuv420p", *self.enc(), out])

    def segment_clip(self, orient, idx, seg, t0, dur, lay, out):
        speed = float(seg.get("speed", 1.0))
        keys = [seg["focus"]] if orient == "portrait" else self.keys
        bg = f"{self.work}/bg-portrait-{seg['focus']}.png" if orient == "portrait" else f"{self.work}/bg-landscape.png"
        args = ["ffmpeg", "-y", "-loop", "1", "-i", bg, "-loop", "1", "-i", f"{self.work}/step-{orient}-{idx}.png"]
        for k in keys:
            args += ["-loop", "1", "-i", f"{self.work}/mask-{orient}-{k}.png"]
        for k in keys:
            start = t0 - self.rec_start[k]
            args += ["-ss", f"{max(0.0, start):.3f}", "-t", f"{dur:.3f}", "-i", self.raw[k]]
        out_dur = dur / speed
        f, last, n = [], "[0:v]", len(keys)
        for j, k in enumerate(keys):
            x, y, w, h = lay[k]
            dim = "" if k == seg["focus"] or orient == "portrait" else ",colorchannelmixer=aa=0.4"
            f.append(f"[{2 + n + j}:v]setpts=(PTS-STARTPTS)/{speed},fps={self.fps},scale={w}:{h}:flags=lanczos,"
                     f"format=rgba[s{j}];[{2 + j}:v]scale={w}:{h},format=gray[m{j}];[s{j}][m{j}]alphamerge{dim}[p{j}]")
            f.append(f"{last}[p{j}]overlay={x}:{y}:eof_action=repeat[o{j}]")
            last = f"[o{j}]"
        f.append(f"{last}[1:v]overlay=0:0,format=yuv420p,trim=duration={out_dur:.3f}[v]")
        run([*args, "-filter_complex", ";".join(f), "-map", "[v]", "-t", f"{out_dur:.3f}", *self.enc(), out])
        return out_dur

    def join(self, clips, durs, out):
        if self.fade <= 0:
            listing = out + ".txt"
            with open(listing, "w") as fh:
                fh.writelines(f"file '{c}'\n" for c in clips)
            run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", out])
            return sum(durs)
        args = ["ffmpeg", "-y"]
        for c in clips:
            args += ["-i", c]
        f, last, t = [], "[0:v]", durs[0]
        for k in range(1, len(clips)):
            off = t - self.fade
            f.append(f"{last}[{k}:v]xfade=transition=fade:duration={self.fade}:offset={off:.3f}[x{k}]")
            last, t = f"[x{k}]", off + durs[k]
        f.append(f"{last}fade=t=in:st=0:d=0.5,fade=t=out:st={t - 0.7:.3f}:d=0.7,format=yuv420p[v]")
        run([*args, "-filter_complex", ";".join(f), "-map", "[v]", *self.enc(), out])
        return t

    def mux(self, video, duration, out):
        music = self.path(self.cfg.get("music", "assets/music.mp3"))
        if os.path.exists(music):
            ain = ["-stream_loop", "-1", "-i", music]
            af = f"volume={self.cfg.get('music_volume', 0.18)},afade=t=in:st=0:d=1.5,afade=t=out:st={max(0, duration - 2):.2f}:d=2"
        else:
            ain = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
            af = "anull"
        run(["ffmpeg", "-y", "-i", video, *ain, "-filter:a", af, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "160k", "-t", f"{duration:.3f}", "-movflags", "+faststart", out])

    def raw_side_by_side(self, out):
        later = max(self.rec_start.values())
        ins, f = [], []
        for j, k in enumerate(self.keys):
            ins += ["-ss", f"{later - self.rec_start[k]:.3f}", "-i", self.raw[k]]
            f.append(f"[{j}:v]fps={self.fps},scale=-2:1280[r{j}]")
        stack = "".join(f"[r{j}]" for j in range(len(self.keys)))
        f.append(f"{stack}hstack=inputs={len(self.keys)}:shortest=1,format=yuv420p[v]" if len(self.keys) > 1
                 else "[r0]format=yuv420p[v]")
        run(["ffmpeg", "-y", *ins, "-filter_complex", ";".join(f), "-map", "[v]", *self.enc(),
             "-movflags", "+faststart", out])

    def main(self):
        c = self.cfg
        self.raw = {k: self.path(self.dev[k]["raw"]) for k in self.keys}
        self.rec_start = {}
        for k in self.keys:
            if not os.path.exists(self.raw[k]):
                sys.exit(f"edit: missing recording {self.raw[k]}")
            rm = self.dev[k]["rec_mark"]
            if rm not in self.marks:
                sys.exit(f"edit: recording-start mark {rm!r} not in marks file")
            self.rec_start[k] = self.marks[rm]
        missing = {m for s in c["segments"] for m in (s["from"][0], s["to"][0])} - self.marks.keys()
        if missing:
            sys.exit(f"edit: marks not in the last run: {', '.join(sorted(missing))}")
        if os.path.isdir(self.work):
            shutil.rmtree(self.work)
        os.makedirs(self.work)

        self.aspect = {}
        for k in self.keys:
            w, h, _ = probe(self.raw[k])
            self.aspect[k] = w / h
        port, land = self.layouts()
        spec = os.path.join(self.work, "scenes.json")
        with open(spec, "w") as f:
            json.dump({"fonts": [p for p in self.fonts.values() if p], "scenes": self.scenes(port, land)}, f,
                      ensure_ascii=False)
        run(["swift", os.path.join(HERE, "render.swift"), spec])

        name, raw_name = c.get("name", "demo-final"), c.get("raw_name", "demo-raw")
        for orient, lay in (("portrait", port), ("landscape", land)):
            clips, durs = [f"{self.work}/{orient}-00-intro.mp4"], [self.card_seconds]
            self.card_clip(f"{self.work}/intro-{orient}.png", clips[0])
            for i, seg in enumerate(c["segments"], 1):
                t0 = self.marks[seg["from"][0]] + seg["from"][1]
                t1 = self.marks[seg["to"][0]] + seg["to"][1]
                if t1 <= t0:
                    sys.exit(f"edit: segment {i} ({seg.get('title')}) ends before it starts")
                clip = f"{self.work}/{orient}-{i:02d}.mp4"
                durs.append(self.segment_clip(orient, i, seg, t0, t1 - t0, lay, clip))
                clips.append(clip)
            clips.append(f"{self.work}/{orient}-99-outro.mp4")
            durs.append(self.card_seconds)
            self.card_clip(f"{self.work}/outro-{orient}.png", clips[-1])
            silent = f"{self.work}/{orient}-video.mp4"
            total = self.join(clips, durs, silent)
            final = os.path.join(self.base, f"{name}.mp4" if orient == "portrait" else f"{name}-landscape.mp4")
            self.mux(silent, total, final)
            print(f"edit: {final}  {total:.1f} s")
        raw = os.path.join(self.base, f"{raw_name}.mp4")
        self.raw_side_by_side(raw)
        print(f"edit: {raw}  (uncut)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    Edit(sys.argv[1]).main()
