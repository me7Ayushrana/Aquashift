#!/usr/bin/env python3
"""AquaShift Headless Browser Verification Script.

Automates Chrome via the Chrome DevTools Protocol (CDP) to:
1. Verify AquaShift branding, tagline, visual palette, and 6-stage pipeline.
2. Confirm the frontend connects to the backend and displays "Online (200 OK)".
3. Verify 0 console errors and 0 unhandled JavaScript exceptions.
4. Verify no horizontal layout overflow at both 1440px and 390px widths.
5. Capture high-resolution desktop (1440px) and mobile (390px) screenshots.
"""
import os
import sys
import json
import time
import base64
import urllib.request
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = ROOT_DIR / "docs" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CDP_PORT = 9222


def main():
    print("🌐 Starting AquaShift Browser Verification Suite...")

    # Launch Chrome headless with remote debugging
    chrome_cmd = [
        CHROME_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--remote-debugging-port={CDP_PORT}",
        "about:blank"
    ]
    chrome_proc = subprocess.Popen(chrome_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"🚀 Launched headless Chrome (PID {chrome_proc.pid}) on port {CDP_PORT}")

    time.sleep(1.5)

    try:
        # Get target websocket URL
        tabs_url = f"http://127.0.0.1:{CDP_PORT}/json"
        req = urllib.request.urlopen(tabs_url)
        tabs = json.loads(req.read().decode())
        target_tab = tabs[0]
        ws_url = target_tab["webSocketDebuggerUrl"]
        print(f"🔌 Connected to Chrome DevTools Protocol: {ws_url}")

        import websockets.sync.client as ws_client
        with ws_client.connect(ws_url) as ws:
            msg_counter = 1

            def call(method, params=None):
                nonlocal msg_counter
                msg_id = msg_counter
                msg_counter += 1
                payload = {"id": msg_id, "method": method, "params": params or {}}
                ws.send(json.dumps(payload))
                while True:
                    raw = ws.recv()
                    data = json.loads(raw)
                    if data.get("id") == msg_id:
                        return data.get("result", {})

            # Enable Page, Runtime
            call("Page.enable")
            call("Runtime.enable")

            # Intercept console.error and unhandled exceptions before page scripts run
            call("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                window.__consoleErrors = [];
                window.__unhandledExceptions = [];
                const _origError = console.error;
                console.error = function(...args) {
                    window.__consoleErrors.push(args.map(a => String(a)).join(' '));
                    _origError.apply(console, args);
                };
                window.addEventListener('error', function(e) {
                    window.__unhandledExceptions.push(e.message || String(e));
                });
                window.addEventListener('unhandledrejection', function(e) {
                    window.__unhandledExceptions.push(e.reason ? (e.reason.message || String(e.reason)) : 'Unhandled rejection');
                });
                """
            })

            # Navigate to frontend
            target_frontend = "http://127.0.0.1:5173/"
            print(f"🧭 Navigating to {target_frontend} ...")
            call("Page.navigate", {"url": target_frontend})

            # Wait for load and API health check resolution
            time.sleep(2.5)

            # Check DOM contents
            eval_res = call("Runtime.evaluate", {
                "expression": """
                (() => {
                    const text = document.body.innerText;
                    return {
                        hasTitle: text.includes("AquaShift"),
                        hasTagline: text.includes("Plan crops. Balance water. Protect livelihoods."),
                        hasPipeline: text.includes("Six-Stage AquaShift Pipeline"),
                        hasFooter: text.includes("Synthetic demo data calibrated to public agri statistics."),
                        hasOnlineStatus: text.includes("Online (200 OK)"),
                        consoleErrors: window.__consoleErrors || [],
                        unhandledExceptions: window.__unhandledExceptions || []
                    };
                })()
                """,
                "returnByValue": True
            })

            dom_info = eval_res.get("result", {}).get("value", {})
            console_errors = dom_info.get("consoleErrors", [])
            unhandled_exceptions = dom_info.get("unhandledExceptions", [])

            print("\n📋 DOM & Status Verification Results:")
            print(f"  • Title 'AquaShift' present: {dom_info.get('hasTitle')}")
            print(f"  • Tagline present: {dom_info.get('hasTagline')}")
            print(f"  • Six-Stage Pipeline present: {dom_info.get('hasPipeline')}")
            print(f"  • Synthetic Data Footer present: {dom_info.get('hasFooter')}")
            print(f"  • Backend Status 'Online (200 OK)': {dom_info.get('hasOnlineStatus')}")
            print(f"  • Console Errors: {len(console_errors)} {console_errors if console_errors else '(Clean)'}")
            print(f"  • Unhandled Exceptions: {len(unhandled_exceptions)} {unhandled_exceptions if unhandled_exceptions else '(Clean)'}")

            # 1. Desktop 1440px Viewport & Screenshot
            call("Emulation.setDeviceMetricsOverride", {
                "width": 1440,
                "height": 900,
                "deviceScaleFactor": 1,
                "mobile": False
            })
            time.sleep(0.5)

            desktop_overflow_check = call("Runtime.evaluate", {
                "expression": "document.documentElement.scrollWidth > window.innerWidth",
                "returnByValue": True
            })
            is_desktop_overflow = desktop_overflow_check.get("result", {}).get("value", False)
            print(f"\n🖥️ Desktop Layout Verification (1440px Width):")
            print(f"  • Layout Overflow: {'FAILED' if is_desktop_overflow else 'PASSED (0 horizontal scroll)'}")

            shot_1440 = call("Page.captureScreenshot", {"format": "png"})
            desktop_png = SCREENSHOT_DIR / "desktop_1440.png"
            with open(desktop_png, "wb") as f:
                f.write(base64.b64decode(shot_1440["data"]))
            print(f"  • Screenshot saved: {desktop_png} ({desktop_png.stat().st_size} bytes)")

            # 2. Mobile 390px Viewport & Screenshot
            call("Emulation.setDeviceMetricsOverride", {
                "width": 390,
                "height": 844,
                "deviceScaleFactor": 2,
                "mobile": True
            })
            time.sleep(0.5)

            mobile_overflow_check = call("Runtime.evaluate", {
                "expression": "document.documentElement.scrollWidth > window.innerWidth",
                "returnByValue": True
            })
            is_mobile_overflow = mobile_overflow_check.get("result", {}).get("value", False)
            print(f"\n📱 Mobile Layout Verification (390px Width):")
            print(f"  • Layout Overflow: {'FAILED' if is_mobile_overflow else 'PASSED (0 horizontal scroll)'}")

            shot_390 = call("Page.captureScreenshot", {"format": "png"})
            mobile_png = SCREENSHOT_DIR / "mobile_390.png"
            with open(mobile_png, "wb") as f:
                f.write(base64.b64decode(shot_390["data"]))
            print(f"  • Screenshot saved: {mobile_png} ({mobile_png.stat().st_size} bytes)")

            # Copy to artifacts directory if available
            artifact_dir = ROOT_DIR.parent / ".gemini" / "antigravity" / "brain" / "a273a544-9471-434e-a3f8-b5791a6c6ab8"
            if artifact_dir.exists():
                import shutil
                shutil.copy2(desktop_png, artifact_dir / "desktop_1440.png")
                shutil.copy2(mobile_png, artifact_dir / "mobile_390.png")
                print(f"  • Screenshots mirrored to artifact directory: {artifact_dir}")

            # Overall verification checks
            checks_passed = (
                dom_info.get("hasTitle") and
                dom_info.get("hasTagline") and
                dom_info.get("hasPipeline") and
                dom_info.get("hasFooter") and
                dom_info.get("hasOnlineStatus") and
                len(console_errors) == 0 and
                len(unhandled_exceptions) == 0 and
                not is_desktop_overflow and
                not is_mobile_overflow
            )

            if checks_passed:
                print("\n🎉 ALL BROWSER CHECKS PASSED PERFECTLY!")
                return 0
            else:
                print("\n❌ SOME CHECKS FAILED.")
                return 1

    finally:
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            chrome_proc.kill()
        print("🛑 Headless Chrome process terminated.")


if __name__ == "__main__":
    sys.exit(main())
