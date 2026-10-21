"""Drive the Ember & Sage demo journey in Chromium and record it for render_web.py.

  python3 record.py --url http://localhost:3099

Journey: Home → Menu (category tabs) → About (team) → Reservations (fill the form) → Contact (FAQ).
One block per caption: mark → camera → actions → wait for the real next state.
"""
import argparse, asyncio, os, sys
from pathlib import Path
from playwright.async_api import async_playwright, expect

SKILL = Path(os.environ.get("APP_DEMO_SKILL", Path(__file__).resolve().parents[3] / "skills/app-demo-video"))
sys.path.insert(0, str(SKILL / "scripts/web"))
from recorder import Recorder  # noqa: E402

HERE = Path(__file__).resolve().parent
VIEW = (1440, 840)
HOST = "emberandsage.example"   # URL-bar label: a clean domain instead of localhost


async def open_page(r, page, nav_name, heading, path):
    """Click a top-nav link, pull back to overview and wait until the new page is fully loaded."""
    await r.click(page.get_by_role("navigation", name="Main").get_by_role("link", name=nav_name, exact=True))
    r.cam("overview")
    await expect(page.get_by_role("heading", level=1, name=heading)).to_be_visible()
    await page.wait_for_load_state("networkidle")
    await r.watch(page, f"{HOST}/{path}")


async def main(url):
    r = Recorder(HERE / "out", VIEW)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(viewport={"width": VIEW[0], "height": VIEW[1]}, device_scale_factor=2,
                                        locale="en-US", color_scheme="light")
        page = await ctx.new_page()
        await page.goto(url + "/index.html")
        await expect(page.get_by_role("heading", level=1, name="Fire, flavor & the joy of the table.")).to_be_visible()
        await page.wait_for_load_state("networkidle")   # hero photo loaded before the first frame
        await r.watch(page, HOST)
        await r.pause(0.5)

        # 1 · home hero
        r.cam("overview"); r.mark("s_home")
        await r.pause(1.2)
        await r.hover(page.get_by_role("heading", level=1), 1.0)
        await r.hover(page.get_by_role("link", name="Reserve a Table"), 1.0)

        # 2 · scroll through the home page: signature dishes
        r.mark("s_dishes")
        await r.hover(page.get_by_role("heading", name="Dishes our guests come back for"), 1.0, scroll=True)
        r.cam("follow", 1.45)
        await r.hover(page.get_by_role("heading", name="Ember Ribeye"), 1.0)
        await r.hover(page.get_by_role("heading", name="Hearth Flatbread"), 1.0)
        r.cam("overview")
        await r.hover(page.get_by_role("heading", name="What people are saying"), 1.4, scroll=True)

        # 3 · menu page
        r.mark("s_menu")
        await open_page(r, page, "Menu", "Our Menu", "menu.html")
        await r.pause(1.4)

        # 4 · jump between categories with the tabs
        r.mark("s_tabs")
        tabs = page.get_by_role("navigation", name="Menu categories")
        await r.click(tabs.get_by_role("link", name="Starters"), settle=1.2)
        r.cam("follow", 1.45)
        await r.hover(page.get_by_role("heading", name="Grilled Tiger Prawns"), 1.2)
        r.cam("overview")
        await r.click(tabs.get_by_role("link", name="Mains"), settle=1.2)
        await expect(page.locator("#mains")).to_be_in_viewport()
        await r.hover(page.get_by_role("heading", name="Ember Ribeye 300g"), 1.2)
        await r.click(tabs.get_by_role("link", name="Desserts"), settle=1.2)
        await expect(page.locator("#desserts")).to_be_in_viewport()
        await r.hover(page.get_by_role("heading", name="Burnt Basque Cheesecake"), 1.4)

        # 5 · about page: story and team
        r.mark("s_about")
        await open_page(r, page, "About", "Honest food, cooked over fire", "about.html")
        await r.pause(1.2)
        await r.hover(page.get_by_role("heading", name="The people behind the fire"), 1.0, scroll=True)
        r.cam("follow", 1.45)
        await r.hover(page.get_by_role("heading", name="Mali Srisuk"), 1.0)
        await r.hover(page.get_by_role("heading", name="Nina Laurent"), 1.0)
        r.cam("overview")
        await r.pause(0.6)

        # 6 · reservations: pick guests, time and seating
        r.mark("s_book")
        await open_page(r, page, "Book a Table", "Book your table", "reservations.html")
        await r.pause(1.2)
        await r.hover(page.get_by_role("heading", name="Reservation details"), 0.6, scroll=True)
        r.cam("follow", 1.5)
        guests = page.get_by_label("Guests *")
        await r.click(guests, settle=0.3)
        await guests.select_option("4 guests")
        await r.pause(0.5)
        await r.click(page.get_by_text("7:30 PM", exact=True), settle=0.5)
        await expect(page.get_by_role("radio", name="7:30 PM")).to_be_checked()
        await r.click(page.get_by_text("Terrace", exact=True), settle=0.6)

        # 7 · reservations: contact details and occasion
        r.mark("s_details")
        await r.type(page.get_by_label("Full name *"), "Somchai Jaidee")
        await r.type(page.get_by_label("Phone *"), "+66 81 234 5678", delay=0.04)
        await r.type(page.get_by_label("Email *"), "somchai@example.com", delay=0.04)
        await r.click(page.get_by_text("Anniversary"), settle=0.4)
        await r.type(page.get_by_label("Special requests"), "Window seat if possible, please.", delay=0.035)
        await r.hover(page.get_by_role("button", name="Confirm Reservation"), 1.4, scroll=True)
        r.cam("overview")
        await r.pause(1.0)

        # 8 · contact page and FAQ
        r.mark("s_contact")
        await open_page(r, page, "Contact", "Get in touch", "contact.html")
        await r.pause(1.2)
        faq = page.get_by_text("Do you cater to dietary restrictions?")
        await r.hover(page.get_by_role("heading", name="Common questions"), 0.8, scroll=True)
        r.cam("follow", 1.45)
        await r.click(faq, settle=0.6)
        await expect(page.get_by_text("Our menu marks vegetarian")).to_be_visible()
        await r.pause(1.6)
        r.cam("overview")
        await r.pause(2.0)
        r.mark("end")

        await r.stop()
        await browser.close()
    r.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:3099")
    asyncio.run(main(ap.parse_args().url))
