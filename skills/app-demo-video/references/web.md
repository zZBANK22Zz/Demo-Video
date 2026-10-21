# Web apps: recording, camera, clicks and sound

The web path replaces Maestro + simulators with Playwright + a CDP screencast. The cursor, click
ripples, key badges, zoom and click sounds are added in the edit from logged events, so they can be
retuned with `--edit-only` without recording again.

```
record.py (your journey) ──uses──► scripts/web/recorder.py
   │  writes out/frames/*.jpg, frames.jsonl, events.json   (one clock: unix seconds)
   ▼
scripts/web/render_web.py video.json ──► out/<name>.mp4   (1920x1080, h264 + aac)
```

Requirements: `python3` with `playwright` (+ `python3 -m playwright install chromium`) and `Pillow`,
`ffmpeg`, `swift`. Ask before installing any of them.

## Recorder API (scripts/web/recorder.py)

| Call | What it does |
|---|---|
| `Recorder(out, viewport=(1440, 840), cursor=None)` | Starts the frame index. `cursor` = where the drawn cursor starts (CSS px) |
| `await r.watch(page, label)` | Record this page from now on. Waits for fonts, moves the real mouse to the drawn cursor, stops the previous page's screencast. `label` is the URL-bar text |
| `r.mark(name)` | A moment the edit can cut on. Start each step with one |
| `r.cam(mode, z, at)` | `overview` · `follow` (zoom `z`, centred on the cursor) · `fixed` (zoom `z` on CSS point `at`) |
| `await r.hover(loc, hold)` | Glide to an element and rest on it. `scroll=True` to bring it into view first |
| `await r.click(loc, settle)` | Smooth-scroll into view → glide → 0.12 s beat → click (logged for ripple + sound) → settle |
| `await r.type(loc, text, delay)` | Click the field, then type one key at a time (default 45 ms per key) |
| `r.keys("⌘ V")` | Key badge next to the cursor, for shortcuts the script performs another way |
| `await r.pause(s)` / `await r.stop()` / `r.close()` | Viewer pause / stop the screencast / write events.json |

## Navigation and camera rules

These made the Help Desk demo easy to follow; start from them.

- **Overview when the screen changes.** After a click opens a new page, panel or modal, call
  `r.cam("overview")` *before* waiting for it, so viewers see where they are. Hold 1.2–2 s.
- **Follow while acting.** Switch to `r.cam("follow", 1.45–1.6)` for typing, picking options and
  pressing buttons. Above 1.7 the page feels cramped; below 1.4 the zoom isn't worth the motion.
- **Point before acting.** `hover` what the caption names (0.8–1.6 s) before clicking it. The
  cursor is where the viewer looks.
- **One camera move at a time.** Don't change the camera in the middle of a glide. Set it, then move.
- **Stay zoomed in across nearby clicks.** Several fields on one screen = one `follow`, not a
  zoom-out-and-in per field.
- **End on overview** with a 2 s hold so the outro cross-fade starts from the whole window.
- Camera feel (in `video.json` → `camera`): `follow_stiffness` 3.2 and `zoom_stiffness` 2.6 rad/s are
  a critically damped spring (no overshoot). Lower = lazier. The view is clamped to the window, so a
  zoom never shows the background, and near z=1 it blends to the centre so a push-in starts from the
  whole scene.

## Clicks, typing, scrolling

- The real mouse jumps; the drawn cursor glides on an eased path lasting 0.45–1.1 s, set by distance.
  `move()` waits for the glide and then moves the real mouse, so hover states line up.
- Ripple: 0.55 s ring in `brand.accent`; the cursor shrinks to 85% for 0.15 s on press.
- Type real-looking text at 35–45 ms per key. Long text: lower the delay or speed up that segment
  (`speed` ≤ 1.4).
- Scrolling: `click`/`hover(scroll=True)` call `scrollIntoView({behavior:'smooth', block:'center'})`
  and wait 0.7 s. That scrolls the element's own container (works inside iframes and side panels).
- Iframes: drive the UI with `page.frame_locator(sel)`; for `evaluate` you need the frame object
  (`next(f for f in page.frames if f.url.startswith(...))`).
- Paste a file: build a `DataTransfer` in the page and dispatch a `ClipboardEvent('paste')`, with
  `r.keys("⌘ V")` so viewers see a shortcut. Grab the image first with `locator.screenshot()`.
- Several pages or tabs: call `watch()` on each switch. Each URL label gets its own window chrome.

## Sound

- **Click sounds** (`click_sound`): `true` = a synthesized soft tick (about 40 ms, no asset needed),
  a path = your own sound file, `false` = off. `click_volume` default 0.35. Every logged click in the
  cut gets one, placed by the segment's speed.
- **Music** (`music`, `music_volume` 0.18): looped, 1 s fade in, 2 s fade out, mixed under the clicks.
  If the file is missing, the renderer prints a warning and the video has clicks only, or no sound
  at all. Put that in the report so the user can add a track.
- Only use music the user owns or that is licensed for this use. Ask; don't download tracks.

## video.json (web)

Same idea as the mobile schema (references/config.md), with these differences:

| Key | Default | Meaning |
|---|---|---|
| `segments[].caption` | required | One line, bottom-centre pill (the web cut has no title/subtitle pair) |
| `segments[].from/to/speed` | | Same as mobile: `[mark, offset]`, speed ≤ 1.4 |
| `viewport` | from frames | CSS size of the recording; the window is sized to fit it |
| `mask_urls` | `[]` | `[[regex, replacement]]` applied to URL-bar labels (hide tokens and secret links) |
| `click_sound` / `click_volume` | `true` / 0.35 | See Sound |
| `camera.follow_stiffness` / `camera.zoom_stiffness` | 3.2 / 2.6 | Spring stiffness |
| `brand.accent` | `#5B3FD1` | Ripple colour |
| `brand.chrome` / `brand.chrome_line` | greys | Window title bar |
| `out` / `output_dir` | `out` / `out` | Recording folder / where `<name>.mp4` goes |

Output is landscape only (1920x1080). For a portrait cut, record a phone-sized viewport (e.g. 430x932)
and ask before building it: it needs a different window layout.

## Isolated demo stack

Run the app for the recording on its own port and its own data folder, with mail, payments and
webhooks in dry-run mode (see templates/web/make-video.sh). Real records must never appear in the
video, and demo records must never land in real data. If the demo needs a real external service
(for example a mailbox to show a notification), use a test account the user chose and signs in to
by hand (see lessons.md).
