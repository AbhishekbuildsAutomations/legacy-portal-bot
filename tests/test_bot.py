import re
from pathlib import Path

from portal.reports import build_file

EXPECTED_FILES = sorted([
    "sales-summary_2026-09.csv", "inventory-levels_2026-09.xlsx", "accounts-receivable-aging_2026-09.pdf",
    "customer-returns_2026-09.csv", "vendor-payments_2026-09.xlsx", "freight-charges_2026-09.csv",
    "compliance-certificate_2026-09.pdf",
])


def test_happy_path(portal, bot):
    record = bot(portal())
    assert record.outcome == "success"
    assert record.downloaded == 7
    assert sorted(p.name for p in bot.output.iterdir()) == EXPECTED_FILES
    assert all(p.stat().st_size > 0 for p in bot.output.iterdir())
    assert bot.log()[-1]["outcome"] == "success"


def test_fail_first_login_retries(portal, bot):
    record = bot(portal(FAIL_FIRST_LOGIN=True))
    assert record.outcome == "success"
    assert bot.log()[-1]["login_attempts"] == 2
    assert record.screenshots  # the busy page was captured


def test_wrong_password_stops_cleanly(portal, bot):
    record = bot(portal(), password="wrong")
    entry = bot.log()[-1]
    assert entry["outcome"] == "failed"
    assert entry["login_attempts"] == 1  # permanent failure: no retries
    assert any("Login rejected" in e for e in entry["errors"])
    assert record.downloaded == 0


def test_missing_report_is_partial(portal, bot):
    record = bot(portal(MISSING_REPORT="vendor-payments:2026-09"))
    entry = bot.log()[-1]
    assert entry["outcome"] == "partial"
    assert entry["missing"] == ["Vendor Payments"]
    assert record.downloaded == 6


def test_rerun_skips_existing_files(portal, bot):
    url = portal()
    bot(url)
    second = bot(url)
    assert second.outcome == "success"
    assert (second.downloaded, second.skipped) == (0, 7)


def test_session_timeout_relogs_and_completes(portal, bot):
    record = bot(portal(SESSION_TIMEOUT=6, SHOW_POPUP=True))
    assert record.outcome == "success"
    assert record.downloaded == 7
    assert record.login_attempts >= 2


def test_no_coordinate_based_calls():
    # mouse.click(x, y), mouse.move(...), touchscreen.tap(x, y), click(position={"x": .., "y": ..})
    pattern = re.compile(r"\b(mouse|touchscreen)\s*\.\s*\w+\s*\(|position\s*=")
    bad = ['page.mouse.click(100, 200)', 'page.mouse.move(5, 5)', 'page.touchscreen.tap(1, 2)',
           'loc.click(position={"x": 1, "y": 2})']
    assert all(pattern.search(b) for b in bad)  # the checker itself works
    hits = [f"{path}:{n}: {line.strip()}"
            for path in Path("bot").rglob("*.py")
            for n, line in enumerate(path.read_text().splitlines(), 1)
            if pattern.search(line)]
    assert not hits, "coordinate-based calls found:\n" + "\n".join(hits)


def test_files_are_deterministic(monkeypatch):
    import time
    for slug in ("sales-summary", "inventory-levels", "compliance-certificate"):
        monkeypatch.setattr(time, "time", lambda: 1_700_000_000)
        first = build_file(slug, "2026-09")
        monkeypatch.setattr(time, "time", lambda: 1_800_000_000)  # a different "now"
        assert build_file(slug, "2026-09") == first
