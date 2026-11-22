"""Render the HTML guides in docs/ to PDF with the system Chrome (Playwright, no browser download needed).

    .venv/bin/python scripts/render_guides.py            # both guides
    .venv/bin/python scripts/render_guides.py pitch      # one of: app, pitch
"""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

DOCS = Path(__file__).resolve().parents[1] / "docs"
GUIDES = {"app": ("VFMonitor_App_Guide", "VFMonitor app guide"),
          "pitch": ("VFMonitor_Pitch_Guide", "VFMonitor pitch guide")}


async def render(stem: str, footer: str) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        page = await browser.new_page()
        await page.goto((DOCS / f"{stem}.html").as_uri(), wait_until="load")
        await page.wait_for_timeout(1500)
        await page.pdf(path=str(DOCS / f"{stem}.pdf"), format="A4", print_background=True,
                       margin={"top": "16mm", "bottom": "16mm", "left": "15mm", "right": "15mm"},
                       display_header_footer=True, header_template="<div></div>",
                       footer_template=f"<div style='font-size:8px;color:#777;width:100%;text-align:center;"
                                       f"font-family:sans-serif'>{footer} · page <span class='pageNumber'></span> / "
                                       f"<span class='totalPages'></span></div>")
        await browser.close()
    print("wrote", DOCS / f"{stem}.pdf")


if __name__ == "__main__":
    for key in (sys.argv[1:] or list(GUIDES)):
        asyncio.run(render(*GUIDES[key]))
