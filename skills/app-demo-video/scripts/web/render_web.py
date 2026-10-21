#!/usr/bin/env python3
"""Turn a recorder.py recording into a finished 1920x1080 demo video.

  python3 render_web.py <video.json>

The browser page is drawn inside a window with a URL bar on a soft background. The cursor, click
ripples and key badges are drawn from the recorded events (never baked into the screencast), and a
spring camera zooms in and follows the cursor wherever the journey asked for it (cam events). Clicks
get a short synthesized tick on the sound track, mixed with optional music. Text (captions, cards, URL
bar) is rendered by ../render.swift so Thai, Arabic and CJK shape correctly. Frames are piped straight
into ffmpeg. Schema: references/web.md.
"""
import array, bisect, json, math, random, re, shutil, subprocess, sys, wave
from pathlib import Path
from PIL import Image, ImageDraw

SWIFT = Path(__file__).resolve().parent.parent / "render.swift"
W, H = 1920, 1080
S = 2                                    # the scene is composed at 2x so zoomed frames stay sharp
BAR = 40                                 # window title bar height (1x)
MAX_PAGE = (1500, 875)                   # page area limit (1x); leaves room for the caption below
RATE = 48000

DEFAULT_BRAND = {
    "kicker": "", "primary": "#1F6F66", "deep": "#13233A", "tint": "#E3F3F0", "muted": "#475467",
    "chrome": "#EEF0F4", "chrome_line": "#DDE1E8", "accent": "#5B3FD1",
    "background": ["#E7ECF5", "#F6F4FB"], "fonts": {},
}


def ease(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


class Geometry:
    """Where the window sits in the 1920x1080 scene, sized to the recorded viewport."""

    def __init__(self, vw, vh):
        self.vw, self.vh = vw, vh
        self.k = min(MAX_PAGE[0] / vw, MAX_PAGE[1] / vh)        # CSS px -> scene px
        pw, ph = vw * self.k, vh * self.k
        x0 = (W - pw) / 2
        self.win = (x0, 20, x0 + pw, 20 + BAR + ph)
        self.page = (x0, 20 + BAR, x0 + pw, 20 + BAR + ph)

    def to_scene(self, x, y):
        return self.page[0] + x * self.k, self.page[1] + y * self.k


# ------------------------------------------------------------------ recording
class Recording:
    def __init__(self, out, cfg):
        self.out = out
        self.frames = [json.loads(l) for l in open(out / "frames.jsonl")]
        if not self.frames:
            sys.exit("render: no frames recorded (did the journey call recorder.watch()?)")
        self.ts = [f["ts"] for f in self.frames]
        ev = json.load(open(out / "events.json"))
        by = lambda k: [e for e in ev if e["type"] == k]
        self.marks = {e["name"]: e["t"] for e in by("mark")}
        self.moves, self.clicks, self.keys, self.cams = by("move"), by("click"), by("keys"), by("cam")
        vw, vh = cfg.get("viewport") or (self.frames[0]["css_w"], self.frames[0]["css_h"])
        self.geo = Geometry(vw, vh)
        masks = [(re.compile(p), r) for p, r in cfg.get("mask_urls", [])]
        self.labels = {}
        for p in by("page"):
            label = p["label"]
            for rx, rep in masks:
                label = rx.sub(rep, label)
            self.labels.setdefault(p["page"], label)
        self.start_cursor = tuple(self.moves[0]["frm"]) if self.moves else (vw / 2, vh / 2)
        self.t_start = min(self.ts[0], ev[0]["t"])
        self.t_end = max(self.ts[-1], ev[-1]["t"])
        self._camera(cfg.get("camera", {}))

    def frame_at(self, t):
        i = max(bisect.bisect_right(self.ts, t) - 1, 0)   # the screencast only sends changes: hold the last one
        return self.frames[i]

    def cursor(self, t):
        x, y = self.start_cursor
        for m in self.moves:
            if m["t0"] > t:
                break
            u = ease((t - m["t0"]) / max(m["t1"] - m["t0"], 1e-3))
            x = m["frm"][0] + (m["to"][0] - m["frm"][0]) * u
            y = m["frm"][1] + (m["to"][1] - m["frm"][1]) * u
        return min(max(x, 4), self.geo.vw - 4), min(max(y, 4), self.geo.vh - 20)

    def _camera(self, c):
        """A critically damped spring camera simulated over the whole recording at 60 Hz."""
        self.cam_dt = 1 / 60
        w_pos, w_zoom = c.get("follow_stiffness", 3.2), c.get("zoom_stiffness", 2.6)   # rad/s: lower = lazier
        n = int((self.t_end - self.t_start) / self.cam_dt) + 2
        cx, cy, z = W / 2, H / 2, 1.0
        vx = vy = vz = 0.0
        self.cam, ci = [], 0
        mode, tz, at = "overview", 1.0, None
        for k in range(n):
            t = self.t_start + k * self.cam_dt
            while ci < len(self.cams) and self.cams[ci]["t"] <= t:
                e = self.cams[ci]
                mode, tz, at = e["mode"], e["z"], e.get("at")
                ci += 1
            if mode == "overview":
                tx, ty, tz_ = W / 2, H / 2, 1.0
            else:
                tx, ty = self.geo.to_scene(*(at if mode == "fixed" and at else self.cursor(t)))
                tz_ = tz
            vx += (w_pos ** 2 * (tx - cx) - 2 * w_pos * vx) * self.cam_dt
            vy += (w_pos ** 2 * (ty - cy) - 2 * w_pos * vy) * self.cam_dt
            vz += (w_zoom ** 2 * (tz_ - z) - 2 * w_zoom * vz) * self.cam_dt
            cx += vx * self.cam_dt; cy += vy * self.cam_dt; z += vz * self.cam_dt
            self.cam.append((cx, cy, max(z, 1.0)))

    def camera(self, t):
        k = min(max(int((t - self.t_start) / self.cam_dt), 0), len(self.cam) - 1)
        cx, cy, z = self.cam[k]
        win, m = self.geo.win, 16
        # keep the view inside the window (plus a small margin) so zooming never shows empty background
        lo_x, hi_x = win[0] - m + W / 2 / z, win[2] + m - W / 2 / z
        lo_y, hi_y = win[1] - m + H / 2 / z, win[3] + m - H / 2 / z
        cx = (lo_x + hi_x) / 2 if lo_x > hi_x else min(max(cx, lo_x), hi_x)
        cy = (lo_y + hi_y) / 2 if lo_y > hi_y else min(max(cy, lo_y), hi_y)
        if z <= 1.001:
            return W / 2, H / 2, 1.0
        u = min((z - 1) / 0.25, 1)    # blend toward the centred overview near z=1, so a push-in starts from the whole scene
        return W / 2 + (cx - W / 2) * u, H / 2 + (cy - H / 2) * u, z


# ------------------------------------------------------------------ stills (render.swift)
def build_stills(cfg, rec, b, work):
    f, g = b["fonts"], rec.geo
    labels = sorted(set(rec.labels.values()))
    scenes = []
    for i, label in enumerate(labels):                       # background + window chrome, one per URL label (2x)
        x0, y0, x1, y1 = (v * S for v in g.win)
        items = [
            {"type": "rect", "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "radius": 24, "color": "#FFFFFF", "shadow": True},
            {"type": "rect", "x": x0, "y": y0, "w": x1 - x0, "h": BAR * S + 30, "radius": 24, "color": b["chrome"]},
            {"type": "rect", "x": x0, "y": y0 + BAR * S, "w": x1 - x0, "h": 2, "radius": 0, "color": b["chrome_line"]},
        ]
        for j, col in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
            items.append({"type": "rect", "x": x0 + 36 + j * 40, "y": y0 + BAR * S / 2 - 12, "w": 24, "h": 24,
                          "radius": 12, "color": col})
        items.append({"type": "pill", "text": label, "font": f.get("regular"), "size": 26, "color": b["muted"],
                      "bg": "#FFFFFF", "cx": (x0 + x1) / 2, "cy": y0 + BAR * S / 2, "padX": 120, "padY": 10})
        scenes.append({"path": str(work / f"scene-{i}.png"), "width": W * S, "height": H * S,
                       "background": {"gradient": b["background"]}, "items": items})
    for i, seg in enumerate(cfg["segments"]):
        scenes.append({"path": str(work / f"cap-{i}.png"), "width": W, "height": 140, "items": [
            {"type": "pill", "text": seg["caption"], "font": f.get("semibold"), "size": 34, "color": "#FFFFFF",
             "bg": "#101828E8", "cx": W / 2, "cy": 70, "padX": 34, "padY": 16}]})
    for i, k in enumerate(rec.keys):
        scenes.append({"path": str(work / f"key-{i}.png"), "width": 360, "height": 120, "items": [
            {"type": "pill", "text": k["label"], "font": f.get("bold"), "size": 44, "color": "#FFFFFF",
             "bg": "#101828E0", "cx": 180, "cy": 60, "padX": 34, "padY": 14}]})

    def card(name, title, lines):
        items = [{"type": "text", "text": title, "font": f.get("bold"), "size": 104, "color": b["deep"], "cx": W / 2, "cy": 490}]
        if b.get("kicker"):
            items.append({"type": "pill", "text": b["kicker"], "font": f.get("semibold"), "size": 28, "color": b["primary"],
                          "bg": b["tint"], "cx": W / 2, "cy": 380, "padX": 26, "padY": 10})
        items += [{"type": "text", "text": t, "font": f.get("semibold" if j == 0 else "regular"), "size": 44 if j == 0 else 32,
                   "color": b["muted"], "cx": W / 2, "cy": 610 + j * 70} for j, t in enumerate(lines) if t]
        return {"path": str(work / f"{name}.png"), "width": W, "height": H,
                "background": {"gradient": b["background"]}, "items": items}

    intro, outro = cfg.get("intro", {}), cfg.get("outro", {})
    scenes.append(card("intro", intro.get("title", ""), [intro.get("tagline"), intro.get("note")]))
    scenes.append(card("outro", outro.get("title", ""), [outro.get("cta")]))
    for s in scenes:                                           # render.swift wants no null fonts
        for it in s["items"]:
            if it.get("font") is None:
                it.pop("font", None)
    spec = work / "stills.json"
    spec.write_text(json.dumps({"fonts": [], "scenes": scenes}, ensure_ascii=False))
    subprocess.run(["swift", str(SWIFT), str(spec)], check=True)
    return {label: Image.open(work / f"scene-{i}.png").convert("RGB") for i, label in enumerate(labels)}


# ------------------------------------------------------------------ compositing
ARROW = [(0, 0), (0, 17), (4.2, 13.2), (7, 19.5), (9.6, 18.4), (6.9, 12.3), (12.5, 12.3)]


def draw_cursor(d, x, y, s):
    pts = [(x + px * s * 1.25, y + py * s * 1.25) for px, py in ARROW]
    d.polygon([(px + 1.5, py + 2.5) for px, py in pts], fill=(0, 0, 0, 70))
    d.polygon(pts, fill=(17, 17, 17, 255), outline=(255, 255, 255, 255), width=max(2, int(2 * s)))


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class Compositor:
    def __init__(self, rec, scenes, work, accent, cursor=True):
        self.rec, self.scenes, self.cache, self.draw_cursor = rec, scenes, {}, cursor
        g = rec.geo
        pw, ph = (g.page[2] - g.page[0]) * S, (g.page[3] - g.page[1]) * S
        self.page_size = (int(pw), int(ph))
        self.mask = Image.new("L", self.page_size, 0)
        ImageDraw.Draw(self.mask).rounded_rectangle((0, -60, pw - 1, ph - 1), radius=24, fill=255)  # round the bottom corners only
        self.badges = [Image.open(work / f"key-{i}.png") for i in range(len(rec.keys))]
        self.accent = hex_rgb(accent)

    def scene_for(self, frame):
        name = frame["file"]
        if name not in self.cache:
            if len(self.cache) > 6:
                self.cache.pop(next(iter(self.cache)))
            base = self.scenes[self.rec.labels.get(frame["page"], next(iter(self.scenes)))].copy()
            shot = Image.open(self.rec.out / "frames" / name).convert("RGB").resize(self.page_size, Image.LANCZOS)
            g = self.rec.geo
            base.paste(shot, (int(g.page[0] * S), int(g.page[1] * S)), self.mask)
            self.cache[name] = base
        return self.cache[name]

    def frame(self, t):
        rec, g = self.rec, self.rec.geo
        scene = self.scene_for(rec.frame_at(t))
        cx, cy, z = rec.camera(t)
        hw, hh = W / 2 / z, H / 2 / z
        img = scene.resize((W, H), Image.BILINEAR, box=((cx - hw) * S, (cy - hh) * S, (cx + hw) * S, (cy + hh) * S))
        to_out = lambda sx, sy: ((sx - cx) * z + W / 2, (sy - cy) * z + H / 2)
        d = ImageDraw.Draw(img, "RGBA")
        r_, g_, b_ = self.accent
        for c in rec.clicks:                                   # ripple
            age = t - c["t"]
            if 0 <= age < 0.55:
                ox, oy = to_out(*g.to_scene(c["x"], c["y"]))
                r = (14 + 46 * ease(age / 0.55)) * z ** 0.5
                a = int(150 * (1 - age / 0.55))
                d.ellipse((ox - r, oy - r, ox + r, oy + r), fill=(r_, g_, b_, a // 3), outline=(r_, g_, b_, a), width=4)
        px, py = to_out(*g.to_scene(*rec.cursor(t)))
        press = any(0 <= t - c["t"] < 0.15 for c in rec.clicks)
        if self.draw_cursor:
            draw_cursor(d, px, py, 1.25 * z ** 0.6 * (0.85 if press else 1.0))
        for k, badge in zip(rec.keys, self.badges):           # key badge next to the cursor
            age = t - k["t"]
            if -0.1 <= age < 1.3:
                a = min(1.0, (age + 0.1) / 0.2, (1.3 - age) / 0.25)
                bb = badge.copy()
                bb.putalpha(bb.getchannel("A").point(lambda v: int(v * a)))
                img.paste(bb, (int(px + 24), int(py + 18)), bb)
        return img


# ------------------------------------------------------------------ sound
def tick():
    """A soft mouse click: two decaying partials plus a little noise, ~40 ms."""
    rnd = random.Random(7)
    n = int(RATE * 0.04)
    return [(0.55 * math.sin(2 * math.pi * 1900 * i / RATE) + 0.25 * math.sin(2 * math.pi * 3700 * i / RATE)
             + 0.2 * (rnd.random() * 2 - 1)) * math.exp(-i / RATE * 110) for i in range(n)]


def load_sound(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(RATE), "-"],
                         capture_output=True, check=True).stdout
    return [v / 32768 for v in array.array("h", raw)]


def write_sfx(path, total, hits, sample, volume):
    buf = [0.0] * (int(total * RATE) + 1)
    for t in hits:
        i0 = int(t * RATE)
        for j, v in enumerate(sample):
            if i0 + j < len(buf):
                buf[i0 + j] += v * volume
    pcm = array.array("h", (int(max(-1.0, min(1.0, v)) * 32767) for v in buf))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


# ------------------------------------------------------------------ edit
def main():
    cfg_path = Path(sys.argv[1] if len(sys.argv) > 1 else "video.json").resolve()
    cfg = json.load(open(cfg_path))
    base = cfg_path.parent
    out = base / cfg.get("out", "out")
    work = out / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    brand = {**DEFAULT_BRAND, **cfg.get("brand", {})}
    rec = Recording(out, cfg)
    segs = cfg["segments"]
    missing = {s[k][0] for s in segs for k in ("from", "to")} - rec.marks.keys()
    if missing:
        sys.exit(f"render: marks not in the last recording: {', '.join(sorted(missing))}")
    comp = Compositor(rec, build_stills(cfg, rec, brand, work), work, brand["accent"], cfg.get("draw_cursor", True))
    caps = [Image.open(work / f"cap-{i}.png") for i in range(len(segs))]
    intro, outro = (Image.open(work / f"{n}.png").convert("RGB") for n in ("intro", "outro"))

    fps, card, xf = cfg.get("fps", 30), cfg.get("card_seconds", 3.0), cfg.get("transition", 0.45)
    spans = []
    for s in segs:
        t0, t1 = rec.marks[s["from"][0]] + s["from"][1], rec.marks[s["to"][0]] + s["to"][1]
        if t1 <= t0:
            sys.exit(f"render: segment '{s['caption']}' ends before it starts")
        spans.append((t0, t1, s.get("speed", 1.0)))

    # Timeline: intro, segments, outro. A cut (next segment does not start where the previous ended) gets a
    # cross-fade; contiguous segments just swap captions.
    clips = [("card", intro, card)] + [("seg", i, (t1 - t0) / sp) for i, (t0, t1, sp) in enumerate(spans)] + \
            [("card", outro, card)]
    starts, t = [], 0.0
    for j, c in enumerate(clips):
        cut = j > 0 and not (c[0] == "seg" and clips[j - 1][0] == "seg" and
                             abs(spans[c[1]][0] - spans[clips[j - 1][1]][1]) < 0.05)
        if cut:
            t -= xf
        starts.append(t)
        t += c[2]
    total = t

    # click sound at each click's place on the output timeline
    snd = cfg.get("click_sound", True)
    hits = []
    if snd:
        for j, (kind, ref, dur) in enumerate(clips):
            if kind == "seg":
                t0, t1, sp = spans[ref]
                hits += [starts[j] + (c["t"] - t0) / sp for c in rec.clicks if t0 <= c["t"] < t1]
    sample = load_sound(base / snd) if isinstance(snd, str) else tick()
    sfx = work / "sfx.wav"
    write_sfx(sfx, total, hits, sample, cfg.get("click_volume", 0.35))

    def clip_frame(j, local):
        kind, ref, dur = clips[j]
        if kind == "card":
            return ref.copy()
        t0, t1, sp = spans[ref]
        img = comp.frame(t0 + min(max(local, 0), dur) * sp)
        a = min(1.0, max(local, 0) / 0.35, max(dur - local, 0) / 0.35)
        img.paste(caps[ref], (0, H - 150), caps[ref].getchannel("A").point(lambda v: int(v * a)))
        return img

    music = base / cfg.get("music", "assets/music.mp3")
    final = base / cfg.get("output_dir", "out") / f"{cfg.get('name', 'demo')}.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-i", str(sfx)]
    if music.exists():
        cmd += ["-stream_loop", "-1", "-i", str(music), "-filter_complex",
                f"[2:a]volume={cfg.get('music_volume', 0.18)},afade=t=in:d=1,afade=t=out:st={max(total - 2, 0):.2f}:d=2[m];"
                "[1:a][m]amix=inputs=2:normalize=0:duration=first[a]", "-map", "0:v", "-map", "[a]"]
    else:
        print(f"render: no music at {music}; sound track is click sounds only" if hits else
              f"render: no music at {music}; the video is silent")
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2",
            "-b:a", "160k", "-t", f"{total:.3f}", "-movflags", "+faststart", str(final)]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(round(total * fps))
    for k in range(n):
        t = k / fps
        live = [j for j, st in enumerate(starts) if st <= t < st + clips[j][2]][-2:]
        frames = [(j, clip_frame(j, t - starts[j])) for j in live]
        if len(frames) == 2:
            img = Image.blend(frames[0][1], frames[1][1], ease((t - starts[frames[1][0]]) / xf))
        else:
            img = frames[-1][1]
        ff.stdin.write(img.tobytes())
        if k % (fps * 5) == 0:
            print(f"render: {t:5.1f}/{total:.1f} s", flush=True)
    ff.stdin.close()
    if ff.wait():
        sys.exit("render: ffmpeg failed")
    print(f"render: {final}  {total:.1f} s, {len(hits)} click sounds")


if __name__ == "__main__":
    main()
