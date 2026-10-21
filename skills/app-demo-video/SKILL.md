---
name: app-demo-video
description: Produce a polished, regenerable demo video of any app — mobile (React Native / Expo / native, recorded from iOS simulators or Android emulators with Maestro), web (any browser app, driven by Playwright with a smooth drawn cursor, click ripples, click sounds and a camera that zooms in and follows the cursor), or anything else (desktop, CLI) from a screen capture. Cuts on named moments into captioned videos with intro/outro cards, cross-fades, music and captions in any language (Thai, Arabic, CJK render correctly). Handles multi-device and multi-page journeys (passenger + driver, requester + support agent, a notification e-mail) on one synchronized timeline. Use this whenever the user wants a demo/promo/walkthrough/tutorial/app-store/LinkedIn/YouTube video of their app or website, wants to record a user flow, asks to "make a video of the app" or "show how to use X", wants to regenerate or fix an existing demo video, or mentions Maestro or Playwright recordings, even if they don't say "skill" or name the tools.
---

# App demo video

Turn a user journey into a calm, captioned demo video that can be regenerated with one command
after UI changes.

**How it works, for every project type:** a script drives the app while it is recorded and logs
named moments ("marks", e.g. `s_home`, `d_offer`) on the same clock as the recording. The editor
cuts at those exact moments instead of guessed timestamps, so a step can show one screen reacting
to something another screen just did. Text is rendered as PNGs with macOS CoreText (correct
shaping for every script), then composited with ffmpeg.

## Pick the path

| Project | Driver | Recorder | Editor | Read |
|---|---|---|---|---|
| Mobile (iOS / Android) | Maestro flows | `simctl recordVideo` / `scrcpy` | `scripts/edit.py`: portrait + landscape, phone bezels | this file, `references/config.md`, `references/android.md` |
| Web (any browser UI: sites, dashboards, embedded widgets, iframes) | Playwright (`templates/web/record.py`) | CDP screencast (`scripts/web/recorder.py`) | `scripts/web/render_web.py`: landscape, browser window, drawn cursor, follow-zoom, click sounds | `references/web.md` |
| Desktop app, CLI, anything else | your script / AppleScript, marks via `scripts/mark-server.py` | `ffmpeg -f avfoundation` screen capture | `scripts/web/import_capture.py` → `render_web.py` | "Other projects" below + `references/web.md` |

Ask the user when the project type or the story is unclear. Never assume a simulator setup for a
website, or a browser for a native app.

Bundled. **Scripts** are generic: use them as they are (fix bugs in them, don't fork per project).
**Templates** are starting points: copy them into the project and adapt freely, structure included.
- Shared: `scripts/render.swift` (PNG cards/captions), `scripts/mark-server.py` (records marks over HTTP)
- Mobile: `scripts/edit.py`, `scripts/route_legs.py` (route → paced `setLocation` subflow),
  `templates/make-video.sh`, `templates/flows/lib/*`, `templates/flow-example.yaml`, `templates/video.json`
- Web / other: `scripts/web/{recorder.py,render_web.py,import_capture.py}`, `templates/web/{record.py,make-video.sh,video.json}`
- `references/lessons.md`: symptom → cause → fix. **Read it before debugging anything.**

**Paths.** `scripts/…`, `templates/…` and `references/…` are relative to this skill's base directory,
which may be a personal skills folder, a project's `.claude/skills/`, or a plugin cache. When you copy
a `make-video.sh` template, set its `SKILL=` default to that base directory. The script exports it as
`APP_DEMO_SKILL`, which `record.py` reads.

## Ground rules

- **Seeded/test data only.** Never real users, phone numbers, e-mails or payment data in a published
  video. Web: run an isolated demo stack (own port, own data folder, side effects in dry-run).
- **Don't change app behaviour for the video.** The only routine app edit is adding a few
  `testID`s / `data-testid`s to elements with no stable text or role. List each one for the user.
  If the recording exposes a real app bug, tell the user and fix it only with their agreement.
- **Ask before installing** anything (Maestro: `curl -Ls "https://get.maestro.mobile.dev" | bash`;
  ffmpeg: `brew install ffmpeg`; Android: `brew install scrcpy`; web: `pip install playwright pillow`
  + `python3 -m playwright install chromium`).
- **Nothing leaves the machine.** Don't use `maestro record` without `--local` (it uploads to
  Maestro's cloud and captures one device only). No cloud recorders or upload-to-edit services.
- **Real accounts only with consent.** If a scene needs a real service (an inbox showing the
  notification e-mail), the user picks the account and signs in by hand in a dedicated browser
  profile. Never handle their password.
- **Captions and cards are user-facing copy:** short, plain, in the app's language.
- **Music must be the user's or licensed.** Ask for a file; don't download tracks.
- Put everything in `demo/` in the project, plus `demo/.gitignore` with `out/`, `flows/generated/`
  and any browser profile folder.

## Workflow

### 1. Understand the journey and the app
Read the routes/navigation and the screens on the path. Note which elements have unique visible
text, roles or accessibility labels (Maestro matches those as full regexes; Playwright: prefer
`get_by_role` / `get_by_label` / `get_by_text`) and which need a test id. Settle the story with
the user if it's ambiguous: which screens or devices, start signed in or show sign-in, which side
effects to show (e-mail, notification, a second user's screen), target length. Default to
"start signed in" and 80–110 s (pacing guide in references/config.md).

### 2. Check tools
Mobile: `maestro` (Java 17+), `xcrun simctl` and/or `adb` (+ `scrcpy`). Web: `python3 -c "import
playwright, PIL"` and Playwright's Chromium. All: `ffmpeg`/`ffprobe`, `python3`, `swift` (Xcode CLT).
Report what's missing with the install command and wait for approval.

### 3. Set up `demo/` and write the journey

**Mobile.** Copy `templates/make-video.sh`, `templates/video.json`, `templates/flows/lib/` into
`demo/`. Set `appId` in `flows/lib/*.yaml`, fill in APP_ID and the DEVICES list (5th column =
per-device app id when devices run different apps; list the device that *waits* first). Write one
flow per device using `templates/flow-example.yaml`:
- set start locations with Maestro `setLocation` inside the flow;
- `extendedWaitUntil` for every state change, `pause.yaml` only for viewer pauses (1.5–3 s per screen);
- type in chunks with short pauses; `hideKeyboard` before tapping under a keyboard;
- wrap state-changing taps in `retry` + optional tap + wait for the next screen;
- `mark` every moment the edit might cut on; dismiss dev warning bars;
- cross-device steps are long waits for the state the other device causes.

**Web.** Copy `templates/web/*` into `demo/`. Fill in CONFIGURE in `make-video.sh` (port, build,
start command, env pointing the app at throwaway data). Write `record.py` as one block per caption:
`mark` → camera → actions → wait for the real next state (`expect(...)`, never a bare sleep).
Navigation, camera, click and sound rules are in references/web.md. The short version: overview
whenever the screen changes, follow-zoom 1.45–1.6 while acting, hover what the caption names before
clicking it, and end on overview.

**Other projects.** Run `python3 scripts/mark-server.py out/marks.txt 8787 &`. Start the capture
(`ffmpeg -f avfoundation -capture_cursor 1 -framerate 30 -i "<screen>:none" out/capture.mp4`) and
POST `rec_x` as it starts (`curl -d rec_x localhost:8787/mark`). Drive the app by hand or by script,
POSTing a mark at each step. Then run `python3 scripts/web/import_capture.py out/capture.mp4 --marks
out/marks.txt --rec-mark rec_x --label "App" --crop W:H:X:Y` and render with `render_web.py` and
`"draw_cursor": false` (the real cursor is in the capture). There's no automatic follow-zoom
because clicks aren't logged; add `fixed` cam events by hand where a close-up helps. If the app
also has a web UI, prefer the web path: it gets the drawn cursor, ripples and click sounds.

**Data in a known state.** If the app needs it (accounts online, no leftover orders, wallet funded),
write `demo/scripts/prepare.py` against the app's API with test credentials, and clear ALL
leftovers, not just the "active" one. Web stacks with a data folder: delete it before each run.

**Signed-in start.** API logins don't sign the *app* in. Mobile: sign each device in once (by hand
or a one-off `login-<key>.yaml`); dev/preview builds keep the session across relaunches. Web: log in
inside `record.py` before `watch()`, or load a saved `storage_state`. Have each flow first assert
its home screen, so a lost session fails fast instead of mid-recording.

**Build.** Prefer a release/preview/production build: no dev chrome, no dev-server dependency.
With a mobile dev build, keep Metro running and use the dismiss-dev-warning subflow.

**Movement (maps, navigation, delivery; mobile).**
- Get the route from the **same source the app uses** (usually its backend's route endpoint) so the
  drive matches the line the app draws. Fall back to Google Directions (needs a key) or OSRM only if
  the app has none, and expect the app to reroute if they differ.
- `python3 scripts/route_legs.py route.json flows/generated/leg-x.yaml --app-id <id> --end <lat,lng> [--mark-every 10 --mark-prefix x]`.
  `--end` = the booking's exact coordinate; the last stretch to it is driven, not jumped.
- Pick short routes (~1 km per leg) and drive all of each; never teleport. The edit shows ~8 s of
  each leg, cut around marks (`--mark-every` gives anchors mid-leg).

### 4. Dry run until clean
Mobile: `demo/make-video.sh --dry-run`; on failure open the newest `~/.maestro/tests/<run>/`
(`screenshots/`, `screen-hierarchy/*.json`). Web: `demo/make-video.sh --record`; on failure the
Playwright error names the locator, and the last files in `out/frames/` show the screen.
Check references/lessons.md for the symptom. Expect 2–4 iterations.

### 5. Record and edit
`demo/make-video.sh` records and edits. Each run replaces the previous recording in `demo/out/`;
tell the user if older takes matter. Write `video.json` segments from the actual marks (mobile:
`out/marks.txt`; web: the `mark` events in `out/events.json`). Print them relative to the first
mark to see the timeline. Re-edit without re-recording: `--edit-only`. On the web path the camera,
cursor, ripples and sound are all edit-time settings.
For decks and landscape-first outputs (YouTube, slides), design the steps for the landscape cut.

### 6. QA: look, don't assume
Follow "QA before handing over" in references/lessons.md: probe formats, a mid-step frame grid
for caption/content match, zoomed frames to check the cursor sits on what it clicks, and the audio
level (silent when music was expected?). Map steps need 3–4 cropped frames across each step. Fix,
then re-edit or re-record. Re-check durations after every recording: steps run slower while recording.

### 7. Report
Output paths, durations, resolutions/fps, and what the sound track holds (music, clicks, or
nothing); every app file touched (test ids, any approved fix); anything installed; deviations from
the request and why; what to check manually (placeholder intro/outro copy, real content visible,
missing music); how to regenerate (`demo/make-video.sh`, `--edit-only`, where captions live).
