"""Drive a browser journey with Playwright and record it for render_web.py.

Import it from the project's demo/record.py (see templates/web/record.py):

    SKILL = Path(os.environ.get("APP_DEMO_SKILL", Path.home() / ".claude/skills/app-demo-video"))
    sys.path.insert(0, str(SKILL / "scripts/web"))
    from recorder import Recorder

Writes to <out>/: frames/NNNNNN.jpg (screencast frames at 2x), frames.jsonl (one line per frame:
timestamp, file, page id, CSS size) and events.json (cursor moves, clicks, key badges, camera
instructions, marks, page switches). Everything shares one clock (unix seconds), so the editor cuts on
marks exactly as the mobile pipeline does.

The real mouse jumps; the *drawn* cursor glides. move() logs the glide (eased, 0.45-1.1 s by distance)
and waits for it, then moves the real mouse, so what the viewer sees and what the page gets stay in step.
"""
import asyncio, base64, json, time
from pathlib import Path


class Recorder:
    def __init__(self, out, viewport=(1440, 840), cursor=None):
        self.out = Path(out)
        self.view = {"width": viewport[0], "height": viewport[1]}
        self.events, self.n = [], 0
        self.cur = cursor or (viewport[0] * 0.68, viewport[1] * 0.74)
        self.page = self.cdp = None
        (self.out / "frames").mkdir(parents=True, exist_ok=True)
        self.index = open(self.out / "frames.jsonl", "w")

    def log(self, **e):
        e.setdefault("t", time.time())
        self.events.append(e)

    # ------------------------------------------------------------ capture
    async def watch(self, page, label):
        """Record `page` from now on (stops the previous page's screencast). `label` is the URL-bar text."""
        await page.evaluate("document.fonts.ready")
        await page.mouse.move(*self.cur)            # hover states must match where the drawn cursor is
        if self.cdp:
            await self.cdp.send("Page.stopScreencast")
        self.page, self.cdp = page, await page.context.new_cdp_session(page)
        pid, cdp = id(page), self.cdp

        def on_frame(p):
            self.n += 1
            name = f"{self.n:06d}.jpg"
            (self.out / "frames" / name).write_bytes(base64.b64decode(p["data"]))
            m = p["metadata"]
            self.index.write(json.dumps({"ts": m["timestamp"], "file": name, "page": pid,
                                         "css_w": m["deviceWidth"], "css_h": m["deviceHeight"]}) + "\n")
            asyncio.ensure_future(cdp.send("Page.screencastFrameAck", {"sessionId": p["sessionId"]}))

        cdp.on("Page.screencastFrame", on_frame)
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92,
                                                "maxWidth": self.view["width"] * 2, "maxHeight": self.view["height"] * 2})
        self.log(type="page", page=pid, label=label)

    # ------------------------------------------------------------ editing hints
    def mark(self, name):
        self.log(type="mark", name=name)
        print(f"mark {name}", flush=True)

    def cam(self, mode, z=1.0, at=None):
        """overview: whole window · follow: zoom z, centred on the cursor · fixed: zoom z on CSS point `at`."""
        self.log(type="cam", mode=mode, z=z, at=at)

    def keys(self, label):
        """Show a key badge (e.g. "⌘ V") next to the cursor, for actions done by script, not by mouse."""
        self.log(type="keys", label=label)

    # ------------------------------------------------------------ actions
    async def move(self, x, y, dur=None):
        dx, dy = x - self.cur[0], y - self.cur[1]
        dur = dur if dur is not None else min(1.1, max(0.45, (dx * dx + dy * dy) ** 0.5 / 900))
        now = time.time()
        self.log(type="move", t0=now, t1=now + dur, frm=self.cur, to=(x, y))
        await asyncio.sleep(dur)
        await self.page.mouse.move(x, y)
        self.cur = (x, y)

    async def spot(self, loc, scroll=True):
        """Wait for an element, smooth-scroll it to the middle of its own scroller, return its centre."""
        await loc.wait_for(state="visible", timeout=20000)
        if scroll:
            await loc.evaluate("el => el.scrollIntoView({behavior: 'smooth', block: 'center'})")
            await asyncio.sleep(0.7)
        b = await loc.bounding_box()
        return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2

    async def click(self, loc, settle=0.35, scroll=True):
        x, y = await self.spot(loc, scroll)
        await self.move(x, y)
        await asyncio.sleep(0.12)                    # a beat on target before pressing reads as deliberate
        self.log(type="click", x=x, y=y)
        await self.page.mouse.click(x, y)
        await asyncio.sleep(settle)

    async def type(self, loc, text, delay=0.045):
        await self.click(loc, settle=0.2)
        await loc.press_sequentially(text, delay=delay * 1000)

    async def hover(self, loc, hold=0.8, scroll=False):
        """Point at something the caption talks about. The cursor is the viewer's eye: use it."""
        x, y = await self.spot(loc, scroll)
        await self.move(x, y)
        await asyncio.sleep(hold)

    async def pause(self, s):
        await asyncio.sleep(s)

    async def stop(self):
        if self.cdp:
            await self.cdp.send("Page.stopScreencast")

    def close(self):
        self.index.close()
        (self.out / "events.json").write_text(json.dumps(self.events, ensure_ascii=False, indent=1))
