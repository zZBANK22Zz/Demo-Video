"""Drive the demo journey in Chromium and record it for render_web.py.  Copy to <project>/demo/record.py.

  python3 record.py --url http://localhost:3000

Structure: one block per caption-sized step. Each block starts with a mark (the edit cuts on it), sets
the camera, then acts. Wait for the app's real state (expect / wait_for) after every action that
changes the screen, and never sleep instead of waiting. See references/web.md for the camera,
navigation and pacing rules.
"""
import argparse, asyncio, os, re, sys
from pathlib import Path
from playwright.async_api import async_playwright, expect

# make-video.sh exports APP_DEMO_SKILL; the fallback is the default personal-skills install
SKILL = Path(os.environ.get("APP_DEMO_SKILL", Path.home() / ".claude/skills/app-demo-video"))
sys.path.insert(0, str(SKILL / "scripts/web"))
from recorder import Recorder  # noqa: E402

HERE = Path(__file__).resolve().parent
VIEW = (1440, 840)            # CSS viewport; 1440x840 fills the 1920x1080 frame with room for captions


async def main(url):
    r = Recorder(HERE / "out", VIEW)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(viewport={"width": VIEW[0], "height": VIEW[1]}, device_scale_factor=2,
                                        locale="en-US", color_scheme="light")
        page = await ctx.new_page()
        await page.goto(url)
        await expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()   # fail fast on a wrong start
        await r.watch(page, url.split("//")[-1])      # URL-bar text; mask secrets with mask_urls in video.json
        await r.pause(0.5)

        # 1 · establish: the whole window, then point at what the caption names
        r.cam("overview"); r.mark("s_home")
        await r.pause(1.0)
        await r.hover(page.get_by_text("Revenue"), 0.8)

        # 2 · zoom in to act (follow the cursor), click into a new screen
        r.cam("follow", 1.5); r.mark("s_open")
        await r.click(page.get_by_role("button", name="New report"))
        r.cam("overview")                              # a whole new screen: pull back so viewers see where they are
        await expect(page.get_by_role("heading", name="New report")).to_be_visible()
        await r.pause(1.4)

        # 3 · fill a form while following the cursor
        r.cam("follow", 1.6); r.mark("s_fill")
        await r.type(page.get_by_label("Title"), "Weekly sales")
        await r.click(page.get_by_role("radio", name="PDF"))
        await r.click(page.get_by_role("button", name="Create"))
        await expect(page.get_by_text(re.compile("^Report created"))).to_be_visible(timeout=20000)

        # 4 · show the result, then pull back and hold for the outro
        r.mark("s_done")
        await r.hover(page.get_by_text(re.compile("^Report created")), 1.6)
        r.cam("overview")
        await r.pause(2.0)
        r.mark("end")

        # Other patterns:
        #   iframe UI:     f = page.frame_locator("#widget"); await r.click(f.get_by_role(...))
        #   second tab:    p2 = await ctx.new_page(); await p2.goto(...); await r.watch(p2, "label")
        #   back to tab 1: await page.bring_to_front(); await r.watch(page, "label")
        #   scripted key:  r.keys("⌘ V"); then dispatch the event in the page (see references/web.md)
        await r.stop()
        await browser.close()
    r.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:3000")
    asyncio.run(main(ap.parse_args().url))
