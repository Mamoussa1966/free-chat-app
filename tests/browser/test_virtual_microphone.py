"""Independent browser test for the virtual microphone and production voice UI contract.

Run in CI after installing requirements.txt and Playwright Chromium:
    pytest -q tests/browser/test_virtual_microphone.py

The browser test uses Chromium's synthetic microphone and grants microphone
permission only to the local test server. It never opens the production app,
uses account credentials, or submits audio to a provider.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest

pytest.importorskip(
    "playwright", reason="browser test requires Playwright; the dedicated workflow installs it"
)

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests" / "browser" / "voice_audio_smoke_app.py"


@pytest.fixture(scope="module")
def streamlit_server(tmp_path_factory):
    """Start a local Streamlit harness without authentication or external APIs."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    base_url = f"http://127.0.0.1:{port}"
    log_path = tmp_path_factory.mktemp("voice-browser") / "streamlit.log"
    env = os.environ.copy()
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(HARNESS),
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
            deadline = time.monotonic() + 45
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
                    "The local Streamlit voice test harness did not become healthy. "
                    f"Server log: {log_path.read_text(encoding='utf-8', errors='replace')}"
                )

            if process.poll() is not None:
                raise RuntimeError(
                    "The local Streamlit voice test harness exited early. "
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


def test_production_voice_preview_controls_are_ordered():
    """Catch label/order drift without importing or executing authenticated app code."""
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    room_start = source.index("def _render_user_room(")
    audio_input = source.index(
        'st.audio_input("🎙️ تسجيل رسالة صوتية"', room_start
    )
    preview_player = source.index("st.audio(audio_bytes, format=mime)", audio_input)
    discard_button = source.index('"🗑️ حذف التسجيل قبل الإرسال"', preview_player)
    send_button = source.index(
        'st.button("🎤 إرسال الصوت للمجلس"', discard_button
    )

    assert audio_input < preview_player < discard_button < send_button
    voice_section = source[audio_input:send_button]
    assert "st.session_state.voice_nonce = int(" in voice_section
    assert "st.session_state.last_voice_transcription = {}" in voice_section
    assert "st.session_state.last_voice_error = \"\"" in voice_section
    assert "st.rerun()" in voice_section


def test_virtual_microphone_permission_capture_preview_and_discard(streamlit_server):
    """Verify Chromium can capture fake microphone audio and Streamlit receives a recording."""
    from playwright.sync_api import sync_playwright

    artifact_dir = ROOT / "artifacts" / "voice-browser"
    base_url = streamlit_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
                "--autoplay-policy=no-user-gesture-required",
            ],
        )
        context = browser.new_context(
            locale="en-US",
            permissions=["microphone"],
        )
        page = context.new_page()
        try:
            page.goto(base_url, wait_until="domcontentloaded", timeout=30_000)
            page.get_by_role("heading", name="اختبار الميكروفون الافتراضي").wait_for(
                state="visible", timeout=20_000
            )

            # Probe capture permission and actual MediaRecorder output directly.
            # This is separate from Streamlit widget interaction, so failures show
            # whether the browser/virtual-device layer itself is broken.
            capture = page.evaluate(
                """async () => {
                    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                        throw new Error("getUserMedia is unavailable in this browser context");
                    }
                    if (typeof MediaRecorder === "undefined") {
                        throw new Error("MediaRecorder is unavailable in Chromium");
                    }
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    const track = stream.getAudioTracks()[0];
                    if (!track || track.readyState !== "live") {
                        stream.getTracks().forEach((item) => item.stop());
                        throw new Error("The virtual microphone did not provide a live audio track");
                    }
                    const preferredMime = ["audio/webm;codecs=opus", "audio/webm"]
                        .find((type) => MediaRecorder.isTypeSupported(type));
                    const recorder = preferredMime
                        ? new MediaRecorder(stream, { mimeType: preferredMime })
                        : new MediaRecorder(stream);
                    const chunks = [];
                    recorder.addEventListener("dataavailable", (event) => {
                        if (event.data && event.data.size > 0) chunks.push(event.data);
                    });
                    const stopped = new Promise((resolve, reject) => {
                        recorder.addEventListener("stop", resolve, { once: true });
                        recorder.addEventListener("error", (event) => {
                            reject(event.error || new Error("MediaRecorder failed"));
                        }, { once: true });
                    });
                    recorder.start();
                    await new Promise((resolve) => setTimeout(resolve, 900));
                    recorder.stop();
                    await stopped;
                    const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
                    const result = {
                        permissionState: await navigator.permissions.query({ name: "microphone" })
                            .then((permission) => permission.state),
                        trackState: track.readyState,
                        mimeType: blob.type,
                        recordedBytes: blob.size
                    };
                    stream.getTracks().forEach((item) => item.stop());
                    return result;
                }"""
            )
            assert capture["permissionState"] == "granted", capture
            assert capture["trackState"] == "live", capture
            assert capture["recordedBytes"] > 0, capture

            # Exercise Streamlit's actual st.audio_input widget with the same fake device.
            widget = page.locator('[class*="st-key-voice_input_0"]')
            record_button = widget.locator("button").first
            assert record_button.count() > 0, "st.audio_input record button is missing"
            record_button.click()
            page.wait_for_timeout(900)
            record_button.click()

            page.get_by_text(
                re.compile(r"Captured audio bytes:\s*[1-9]\d*")
            ).wait_for(state="visible", timeout=30_000)
            page.get_by_role(
                "button", name="🗑️ حذف التسجيل قبل الإرسال"
            ).wait_for(state="visible", timeout=10_000)
            page.get_by_role(
                "button", name="🎤 إرسال الصوت للمجلس"
            ).wait_for(state="visible", timeout=10_000)
            assert "TEST ONLY" not in page.locator("body").inner_text()

            # Verify preview deletion rotates the widget key and does not submit.
            page.get_by_role(
                "button", name="🗑️ حذف التسجيل قبل الإرسال"
            ).click()
            page.get_by_text("No pending audio preview.").wait_for(
                state="visible", timeout=15_000
            )
            page.get_by_text("Test-only submission count: 0").wait_for(
                state="visible", timeout=10_000
            )
        except Exception:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(
                path=str(artifact_dir / "virtual-microphone-failure.png"),
                full_page=True,
            )
            raise
        finally:
            context.close()
            browser.close()
