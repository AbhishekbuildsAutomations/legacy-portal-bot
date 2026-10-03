"""A fake 'legacy vendor portal' for the bot to automate. Local use only."""

import os
import random
import secrets
import time
from io import BytesIO

from dotenv import load_dotenv
from flask import Flask, abort, redirect, render_template, request, send_file, session, url_for

from . import reports

PAGE_SIZE = 5  # 7 reports per month -> 2 pages, so the bot has to paginate


def read_settings():
    """Fault switches and demo credentials, read from the environment (and .env)."""
    load_dotenv()
    env = os.environ.get
    return {
        "USERNAME": env("PORTAL_USERNAME", "demo_user"),
        "PASSWORD": env("PORTAL_PASSWORD", "change-me-local-only"),
        "FAIL_FIRST_LOGIN": env("FAIL_FIRST_LOGIN", "") not in ("", "0", "false"),
        "SLOW_MODE": float(env("SLOW_MODE") or 0),  # max extra seconds per page load
        "MISSING_REPORT": env("MISSING_REPORT", ""),  # "<report-slug>:<YYYY-MM>"
        "SHOW_POPUP": env("SHOW_POPUP", "") not in ("", "0", "false"),
        "SESSION_TIMEOUT": int(env("SESSION_TIMEOUT") or 0),  # requests per login, 0 = never
    }


def create_app(overrides=None):
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(16)
    cfg = {**read_settings(), **(overrides or {})}
    state = {"login_posts": 0}  # counts login attempts since the server started

    def missing_slug(month):
        slug, _, m = cfg["MISSING_REPORT"].partition(":")
        return slug if m == month else None

    @app.before_request
    def legacy_behaviour():
        if cfg["SLOW_MODE"]:
            time.sleep(random.uniform(0, cfg["SLOW_MODE"]))
        if request.endpoint in ("login", "logout", "static") or "user" not in session:
            return None
        session["requests"] = session.get("requests", 0) + 1
        if cfg["SESSION_TIMEOUT"] and session["requests"] > cfg["SESSION_TIMEOUT"]:
            session.clear()
            return redirect(url_for("login", expired=1))
        return None

    @app.route("/")
    def home():
        return redirect(url_for("reports_page"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_template("login.html", expired=request.args.get("expired"))
        state["login_posts"] += 1
        if cfg["FAIL_FIRST_LOGIN"] and state["login_posts"] == 1:
            return render_template("busy.html"), 503
        if (request.form.get("username") == cfg["USERNAME"]
                and secrets.compare_digest(request.form.get("password", ""), cfg["PASSWORD"])):
            session.clear()
            session["user"] = cfg["USERNAME"]
            session["show_notice"] = cfg["SHOW_POPUP"]
            return redirect(url_for("reports_page"))
        return render_template("login.html", error="Invalid username or password."), 401

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/reports")
    def reports_page():
        if "user" not in session:
            return redirect(url_for("login"))
        month = request.args.get("month", reports.MONTHS[-1])
        if month not in reports.MONTHS:
            abort(404)
        rows = reports.listing(month, missing_slug(month))
        pages = max(1, -(-len(rows) // PAGE_SIZE))  # ceiling division
        page = min(max(request.args.get("page", 1, type=int), 1), pages)
        return render_template(
            "reports.html",
            user=session["user"],
            months=reports.MONTHS,
            month=month,
            rows=rows[(page - 1) * PAGE_SIZE: page * PAGE_SIZE],
            page=page,
            pages=pages,
            show_notice=session.pop("show_notice", False),
        )

    @app.route("/reports/download/<slug>")
    def download(slug):
        if "user" not in session:
            return redirect(url_for("login"))
        month = request.args.get("month", "")
        if month not in reports.MONTHS or not reports.find(slug) or slug == missing_slug(month):
            abort(404)
        data, filename, mimetype = reports.build_file(slug, month)
        return send_file(BytesIO(data), mimetype=mimetype, as_attachment=True, download_name=filename)

    return app
