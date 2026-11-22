"""Small helpers shared by the API blueprints."""
from __future__ import annotations

import re
from datetime import datetime

from flask import Response, jsonify, request

from ..errors import ApiError
from ..services import exporter


def created(payload: dict):
    return jsonify(payload), 201


def not_found(what: str = "Record"):
    raise ApiError(404, f"{what} not found.")


def export_response(base_name: str, title: str, columns: list[str], rows: list[dict], subtitle: str = ""):
    """Return rows as a CSV or PDF download depending on ?format=."""
    fmt = (request.args.get("format") or "csv").lower()
    safe = re.sub(r"[^a-z0-9_\-]+", "-", base_name.lower()).strip("-") or "export"
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    if fmt == "csv":
        body, mime, ext = exporter.to_csv(columns, rows), "text/csv; charset=utf-8", "csv"
    elif fmt == "pdf":
        try:
            body = exporter.to_pdf(title, columns, rows, subtitle)
        except Exception as exc:  # ReportLab layout failures should not crash the app
            raise ApiError(500, "The PDF export could not be generated.") from exc
        mime, ext = "application/pdf", "pdf"
    else:
        raise ApiError(400, "Export format must be 'csv' or 'pdf'.")
    return Response(body, mimetype=mime, headers={
        "Content-Disposition": f'attachment; filename="{safe}-{stamp}.{ext}"',
        "Cache-Control": "no-store",
    })
