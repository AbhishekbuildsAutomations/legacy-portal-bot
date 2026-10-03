# Scope and limitations

This bot automates one specific portal by finding elements through their labels, roles, test IDs and IDs. That is sturdier than screen coordinates, but it still depends on the portal staying the way it is. This note lists what would break it and why.

## UI changes that would break the bot

| Change on the portal | What breaks | Why |
|---|---|---|
| **Renamed labels or buttons**, e.g. "Username" becomes "User ID", "Log In" becomes "Sign in", "Filter" becomes "Go", "Dismiss" becomes "OK" | Login, filtering or popup dismissal | The bot finds these by their visible label or accessible name (`get_by_label("Username")`, `get_by_role("button", name="Log In")`). New wording means no match, and the step times out. |
| **Removed or renamed test IDs** (`report-row`, `report-name`, `next-page`, `login-error`, `server-busy`) | Reading the table, pagination, telling "busy" apart from "wrong password" | These hooks are how the bot reads the table and recognises outcomes. Without them it can't tell which page it's on. |
| **Changed login flow**: two-factor codes, CAPTCHA, single sign-on (SAML/OIDC redirect to another site), a "remember this device" step | Login | The bot expects one form with a username, a password and a button, followed by the reports page. Any extra step means none of the three outcomes it waits for appears, so it treats this as a transient failure, retries, then stops with `failed`. |
| **Different table layout**: report name no longer in its own cell, a grid of cards instead of rows, more than one download link per row | Collecting reports | The bot reads one name and one "Download" link from each `report-row`. |
| **Different pagination**: infinite scroll, "Load more" button, page-number links without a "Next" link, a page-size selector | Bot stops after page 1 and reports the rest as `missing` | The bot follows the `next-page` link until it disappears. |
| **Month filter changes**: free-text date box, date picker, separate year/month dropdowns, a different month format such as "Sep 2026" | Filtering, run `failed` | The bot picks the value `YYYY-MM` from a dropdown labelled "Month". |
| **Changed download format**: links that open a preview page or a new tab, a "Generate report" step that emails the file later, or downloads delivered as a ZIP | Downloading | The bot expects a click on "Download" to start a browser download directly. A ZIP or any extension not in `allowed_file_types` is logged as an error and the run ends `partial`. |
| **Full redesign**, e.g. a move to a single-page app or a new vendor | Everything | All selectors are tied to the current markup. A redesign means rewriting the selectors, though the run log, retries, renaming and scheduling would stay the same. |
| **Session rules change**: much shorter expiry, a limit of one active session (a scheduled run logs out a human user or the reverse), forced password rotation | Mid-run failures | Re-login is capped at `max_relogins` (5). If a session dies before the bot makes progress, the run ends `failed`. An expired password looks like "credentials rejected", which is correctly treated as permanent. |
| **File types it doesn't expect**, e.g. `.xls`, `.docx`, `.zip` | That report | Anything outside `allowed_file_types` (csv, xlsx, pdf) is rejected rather than filed. Change the list in `config.yaml` to accept more. |
| **Report renamed on the portal**, e.g. "Vendor Payments" becomes "Supplier Payments" | That report is reported `missing` | Expected reports are matched by exact name from `config.yaml`. |

## What it does not do

- **It does not solve CAPTCHAs or bypass bot detection.** If a CAPTCHA appears, the run stops. Bypassing one would break most sites' terms of use.
- **It does not handle two-factor authentication** (codes, push approvals, hardware keys).
- **It does not do single sign-on** or log in through Microsoft, Google or Okta.
- **It does not check what's inside files.** It checks only that a file exists, isn't empty and has an allowed extension. A CSV full of the wrong numbers would pass.
- **It does not handle a report published twice** in the same month. It downloads the first one it sees.
- **It does not start the portal.** If the portal isn't running, a scheduled run retries the login with backoff, then stops with outcome `failed`.
- **It does not send alerts.** Failures go to the run log, screenshots and the exit code. Nothing sends an email or Slack message yet.
- **It does not store credentials securely.** `.env` is a plain-text file on disk. In production, use the macOS Keychain, Windows Credential Manager or a vault.
- **It runs one browser, one month at a time.** There's no parallel downloading and no queue of runs.
- **It has only been tested against the fake portal in this repo.** That's deliberate: it never targets real sites.
