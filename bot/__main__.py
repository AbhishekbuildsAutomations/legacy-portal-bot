"""Command line: python -m bot --month 2026-09 [--headed] [--trigger manual|scheduled] [--video DIR]"""

import argparse
import logging
import os
import sys
from datetime import date, datetime

import yaml
from dotenv import load_dotenv

from .runlog import EXIT_CODES
from .runner import run


def month_arg(value):
    datetime.strptime(value, "%Y-%m")  # raises ValueError -> argparse shows a clean error
    return value


def previous_month():
    first = date.today().replace(day=1)
    return f"{first.year - (first.month == 1)}-{(first.month - 2) % 12 + 1:02d}"


def main():
    parser = argparse.ArgumentParser(prog="python -m bot", description="Download the month's reports from the legacy portal.")
    parser.add_argument("--month", type=month_arg, default=previous_month(), help="YYYY-MM (default: last month)")
    parser.add_argument("--headed", action="store_true", help="show the browser while it runs")
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="manual")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--video", metavar="DIR", help="record a video of the run into DIR")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    load_dotenv()
    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    record = run(args.month, args.trigger, cfg, os.environ.get("PORTAL_USERNAME"), os.environ.get("PORTAL_PASSWORD"),
                 headed=args.headed, video_dir=args.video)
    sys.exit(EXIT_CODES[record.outcome])


main()
