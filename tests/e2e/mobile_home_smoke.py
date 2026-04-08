from pathlib import Path

from playwright.sync_api import sync_playwright


# keep the workout landing smoke focused on authenticated homepage content instead of the auth gate; H5 workout smoke only; verify with `uv run --with playwright python tests/e2e/mobile_home_smoke.py`.
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
    required_tokens = [
        "AI COACH",
        "今日训练",
        "方案定制",
        "练了么",
        "吃了么",
        "瘦了么",
    ]

    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        page = browser.new_page(viewport={"width": 430, "height": 932})
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_load_state("networkidle", timeout=30_000)
        page.evaluate(
            """
            () => {
              window.localStorage.setItem('lianleme.mobile.session', JSON.stringify({
                accessToken: 'tok_home_smoke',
                userId: 'u_demo',
                email: 'demo@example.com'
              }))
            }
            """
        )
        page.reload(wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_load_state("networkidle", timeout=30_000)
        body_text = page.locator("body").inner_text()
        browser.close()

    missing_tokens = [token for token in required_tokens if token not in body_text]
    if missing_tokens:
        raise SystemExit(f"Missing homepage tokens: {', '.join(missing_tokens)}")


if __name__ == "__main__":
    main()
