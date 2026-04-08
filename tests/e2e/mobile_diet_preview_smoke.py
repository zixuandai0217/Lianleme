from pathlib import Path

from playwright.sync_api import expect, sync_playwright


# keep the diet landing smoke focused on authenticated page content instead of the auth gate; H5 diet smoke only; verify with `uv run --with playwright python tests/e2e/mobile_diet_preview_smoke.py`.
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
                accessToken: 'tok_diet_smoke',
                userId: 'u_demo',
                email: 'demo@example.com'
              }))
            }
            """
        )
        page.reload(wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_load_state("networkidle", timeout=30_000)

        page.locator("[data-preview-tab='diet']").click()
        expect(page.locator("body")).to_contain_text("今日摄入")
        expect(page.locator("body")).to_contain_text("今日饮食记录")
        expect(page.locator("body")).to_contain_text("AI 推荐晚餐")
        expect(page.locator("body")).to_contain_text("练了么")
        expect(page.locator("body")).to_contain_text("吃了么")
        expect(page.locator("body")).to_contain_text("瘦了么")
        # keep the diet tab visually crimson rather than orange so the theme remains distinct from the workout and progress tabs; diet hero and CTA only; verify this smoke fails if the gradients drift away from the approved red palette.
        rendered_theme = page.evaluate(
            """
            () => {
              const hero = window.getComputedStyle(document.querySelector('.hero-card')).backgroundImage
              const cta = window.getComputedStyle(document.querySelector('.meal-cta')).backgroundImage
              return { hero, cta }
            }
            """
        )
        assert "rgb(143, 15, 46)" in rendered_theme["hero"], rendered_theme["hero"]
        assert "rgb(184, 18, 59)" in rendered_theme["cta"], rendered_theme["cta"]

        browser.close()


if __name__ == "__main__":
    main()
