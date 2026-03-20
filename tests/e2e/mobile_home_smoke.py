from pathlib import Path

from playwright.sync_api import sync_playwright


# Why: lock the richer workout-home landmarks before redesign regression sneaks back in; Scope: mobile H5 homepage smoke coverage only; Verify: `uv run --with playwright python tests/e2e/mobile_home_smoke.py`.
EDGE_PATH = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
TARGET_URL = "http://localhost:5173"


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
        browser = playwright.chromium.launch(headless=True, executable_path=str(EDGE_PATH))
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
