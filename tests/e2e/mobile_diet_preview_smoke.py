from pathlib import Path

from playwright.sync_api import expect, sync_playwright


# Why: prove the H5 preview shell can switch to the diet home and reveal the redesigned landmarks; Scope: mobile H5 diet preview smoke coverage only; Verify: `uv run --with playwright python tests/e2e/mobile_diet_preview_smoke.py`.
EDGE_PATH = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
TARGET_URL = "http://localhost:5173"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=str(EDGE_PATH))
        page = browser.new_page(viewport={"width": 430, "height": 932})
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_load_state("networkidle", timeout=30_000)

        page.locator("[data-preview-tab='diet']").click()
        expect(page.locator("body")).to_contain_text("今日摄入")
        expect(page.locator("body")).to_contain_text("今日饮食记录")
        expect(page.locator("body")).to_contain_text("AI 推荐晚餐")
        expect(page.locator("body")).to_contain_text("练了么")
        expect(page.locator("body")).to_contain_text("吃了么")
        expect(page.locator("body")).to_contain_text("瘦了么")

        browser.close()


if __name__ == "__main__":
    main()
