import json
import threading

import pytest
import yaml
from werkzeug.serving import make_server

from bot.runner import run
from portal import create_app

USER, PASSWORD = "test_user", "test-password"
MONTH = "2026-09"


@pytest.fixture
def portal():
    """Start the fake portal with the given fault switches; returns its URL."""
    servers = []

    def start(**faults):
        app = create_app({"USERNAME": USER, "PASSWORD": PASSWORD, "FAIL_FIRST_LOGIN": False, "SLOW_MODE": 0,
                          "MISSING_REPORT": "", "SHOW_POPUP": False, "SESSION_TIMEOUT": 0, **faults})
        server = make_server("127.0.0.1", 0, app, threaded=True)  # port 0 = any free port
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_port}"

    yield start
    for s in servers:
        s.shutdown()


@pytest.fixture
def bot(tmp_path):
    """Run the bot against a portal URL with output and logs kept in a temp folder."""
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    cfg.update(output_dir=str(tmp_path / "output"), logs_dir=str(tmp_path / "logs"))
    cfg["retries"].update(backoff_seconds=0.1, backoff_max_seconds=0.5)

    def go(url, password=PASSWORD, month=MONTH):
        cfg["portal_url"] = url
        return run(month, "manual", cfg, USER, password)

    go.output = tmp_path / "output" / MONTH
    go.log = lambda: [json.loads(line) for line in (tmp_path / "logs" / "runs.jsonl").read_text().splitlines()]
    return go
