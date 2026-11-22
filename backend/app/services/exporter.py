"""CSV and PDF export of database query results.

CSV uses the standard library ``csv`` module (UTF-8 with BOM so Excel opens
accented characters correctly).  PDF uses ReportLab's table layout with text
wrapping, a title, generation timestamp and row count.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value == value.to_integral() else str(value)
    return str(value)


def _csv_safe(text: str) -> str:
    """Neutralise spreadsheet formula injection (cells starting with = + - @)."""
    if text and text[0] in "=+-@" and not re.fullmatch(r"-?\d+(\.\d+)?", text):
        return "'" + text
    return text


def to_csv(columns: list[str], rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_csv_safe(fmt(row.get(c))) for c in columns])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def to_pdf(title: str, columns: list[str], rows: list[dict], subtitle: str = "") -> bytes:
    buf = io.BytesIO()
    page = landscape(A4)
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm, title=title,
                            author="Intelligent Route Planning System")
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=7.5, leading=9)
    head = ParagraphStyle("head", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
    story = [Paragraph(escape(title), styles["Title"])]
    meta = f"Generated {datetime.now():%Y-%m-%d %H:%M} &middot; {len(rows)} row(s)"
    if subtitle:
        meta = escape(subtitle) + " &middot; " + meta
    story += [Paragraph(meta, styles["Normal"]), Spacer(1, 6 * mm)]

    data = [[Paragraph(escape(c.replace("_", " ")), head) for c in columns]]
    for row in rows:
        data.append([Paragraph(escape(fmt(row.get(c))), cell) for c in columns])
    if not rows:
        data.append([Paragraph("No rows match the current filters.", cell)] + [""] * (len(columns) - 1))

    width = page[0] - 24 * mm
    table = Table(data, colWidths=[width / max(1, len(columns))] * len(columns), repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef3f8")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8c4d0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)
    doc.build(story)
    return buf.getvalue()
