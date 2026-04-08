import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


# simplify the mobile auth experience to email/password while keeping a browser-level regression for the authenticated shell; H5 auth flow only; verify with `uv run --with playwright python tests/e2e/mobile_auth_email_flow_smoke.py`.
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
        page.add_init_script(
            """
            () => {
              window.localStorage.removeItem('lianleme.mobile.session')
            }
            """
        )
        # isolate the simplified auth flow from backend process state so the smoke only proves UI behavior plus session transition; H5 auth smoke only; verify with `uv run --with playwright python tests/e2e/mobile_auth_email_flow_smoke.py`.
        page.route(
            "**/v1/auth/register",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "access_token": "tok_auth_smoke",
                        "token_type": "bearer",
                        "user_id": "u_fresh",
                        "email": "fresh@example.com",
                    }
                ),
            ),
        )
        page.route(
            "**/v1/home/workout",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "tab": "workout",
                        "today_workout": {"name": "胸背力量强化训练", "duration_minutes": 45, "intensity": "中等"},
                        "calendar": {"month": "2026-03", "highlight_days": [3, 5, 7, 8]},
                        "ai_buddy": {
                            "entry": "/pages/workout/ai-chat",
                            "teaser": "测试会话，直接进入训练首页。",
                        },
                    }
                ),
            ),
        )
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_load_state("networkidle", timeout=30_000)

        body = page.locator("body")
        expect(body).to_contain_text("邮箱")
        expect(body).to_contain_text("密码")
        if "验证码" in body.inner_text():
            raise SystemExit("Auth page still shows verification-code flow")

        page.get_by_text("注册新账号").click()
        page.wait_for_load_state("networkidle", timeout=30_000)
        expect(body).to_contain_text("确认密码")
        if "发送验证码" in body.inner_text():
            raise SystemExit("Register page still shows send-code flow")

        page.get_by_placeholder("请输入邮箱").fill("fresh@example.com")
        page.get_by_placeholder("请输入密码").fill("secret123")
        page.get_by_placeholder("请再次输入密码").fill("secret123")
        page.get_by_role("button", name="注册并进入").click()
        page.wait_for_load_state("networkidle", timeout=30_000)

        expect(body).to_contain_text("AI COACH")
        expect(page.locator(".preview-nav")).to_be_visible()
        browser.close()


if __name__ == "__main__":
    main()
