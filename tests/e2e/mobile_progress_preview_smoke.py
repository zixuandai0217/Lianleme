from pathlib import Path

from playwright.sync_api import expect, sync_playwright


# Why: lock the redesigned progress preview landmarks before the page rebuild lands so the H5 tab switch and key copy are both covered; Scope: mobile H5 progress preview smoke coverage only; Verify: `uv run --with playwright python tests/e2e/mobile_progress_preview_smoke.py`.
EDGE_PATH = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
TARGET_URL = "http://localhost:5173"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=str(EDGE_PATH))
        page = browser.new_page(viewport={"width": 430, "height": 932})
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_load_state("networkidle", timeout=30_000)

        page.locator("[data-preview-tab='progress']").click()
        expect(page.locator("body")).to_contain_text("今日体重")
        expect(page.locator("body")).to_contain_text("体重趋势图")
        expect(page.locator("body")).to_contain_text("智能建议")
        expect(page.locator("body")).to_contain_text("练了么")
        expect(page.locator("body")).to_contain_text("吃了么")
        expect(page.locator("body")).to_contain_text("瘦了么")
        page.get_by_text("个人中心").click()
        expect(page.locator("body")).to_contain_text("我的资料")

        browser.close()


if __name__ == "__main__":
    main()
