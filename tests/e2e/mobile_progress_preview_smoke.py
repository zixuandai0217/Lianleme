from pathlib import Path

from playwright.sync_api import expect, sync_playwright


# keep the progress landing smoke focused on authenticated page content instead of the auth gate; H5 progress smoke only; verify with `uv run --with playwright python tests/e2e/mobile_progress_preview_smoke.py`.
TARGET_URL = "http://localhost:5273"
BROWSER_CANDIDATES = [
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
]


def launch_browser(playwright):
    for candidate in BROWSER_CANDIDATES:
        if candidate.exists():
            return playwright.chromium.launch(headless=True, executable_path=str(candidate))
    return playwright.chromium.launch(headless=True)


def main() -> None:
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        page = browser.new_page(viewport={"width": 430, "height": 932})
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_load_state("networkidle", timeout=30_000)
        page.evaluate(
            """
            () => {
              window.localStorage.setItem('lianleme.mobile.session', JSON.stringify({
                accessToken: 'tok_progress_smoke',
                userId: 'u_demo',
                email: 'demo@example.com'
              }))
            }
            """
        )
        page.reload(wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_load_state("networkidle", timeout=30_000)

        page.locator("[data-preview-tab='progress']").click()
        expect(page.locator("body")).to_contain_text("本周数据周报")
        expect(page.locator("body")).to_contain_text("饮食总结")
        expect(page.locator("body")).to_contain_text("运动总结")
        expect(page.locator("body")).to_contain_text("体重趋势")
        expect(page.locator("body")).to_contain_text("AI 教练建议")
        expect(page.locator("body")).to_contain_text("练了么")
        expect(page.locator("body")).to_contain_text("吃了么")
        expect(page.locator("body")).to_contain_text("瘦了么")
        # keep the major progress cards as block containers so H5 backgrounds render as full surfaces instead of inline line boxes; progress preview layout only; verify this smoke fails if any critical card computes to inline.
        display_modes = page.evaluate(
            """
            () => ['.report-card', '.summary-card', '.trend-card', '.detail-card', '.coach-card'].map((selector) => {
              const element = document.querySelector(selector)
              return [selector, window.getComputedStyle(element).display]
            })
            """
        )
        for selector, display_mode in display_modes:
            assert display_mode != "inline", f"{selector} rendered inline in H5 preview: {display_mode}"
        page.get_by_text("个人中心").click()
        expect(page.locator("body")).to_contain_text("我的资料")

        browser.close()


if __name__ == "__main__":
    main()
