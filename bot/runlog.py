"""The run log: one JSON line + one CSV row per run, plus a printed summary."""

import csv
import json
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

EXIT_CODES = {"success": 0, "partial": 1, "failed": 2}


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class RunRecord:
    month: str
    trigger: str
    run_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2))
    started_at: str = field(default_factory=now)
    finished_at: str = ""
    duration_seconds: float = 0.0
    outcome: str = ""
    downloaded: int = 0
    skipped: int = 0
    missing: list = field(default_factory=list)
    login_attempts: int = 0
    errors: list = field(default_factory=list)
    screenshots: list = field(default_factory=list)

    def row(self):
        """Field order required by the log spec."""
        d = asdict(self)
        order = ["run_id", "trigger", "started_at", "finished_at", "duration_seconds", "month", "outcome",
                 "downloaded", "skipped", "missing", "login_attempts", "errors", "screenshots"]
        return {k: d[k] for k in order}


def append(record, logs_dir):
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    row = record.row()
    with open(logs_dir / "runs.jsonl", "a") as f:
        f.write(json.dumps(row) + "\n")

    csv_path = logs_dir / "runs.csv"
    new_file = not csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        if new_file:
            writer.writeheader()
        writer.writerow({k: " | ".join(v) if isinstance(v, list) else v for k, v in row.items()})


def summary(record):
    lines = [
        f"Run {record.run_id} ({record.trigger}) for {record.month}: {record.outcome.upper()}",
        f"  downloaded {record.downloaded}, skipped {record.skipped}, "
        f"missing {len(record.missing)}, login attempts {record.login_attempts}, "
        f"took {record.duration_seconds}s",
    ]
    if record.missing:
        lines.append("  missing: " + ", ".join(record.missing))
    lines += [f"  error: {e}" for e in record.errors]
    lines += [f"  screenshot: {s}" for s in record.screenshots]
    return "\n".join(lines)
