"""Capture the README screenshots from the real portal and a real bot run.

    python scripts/capture_screenshots.py

Writes PNGs to docs/screenshots/. Uses a temporary portal and temp output/log folders,
so it never touches your own output/ or logs/runs.csv.
"""

import html
import logging
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from portal import create_app  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
logging.getLogger("werkzeug").setLevel(logging.ERROR)  # hide per-request server lines
USER, PASSWORD = "demo_user", "screenshot-demo-only"
BASE = {"USERNAME": USER, "PASSWORD": PASSWORD, "FAIL_FIRST_LOGIN": False, "SLOW_MODE": 0,
        "MISSING_REPORT": "", "SHOW_POPUP": False, "SESSION_TIMEOUT": 0}


def start_portal(**faults):
    server = make_server("127.0.0.1", 0, create_app({**BASE, **faults}), threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def login(page, url, password=PASSWORD):
    page.goto(f"{url}/login")
    page.get_by_label("Username").fill(USER)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Log In").click()


def portal_pages(browser):
    page = browser.new_page(viewport={"width": 820, "height": 480})
    shot = lambda name: page.screenshot(path=OUT / f"{name}.png")

    server, url = start_portal()
    page.goto(f"{url}/login")
    shot("01-login")
    login(page, url, password="wrong")
    shot("02-login-rejected")
    login(page, url)
    page.get_by_label("Month").select_option("2026-09")
    page.get_by_role("button", name="Filter").click()
    shot("03-reports-page-1")
    page.get_by_test_id("next-page").click()
    shot("04-reports-page-2")
    server.shutdown()

    server, url = start_portal(FAIL_FIRST_LOGIN=True)
    login(page, url)
    shot("05-server-busy-503")
    server.shutdown()

    server, url = start_portal(SHOW_POPUP=True)
    login(page, url)
    shot("06-popup-notice")
    server.shutdown()

    server, url = start_portal(SESSION_TIMEOUT=1)
    login(page, url)
    page.get_by_role("button", name="Filter").click()  # 2nd request -> session expires
    shot("07-session-expired")
    server.shutdown()
    page.close()


def terminal(browser, title, text, name):
    """Render real console output as a terminal-style image."""
    page = browser.new_page(viewport={"width": 980, "height": 200})
    page.set_content(
        "<body style='margin:0;background:#1e1e1e'>"
        "<div style='background:#3c3c3c;color:#ccc;font:12px sans-serif;padding:6px 12px'>" + html.escape(title) + "</div>"
        "<pre style='margin:0;padding:12px 16px;color:#d4d4d4;font:13px/1.45 Menlo,Consolas,monospace;"
        "white-space:pre-wrap'>" + html.escape(text) + "</pre></body>"
    )
    page.screenshot(path=OUT / f"{name}.png", full_page=True)
    page.close()


def bot_run(tmp):
    """Run the real bot (broken login scenario) and return its console output."""
    server, url = start_portal(FAIL_FIRST_LOGIN=True)
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    cfg.update(portal_url=url)  # output/ and logs/ stay relative, inside the temp folder
    (tmp / "config.yaml").write_text(yaml.safe_dump(cfg))
    env = {**os.environ, "PORTAL_USERNAME": USER, "PORTAL_PASSWORD": PASSWORD, "PYTHONPATH": str(ROOT)}
    cmd = [sys.executable, "-m", "bot", "--month", "2026-09"]
    result = subprocess.run(cmd, cwd=tmp, env=env, capture_output=True, text=True)
    server.shutdown()
    files = sorted(p.name for p in (tmp / "output" / "2026-09").iterdir())
    console = f"$ python -m bot --month 2026-09\n{result.stderr}{result.stdout}$ echo $?\n{result.returncode}\n"
    console += "$ ls output/2026-09\n" + "\n".join(files) + "\n"
    shots = sorted((tmp / "logs" / "screenshots").glob("*.png"))
    return console, shots


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
        browser = p.chromium.launch()
        portal_pages(browser)
        console, shots = bot_run(Path(tmp))
        terminal(browser, "Terminal - bot recovering from a 'Server busy' login", console, "08-bot-console-recovery")
        if shots:  # the screenshot the bot itself saved as evidence of the failed attempt
            (OUT / "09-bot-error-evidence.png").write_bytes(shots[0].read_bytes())
        browser.close()
    print("\n".join(sorted(str(f.relative_to(ROOT)) for f in OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
