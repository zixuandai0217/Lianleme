from pathlib import Path

from playwright.sync_api import expect, sync_playwright


# keep the progress landing smoke focused on authenticated page content instead of the auth gate; H5 progress smoke only; verify with `uv run --with playwright python tests/e2e/mobile_progress_preview_smoke.py`.
TARGET_URL = "http://localhost:5173"
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
        page.get_by_text("个人中心").click()
        expect(page.locator("body")).to_contain_text("我的资料")

        browser.close()


if __name__ == "__main__":
    main()
