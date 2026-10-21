# Lessons from production runs

Every item here cost real debugging time: first on a two-simulator Expo app demo, then on a web
demo (a dashboard with a help-desk side panel in an iframe, a support agent's page, and the
notification e-mail in Gmail). Check the symptom column first when something goes wrong.

## Mobile

| Symptom | Cause | Fix |
|---|---|---|
| A wait that should pass times out; the other device's app looks stuck (e.g. an offer never appears though the server sent it) | Maestro runners from an earlier, interrupted run still attached (`xcodebuild test-without-building ... maestro-driver-ios`, java `maestro.cli.AppKt`). Two runners on one device. `pkill -f "maestro test"` does NOT match them. | `pkill -f maestro.cli.AppKt; pkill -f maestro-driver-ios` before and after every run (the template does). |
| Location set with `simctl location set` / `adb emu geo fix` is ignored | A Maestro `setLocation` from an earlier run is still overriding the device location. | Set start positions inside the flows with Maestro `setLocation`, never with simctl/adb. |
| `travel` takes minutes for a short leg | Maestro `travel` ignores `speed` on iOS. | Generate `setLocation` steps (`scripts/route_legs.py`). |
| Car moves absurdly fast; map/route lines look wrong; distance left jumps around | Bare `setLocation` steps run ~0.3 s apart; 20–70 m per step ≈ 240 km/h. Under recording load each step instead takes 1–3 s — pace is not constant. | Even spacing (~15 m) + a pause per step. Judge pace from the marks, not assumptions. |
| On arrival the map shows a stray route / the car disappears / distance goes UP | Teleporting mid-route: the app reroutes from an arbitrary point (one-way streets → detours), or falls back to an overview. Also check the app itself: arrival states may drop the live position. | Drive every metre of each leg (choose a SHORT demo route, ~1 km), land on the booking's exact coordinate with `--end`. If the app is wrong at stops, that is an app bug — fix or report it. |
| Tap "succeeds" but the screen does not change (only while recording) | Recording + two Maestro sessions slow the app; the tap lands mid-render (e.g. a CTA re-labelling). | `retry` + optional tap + wait for the NEXT screen (see templates/flow-example.yaml). |
| Taps land on the keyboard ("Jungceylony") | Keyboard stays up over lists after picking a search result. | `hideKeyboard` after the pick. |
| Yellow "Open debugger to view warnings." bar in the video | React Native dev-build LogBox toast. | `flows/lib/dismiss-dev-warning.yaml` (taps the ×, not the bar — the bar opens the debugger). Run it after each screen where it appeared; tune the point if the layout differs. |
| `"Button"` text not found though visible | Label includes icon text: `", Go online"`. Maestro matches the WHOLE label (regex). | Use `".*Go online"`; read labels via the failure's `screen-hierarchy/*.json`. |
| A ride/job is offered before the flow started | Leftover records from aborted runs still dispatching. | The prepare step must clear ALL leftovers (list endpoints, not just "active"). |
| `maestro record` | One device only; without `--local` it uploads the recording to Maestro's cloud. | Record with `xcrun simctl io <udid> recordVideo` / scrcpy while `maestro test` runs. |
| Captions in Thai/Arabic/Indic render with misplaced marks or not at all | Homebrew ffmpeg has no `drawtext`; drawtext without HarfBuzz mis-shapes complex scripts. | Render text as PNGs with `scripts/render.swift` (CoreText), overlay with ffmpeg. |
| ffmpeg `tile` contact sheet writes nothing | `tile=CxR` only emits when full. | Use `xstack` with an exact input count, or extract frames individually. |
| Tool can't write to the scratchpad / `/tmp` | Sandboxed process. | Write QA frames under `demo/out/qa/`. |
| A Python edit made git show the whole file changed | Read/write in text mode converted CRLF → LF. | Open with `newline=''` and preserve the file's line endings. |
| zsh: `no matches found: dir/*` aborted a command chain — and the rest still ran | zsh nomatch. | `setopt nonomatch`, `rm -f` with explicit names, or `find -delete`. Never assume a failed glob stopped the script; check for duplicate runs (`pgrep -fl make-video`). |
| Video too long after a re-record | Steps take longer under recording load; offsets from a dry run no longer fit. | Cut windows around marks (`p_prices -2 → +6.5`) instead of spanning two distant marks. Re-check durations after every recording. |

## Web

| Symptom | Cause | Fix |
|---|---|---|
| The video holds one frame for seconds, then jumps | The CDP screencast only sends a frame when the page changes. That's expected; render_web.py holds the last frame. If it also stutters during motion, the screencast frames weren't acked | Keep `recorder.py`'s ack; don't do heavy work in the frame handler |
| Cursor drawn in one place, hover/tooltip shown in another | The real mouse wasn't moved to the drawn cursor after a page switch | `watch()` moves it; call `watch()` on every page or tab switch |
| Captions say "Thai" but boxes/tofu appear in the *page* | Web fonts not loaded when recording starts | `watch()` waits for `document.fonts.ready`; for late-loading fonts wait for a visible text element too |
| A click lands on the wrong part of a row (an attachment chip, an icon) | `bounding_box()` centre of a wide row isn't the text | Target the inner text element (e.g. the subject span), not the row |
| Smooth scroll doesn't move a side panel or iframe | `window.scrollTo` scrolls the outer page | `scrollIntoView` on the element (recorder does) scrolls its own container |
| `evaluate` on a `frame_locator` fails | `FrameLocator` can't evaluate | Get the `Frame`: `next(f for f in page.frames if f.url.startswith(url))` |
| Pasting a screenshot needs the OS clipboard | Headless Chromium has no clipboard access | Dispatch a synthetic `ClipboardEvent('paste')` with a `DataTransfer` holding the file, plus `r.keys("⌘ V")` |
| Google refuses the sign-in ("browser may not be secure") | Automated Chromium | Have the user sign in once in plain Chrome with a dedicated `--user-data-dir`, quit it, then record with `launch_persistent_context(channel="chrome")` on that profile |
| Persistent Chrome profile opens signed out | Playwright's `--use-mock-keychain` can't decrypt the profile's cookies | `ignore_default_args=["--use-mock-keychain"]` |
| The second run's e-mail shows a collapsed body in Gmail | Gmail threads messages with the same subject | Keep earlier demo data so each run gets a new id/subject, or vary the subject |
| The notification e-mail isn't in the inbox | Test sender lands in Spam | Search `in:anywhere "<id>" after:<epoch>` and retry for a few seconds |
| A secret link or token shows in the URL bar | The URL-bar label is the real URL | `mask_urls` in video.json, or pass a clean label to `watch()` |
| The demo created records in the real database / sent real mail | Recorded against the dev stack | Separate port + data folder + dry-run side effects (templates/web/make-video.sh) |
| Video has no sound | `music` file missing (the renderer prints a warning) and `click_sound` false or no clicks in the cut | Add a licensed track at `assets/music.mp3`; keep `click_sound: true` |
| Zoom feels seasick | Camera changed mid-glide, or zoom > 1.7, or a zoom-out/in per field | One `cam()` per step, set before moving; 1.45–1.6; stay zoomed in across nearby clicks |

## QA before handing over

- Probe: `ffprobe` codec h264/aac, sizes 1080x1920 & 1920x1080, fps, duration; `moov` before `mdat` (faststart).
- Sound: `ffmpeg -i out.mp4 -af volumedetect -vn -f null -`. A mean around -91 dB means silent. Say so if music was expected.
- Web: 3–4 frames from zoomed steps. The cursor tip must sit on the control it clicks, and the ripple must be centred on it.
- One frame from the middle of each step in a grid (`xstack`) — does each frame match its caption?
- For any map/navigation step: 3-4 frames across the step, cropped to the map. The distance chip must
  count down, the line must start at the car, the car must sit on the pin at arrival.
- Look for dev chrome (warning bars, debug overlays) and real-data leaks.
