from pathlib import Path

from playwright.sync_api import expect, sync_playwright


# keep the preview nav smoke focused on the authenticated shared tab bar instead of the auth gate; H5 tab-bar smoke only; verify with `uv run --with playwright python tests/e2e/mobile_tabbar_preview_smoke.py`.
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
                accessToken: 'tok_tabbar_smoke',
                userId: 'u_demo',
                email: 'demo@example.com'
              }))
            }
            """
        )
        page.reload(wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_load_state("networkidle", timeout=30_000)

        nav = page.locator(".preview-nav")
        expect(nav).to_be_visible()

        background = nav.evaluate("node => getComputedStyle(node).backgroundColor")
        if background not in {"rgb(255, 255, 255)", "rgba(255, 255, 255, 0.94)", "rgba(255, 255, 255, 0.96)"}:
            raise SystemExit(f"Preview tab bar is not light themed yet: {background}")

        active_color = page.locator(".nav-item.active .nav-label").evaluate("node => getComputedStyle(node).color")
        if active_color not in {"rgb(248, 100, 72)", "rgb(242, 17, 98)", "rgb(255, 122, 69)"}:
            raise SystemExit(f"Active tab color is not the design accent yet: {active_color}")

        browser.close()


if __name__ == "__main__":
    main()
