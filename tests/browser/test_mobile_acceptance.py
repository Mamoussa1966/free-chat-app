"""Phone-viewport acceptance smoke for the real Streamlit UI.

Runs main.py locally with no secrets, no Auth session, no provider keys, no
voice input, and no conversation submission. Only local session state changes.
"""
from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest

pytest.importorskip(
    "playwright", reason="mobile browser acceptance requires Playwright Chromium"
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def local_council_app(tmp_path_factory):
    """Start the production Streamlit entrypoint in a no-secrets local process."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    base_url = f"http://127.0.0.1:{port}"
    log_path = tmp_path_factory.mktemp("mobile-acceptance") / "streamlit.log"
    env = os.environ.copy()
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    env.pop("SUPABASE_AUTH_ENABLED", None)
    env.pop("SUPABASE_URL", None)
    env.pop("SUPABASE_PUBLISHABLE_KEY", None)

    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(ROOT / "main.py"),
                "--server.headless=true",
                f"--server.port={port}",
                "--server.address=127.0.0.1",
                "--browser.gatherUsageStats=false",
            ],
            cwd=ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    with urlopen(f"{base_url}/_stcore/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except (URLError, TimeoutError, OSError):
                    time.sleep(0.25)
            else:
                process.terminate()
                process.wait(timeout=5)
                raise RuntimeError(
                    "The local Council UI did not become healthy. "
                    f"Server log: {log_path.read_text(encoding='utf-8', errors='replace')}"
                )

            if process.poll() is not None:
                raise RuntimeError(
                    "The local Council UI exited during startup. "
                    f"Server log: {log_path.read_text(encoding='utf-8', errors='replace')}"
                )
            yield base_url
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def _open_sidebar(page) -> None:
    sidebar = page.locator('[data-testid="stSidebar"]')
    if sidebar.locator("button").count() and sidebar.is_visible():
        return

    possible_controls = [
        page.locator('[data-testid="stSidebarCollapsedControl"] button'),
        page.get_by_role("button", name="Open sidebar"),
        page.get_by_role("button", name="Open sidebar", exact=False),
    ]
    for control in possible_controls:
        if control.count() and control.first.is_visible():
            control.first.click()
            sidebar.wait_for(state="visible", timeout=10_000)
            return
    raise AssertionError("Streamlit sidebar could not be opened at the phone viewport")


def test_real_council_sidebar_order_new_chat_and_phone_layout(local_council_app):
    from playwright.sync_api import sync_playwright

    artifact_dir = ROOT / "artifacts" / "mobile-acceptance"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=1,
            is_mobile=True,
            has_touch=True,
        )
        page = context.new_page()
        try:
            page.goto(local_council_app, wait_until="domcontentloaded", timeout=30_000)
            page.locator("h1").filter(has_text="AI Council").wait_for(
                state="visible", timeout=45_000
            )
            _open_sidebar(page)

            sidebar = page.locator('[data-testid="stSidebar"]')
            sidebar_text = sidebar.inner_text()
            for expected in (
                "📚 سجل المحادثات",
                "🗑️ مسح المحادثة الحالية",
                "🧹 مسح جميع المحادثات",
                "📦 النسخ الاحتياطية",
                "➕ محادثة جديدة مستقلة",
            ):
                assert expected in sidebar_text, f"Missing sidebar control: {expected}"

            ordered_controls = page.evaluate(
                """() => {
                    const root = document.querySelector('[data-testid="stSidebar"]');
                    if (!root) return [];
                    return Array.from(root.querySelectorAll('button'))
                        .map((node) => (node.innerText || node.getAttribute('aria-label') || '').trim())
                        .filter(Boolean);
                }"""
            )
            labels = [
                "📚 سجل المحادثات",
                "🗑️ مسح المحادثة الحالية",
                "🧹 مسح جميع المحادثات",
                "📦 النسخ الاحتياطية",
            ]
            positions = []
            for label in labels:
                found = next(
                    (i for i, value in enumerate(ordered_controls) if label in value),
                    None,
                )
                assert found is not None, f"Sidebar button missing from DOM: {label}"
                positions.append(found)
            assert positions == sorted(positions), {
                "expected_order": labels,
                "actual_button_texts": ordered_controls,
            }

            # Creating an empty local chat is safe: no message is sent and no provider is called.
            page.get_by_role(
                "button", name="➕ محادثة جديدة مستقلة"
            ).click()
            page.get_by_text(
                "محادثة جديدة مستقلة وجاهزة. المحادثات السابقة محفوظة في السجل ولم يتم نقل رسائلها إلى هذه الغرفة.",
                exact=False,
            ).wait_for(state="visible", timeout=15_000)

            # The actual production composer must remain available to touch users.
            textareas = page.locator("textarea")
            assert textareas.count() >= 1
            assert textareas.first.is_visible()

            dimensions = page.evaluate(
                """() => ({
                    viewportWidth: window.innerWidth,
                    documentWidth: document.documentElement.scrollWidth,
                    bodyWidth: document.body.scrollWidth
                })"""
            )
            assert dimensions["documentWidth"] <= dimensions["viewportWidth"] + 3, dimensions
            assert dimensions["bodyWidth"] <= dimensions["viewportWidth"] + 3, dimensions
            assert "تسجيل الدخول إلى مجلس الذكاء الاصطناعي" not in page.locator("body").inner_text()
        except Exception:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(
                path=str(artifact_dir / "mobile-acceptance-failure.png"),
                full_page=True,
            )
            raise
        finally:
            context.close()
            browser.close()
