"""The report catalogue and deterministic sample-file generators."""

import csv
import io
import random
import zipfile
from datetime import datetime

from fpdf import FPDF
from openpyxl import Workbook

# (display name, legacy code, file type, column headers)
CATALOGUE = [
    ("Sales Summary", "SALESSUM", "csv", ["Region", "Units", "Revenue"]),
    ("Inventory Levels", "INVLVL", "xlsx", ["SKU", "On Hand", "Reorder Point"]),
    ("Accounts Receivable Aging", "ARAGING", "pdf", ["Customer", "Days Overdue", "Balance"]),
    ("Customer Returns", "CUSTRET", "csv", ["Order", "Units", "Refund"]),
    ("Vendor Payments", "VENDPAY", "xlsx", ["Vendor", "Invoices", "Paid"]),
    ("Freight Charges", "FRTCHG", "csv", ["Carrier", "Shipments", "Cost"]),
    ("Compliance Certificate", "COMPCERT", "pdf", ["Check", "Items", "Score"]),
]

# The portal offers 24 months of history, Oct 2024 to Sep 2026.
MONTHS = [f"{2024 + (9 + i) // 12}-{(9 + i) % 12 + 1:02d}" for i in range(24)]

LABELS = ["North", "South", "East", "West", "Central", "Acme Ltd", "Globex", "Initech"]
FIXED_DATE = datetime(2026, 1, 1)  # file metadata date, so output never depends on "now"


def slug(name):
    return name.lower().replace(" ", "-")


def listing(month, missing=None):
    """Rows shown on the reports page for one month. `missing` is a slug to hide."""
    return [
        {"name": name, "slug": slug(name), "code": code, "type": ext, "month": month}
        for name, code, ext, _ in CATALOGUE
        if slug(name) != missing
    ]


def find(report_slug):
    return next((r for r in CATALOGUE if slug(r[0]) == report_slug), None)


def rows_for(report_slug, month):
    # A string seed is stable across runs, so the same month always gives the same data.
    rng = random.Random(f"{report_slug}|{month}")
    return [
        [rng.choice(LABELS) + f" {i:02d}", rng.randint(1, 500), round(rng.uniform(100, 99999), 2)]
        for i in range(1, 21)
    ]


def pinned_zip_dates(wb):
    """Save a workbook with fixed zip timestamps (openpyxl stamps 'now', which changes the bytes)."""
    raw, out = io.BytesIO(), io.BytesIO()
    wb.save(raw)
    with zipfile.ZipFile(raw) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            dst.writestr(zipfile.ZipInfo(item.filename, FIXED_DATE.timetuple()[:6]), src.read(item))
    return out.getvalue()


def build_file(report_slug, month):
    """Return (bytes, legacy filename, mimetype) for one report."""
    name, code, ext, headers = find(report_slug)
    rows = rows_for(report_slug, month)
    filename = f"RPT_{code}_{month.replace('-', '')}.{ext}"  # ugly vendor name; the bot renames it

    if ext == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        writer.writerows(rows)
        return buf.getvalue().encode(), filename, "text/csv"

    if ext == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = month
        ws.append(headers)
        for row in rows:
            ws.append(row)
        wb.properties.created = wb.properties.modified = FIXED_DATE
        return pinned_zip_dates(wb), filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    pdf = FPDF()
    pdf.set_creation_date(FIXED_DATE)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(text=f"{name} - {month}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    with pdf.table() as table:
        for row in [headers, *rows]:
            table.row([str(c) for c in row])
    return bytes(pdf.output()), filename, "application/pdf"
