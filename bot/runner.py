"""The bot: log in, find the month's reports, download, rename and file them.

Every element is found by label, role, test ID or element ID. No screen coordinates.
"""

import logging
import re
import time
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from . import runlog

log = logging.getLogger("bot")


class TransientLoginError(Exception):
    """Worth retrying: the portal was busy or slow."""


class FatalError(Exception):
    """Stops the run with outcome 'failed' and a clear message."""


class SessionExpired(Exception):
    """The portal bounced us back to the login page mid-run."""


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def short(exc):
    """First line of an exception message, for the log."""
    return (str(exc).strip().splitlines() or [type(exc).__name__])[0][:200]


class ReportBot:
    def __init__(self, cfg, record, username, password):
        self.cfg = cfg
        self.record = record
        self.username = username
        self.password = password
        self.month = record.month
        self.url = cfg["portal_url"].rstrip("/")
        self.out_dir = Path(cfg["output_dir"]) / self.month
        self.shot_dir = Path(cfg["logs_dir"]) / "screenshots"
        self.page = None

    # ---------- helpers ----------

    def screenshot(self, label):
        """Save a screenshot for the log. Never let a failed screenshot hide the real error."""
        self.shot_dir.mkdir(parents=True, exist_ok=True)
        path = self.shot_dir / f"{self.record.run_id}_{len(self.record.screenshots) + 1:02d}_{label}.png"
        try:
            self.page.screenshot(path=path, full_page=True)
            self.record.screenshots.append(str(path))
        except PlaywrightError:
            pass

    def error(self, message, shot_label):
        log.error(message)
        self.record.errors.append(message)
        self.screenshot(shot_label)

    def on_login_page(self):
        return self.page.get_by_label("Password").is_visible()

    def check_session(self):
        self.page.wait_for_load_state()
        if self.on_login_page():
            raise SessionExpired()

    def dismiss_popup(self):
        # Called by Playwright whenever a dialog shows up; does nothing if none ever appears.
        log.info("Notice popup appeared; dismissing it")
        self.page.get_by_role("dialog").get_by_role("button", name="Dismiss").click()

    # ---------- login ----------

    def login_once(self):
        page = self.page
        self.record.login_attempts += 1
        n = self.record.login_attempts
        log.info("Login attempt %d", n)
        reports = page.get_by_role("heading", name="Monthly Reports")
        rejected = page.get_by_test_id("login-error")
        busy = page.get_by_test_id("server-busy")
        try:
            page.goto(f"{self.url}/login")
            page.get_by_label("Username").fill(self.username)
            page.get_by_label("Password").fill(self.password)
            page.get_by_role("button", name="Log In").click()
            reports.or_(rejected).or_(busy).first.wait_for()  # whichever outcome shows up first
        except PlaywrightError as e:  # timeouts, connection refused, network drops
            self.error(f"login attempt {n}: portal unreachable or too slow ({short(e)})", "login-unreachable")
            raise TransientLoginError("portal unreachable or too slow") from e
        if busy.is_visible():
            self.error(f"login attempt {n}: portal said 'Server busy, try again'", "login-busy")
            raise TransientLoginError("portal kept saying 'Server busy'")
        if rejected.is_visible():
            msg = rejected.inner_text().strip()
            self.error(f"login attempt {n}: credentials rejected ('{msg}')", "login-rejected")
            raise FatalError(f"Login rejected: '{msg}'. Check PORTAL_USERNAME/PORTAL_PASSWORD in .env. Not retrying.")
        log.info("Logged in")

    def login(self):
        r = self.cfg["retries"]
        retrying = Retrying(
            stop=stop_after_attempt(r["login_attempts"]),
            wait=wait_exponential(multiplier=r["backoff_seconds"], max=r["backoff_max_seconds"]),
            retry=retry_if_exception_type(TransientLoginError),  # FatalError is never retried
            before_sleep=lambda s: log.warning("Retrying login in %.1fs", s.next_action.sleep),
            reraise=True,
        )
        try:
            retrying(self.login_once)
        except TransientLoginError as e:
            raise FatalError(f"Login failed after {r['login_attempts']} attempts: {e}") from e

    # ---------- reports ----------

    def download(self, row, name):
        """Download one report row. Returns 'downloaded', 'skipped' or 'error'."""
        slug = slugify(name)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        if any(f.stat().st_size > 0 for f in self.out_dir.glob(f"{slug}_{self.month}.*")):
            log.info("Skip %s: already downloaded", name)
            self.record.skipped += 1
            return "skipped"

        page = self.page
        try:
            with page.expect_download(timeout=self.cfg["timeouts"]["download_ms"]) as info:
                row.get_by_role("link", name="Download").click()
                # A download keeps us on this page; an expired session sends us to the login form.
                while not info.is_done():
                    if self.on_login_page():
                        raise SessionExpired()
                    page.wait_for_timeout(200)
            download = info.value
        except PlaywrightError as e:
            self.error(f"{name}: download failed ({short(e)})", f"download-{slug}")
            return "error"

        ext = Path(download.suggested_filename).suffix.lstrip(".").lower()
        if ext not in self.cfg["allowed_file_types"]:
            download.delete()
            self.error(f"{name}: unexpected file type '.{ext}' ({download.suggested_filename})", f"filetype-{slug}")
            return "error"

        target = self.out_dir / f"{slug}_{self.month}.{ext}"
        download.save_as(target)
        if target.stat().st_size == 0:
            target.unlink()
            self.error(f"{name}: downloaded file was empty", f"empty-{slug}")
            return "error"
        log.info("Saved %s -> %s", download.suggested_filename, target)
        self.record.downloaded += 1
        return "downloaded"

    def collect_and_download(self, seen, statuses):
        """Filter to the month, walk every page, download expected reports not yet handled."""
        page = self.page
        expected = self.cfg["expected_reports"]
        try:
            page.get_by_label("Month").select_option(self.month)
        except PlaywrightTimeout as e:
            raise FatalError(f"Month {self.month} is not offered by the portal's Month filter") from e
        page.get_by_role("button", name="Filter").click()
        self.check_session()

        page_no = 1
        while True:
            for row in page.get_by_test_id("report-row").all():
                name = row.get_by_test_id("report-name").inner_text().strip()
                seen.add(name)
                if name in expected and name not in statuses:
                    statuses[name] = self.download(row, name)
            next_link = page.get_by_test_id("next-page")
            if next_link.count() == 0:
                log.info("Read %d page(s) of results", page_no)
                return
            next_link.click()
            page_no += 1
            self.check_session()

    def run(self, headed=False, video_dir=None):
        cfg = self.cfg
        seen, statuses = set(), {}
        with sync_playwright() as p:
            # slow_mo makes recordings watchable; it adds nothing else.
            browser = p.chromium.launch(headless=not headed, slow_mo=300 if video_dir else 0)
            size = {"width": 1000, "height": 700}
            context = browser.new_context(viewport=size, record_video_dir=video_dir, record_video_size=size)
            context.set_default_timeout(cfg["timeouts"]["page_ms"])
            self.page = page = context.new_page()
            page.add_locator_handler(page.get_by_role("dialog"), self.dismiss_popup)
            try:
                max_relogins = cfg["retries"]["max_relogins"]
                for attempt in range(max_relogins + 1):
                    try:
                        self.login()
                        self.collect_and_download(seen, statuses)
                        break
                    except SessionExpired:
                        if attempt == max_relogins:
                            raise FatalError(f"Session expired {attempt + 1} times; giving up")
                        log.warning("Session expired mid-run; logging in again")
                        self.record.errors.append("recovered: session expired mid-run, logged in again")
                self.record.missing = [n for n in cfg["expected_reports"] if n not in seen]
                for name in self.record.missing:
                    log.warning("Missing on portal: %s", name)
                failed_downloads = [n for n, s in statuses.items() if s == "error"]
                self.record.outcome = "partial" if self.record.missing or failed_downloads else "success"
            except FatalError as e:
                self.record.outcome = "failed"
                log.error(str(e))
                self.record.errors.append(str(e))
            except Exception as e:  # anything unexpected: log it cleanly, never a raw traceback
                self.record.outcome = "failed"
                self.error(f"unexpected error: {type(e).__name__}: {short(e)}", "unexpected")
            finally:
                context.close()  # also finalises the video file
                if video_dir and page.video:
                    video = Path(video_dir) / f"{self.record.run_id}.webm"
                    Path(page.video.path()).rename(video)
                    log.info("Video saved: %s", video)
                browser.close()


def run(month, trigger, cfg, username, password, headed=False, video_dir=None):
    """Run once, write the run log, print a summary. Returns the RunRecord."""
    record = runlog.RunRecord(month=month, trigger=trigger)
    started = time.monotonic()
    if not username or not password:
        record.outcome = "failed"
        record.errors.append("PORTAL_USERNAME / PORTAL_PASSWORD not set (copy .env.example to .env)")
    else:
        ReportBot(cfg, record, username, password).run(headed=headed, video_dir=video_dir)
    record.finished_at = runlog.now()
    record.duration_seconds = round(time.monotonic() - started, 1)
    runlog.append(record, cfg["logs_dir"])
    print(runlog.summary(record))
    return record
