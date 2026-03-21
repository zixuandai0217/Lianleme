from pathlib import Path

from playwright.sync_api import sync_playwright


# Why: lock the default H5 preview on the workout tab while the shared mobile theme changes land; Scope: mobile H5 workout landing smoke coverage only; Verify: `uv run --with playwright python tests/e2e/mobile_home_smoke.py`.
TARGET_URL = "http://localhost:5173"
BROWSER_CANDIDATES = [
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
]


# keep the preview smoke runnable on local macOS and Windows boxes; browser executable selection for H5 smoke only; verify by running the smoke without editing hard-coded paths.
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
        body_text = page.locator("body").inner_text()
        browser.close()

    missing_tokens = [token for token in required_tokens if token not in body_text]
    if missing_tokens:
        raise SystemExit(f"Missing homepage tokens: {', '.join(missing_tokens)}")


if __name__ == "__main__":
    main()
