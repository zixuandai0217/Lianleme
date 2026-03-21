from pathlib import Path

from playwright.sync_api import expect, sync_playwright


# Why: lock the workout-to-photo-customize preview flow before the new camera page lands so the entry and key camera UI copy are covered together; Scope: mobile H5 photo-customize preview smoke only; Verify: `uv run --with playwright python tests/e2e/mobile_photo_customize_preview_smoke.py`.
TARGET_URL = "http://localhost:5173"
BROWSER_CANDIDATES = [
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
]


def launch_browser(playwright):
    # keep the preview smoke runnable on local macOS and Windows boxes; browser executable selection for H5 smoke only; verify by running the smoke without editing hard-coded paths.
    for candidate in BROWSER_CANDIDATES:
        if candidate.exists():
            return playwright.chromium.launch(headless=True, executable_path=str(candidate))
    return playwright.chromium.launch(headless=True)


def main() -> None:
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_load_state("networkidle", timeout=30_000)

        page.get_by_text("拍照定制").first.click()
        body = page.locator("body")
        phone_shell = page.locator(".phone-shell")

        expect(body).to_contain_text("AI 智能拍照定制")
        expect(body).to_contain_text("选择拍摄模式")
        expect(body).to_contain_text("点击拍照")
        expect(body).to_contain_text("体态分析")
        expect(body).to_contain_text("器械识别")
        # keep the desktop H5 preview locked to a centered mobile shell instead of stretching edge-to-edge; photo-customize layout width only; verify by asserting the shell width stays under phone-sized bounds.
        shell_box = phone_shell.bounding_box()
        if shell_box is None:
            raise SystemExit("Phone shell not found")
        if shell_box["width"] > 430:
            raise SystemExit(f"Phone shell too wide: {shell_box['width']}")

        browser.close()


if __name__ == "__main__":
    main()
