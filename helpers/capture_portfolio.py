"""Capture the real synthetic workspace. Requires playwright and installed Chrome."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/assets/screenshots"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1200}, device_scale_factor=1)
    page.goto("http://127.0.0.1:8517", wait_until="networkidle")
    page.get_by_text("Client folders (IMAP)", exact=True).click()
    page.get_by_role("button", name="Load folders", exact=True).click()
    page.get_by_role("combobox", name="Client folders", exact=True).click()
    page.get_by_role("option", name="Clients/Northstar Imports", exact=False).click()
    page.keyboard.press("Escape")
    dates = page.get_by_test_id("stDateInput").locator("input")
    dates.nth(0).fill("2026-10-01")
    dates.nth(0).press("Enter")
    dates.nth(1).fill("2026-10-31")
    dates.nth(1).press("Enter")
    page.keyboard.press("Escape")
    page.get_by_role("heading", name="Period & scope", exact=True).click()
    page.get_by_test_id("stMain").evaluate("el => el.scrollTop = 0")
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT / "01-client-scope.png"))
    page.get_by_role("button", name="Open selected folders →", exact=True).click()
    page.get_by_role("heading", name="Reading pane").wait_for()
    page.get_by_role("combobox", name="Sender", exact=True).click()
    page.get_by_role("option", name="news@software.example", exact=False).click()
    page.get_by_role("button", name="Exclude sender", exact=True).click()
    page.get_by_role("combobox", name="Sender", exact=True).click()
    page.get_by_role("option", name="All senders", exact=False).click()
    page.get_by_role("combobox", name="Preview email", exact=True).click()
    page.get_by_role("option", name="Re: October records — review completed", exact=True).click()
    page.get_by_test_id("stMain").evaluate("el => el.scrollTop = 0")
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT / "02-email-review.png"))
    page.get_by_role("button", name="Use selected emails →", exact=True).click()
    page.get_by_text("On this computer", exact=True).click()
    page.get_by_role("button", name="Generate work record draft", exact=True).click()
    page.get_by_role("heading", name="Proposed work activities").wait_for()
    page.get_by_role("textbox", name="Reviewer name", exact=True).fill("Demo reviewer")
    page.get_by_text("I have checked the included activities against the email evidence", exact=True).click()
    page.set_viewport_size({"width": 1600, "height": 1400})
    page.get_by_role("heading", name="Client & work summary", exact=True).evaluate("el => { const main = document.querySelector('[data-testid=stMain]'); main.scrollTop += el.getBoundingClientRect().top - 80; }")
    page.wait_for_timeout(1200)
    assert page.get_by_test_id("stException").count() == 0
    assert page.get_by_role("checkbox", name="I have checked the included activities against the email evidence", exact=True).is_checked()
    page.screenshot(path=str(OUT / "03-draft-export.png"))
    with page.expect_download() as download:
        page.get_by_role("button", name="Download Word record", exact=True).click()
    assert download.value.suggested_filename.endswith(".docx")
    assert Path(download.value.path()).stat().st_size > 1000
    print("Captured three synthetic screenshots")
    browser.close()
