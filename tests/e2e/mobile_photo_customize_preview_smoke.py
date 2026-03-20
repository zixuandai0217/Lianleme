from pathlib import Path

from playwright.sync_api import expect, sync_playwright


# Why: lock the workout-to-photo-customize preview flow before the new camera page lands so the entry and key camera UI copy are covered together; Scope: mobile H5 photo-customize preview smoke only; Verify: `uv run --with playwright python tests/e2e/mobile_photo_customize_preview_smoke.py`.
EDGE_PATH = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
TARGET_URL = "http://localhost:5173"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=str(EDGE_PATH))
        page = browser.new_page(viewport={"width": 430, "height": 932})
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_load_state("networkidle", timeout=30_000)

        page.get_by_text("拍照定制").first.click()
        expect(page.locator("body")).to_contain_text("AI 智能拍照定制")
        expect(page.locator("body")).to_contain_text("选择拍摄模式")
        expect(page.locator("body")).to_contain_text("点击拍照")
        expect(page.locator("body")).to_contain_text("体态分析")
        expect(page.locator("body")).to_contain_text("器械识别")

        browser.close()


if __name__ == "__main__":
    main()
