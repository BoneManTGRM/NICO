from __future__ import annotations

from functools import wraps
from typing import Any, Callable

VERSION = "nico.accurate_green_pdf_polish.v2"
_STYLES_MARKER = "_nico_accurate_green_styles_v2"
_TABLE_MARKER = "_nico_accurate_green_table_v2"


def install_accurate_green_pdf_polish_v2() -> dict[str, Any]:
    from nico import express_pdf_score_assurance_v1 as target

    styles_current: Callable[[], dict[str, Any]] = target._styles
    if not getattr(styles_current, _STYLES_MARKER, False):
        @wraps(styles_current)
        def styles() -> dict[str, Any]:
            from reportlab.lib import colors

            output = styles_current()
            title = output.get("title")
            if title is not None:
                title.fontSize = 20
                title.leading = 23
                title.textColor = colors.HexColor("#0f172a")
                title.spaceAfter = 12
            heading = output.get("h2")
            if heading is not None:
                heading.fontSize = 10.8
                heading.leading = 13.2
                heading.textColor = colors.HexColor("#0369a1")
                heading.spaceBefore = 8
                heading.spaceAfter = 4
            body = output.get("body")
            if body is not None:
                body.fontSize = 8.5
                body.leading = 10.8
                body.textColor = colors.HexColor("#334155")
                body.spaceAfter = 5
            small = output.get("small")
            if small is not None:
                small.fontSize = 7.6
                small.leading = 9.6
                small.textColor = colors.HexColor("#475569")
                small.spaceAfter = 3.5
            label = output.get("label")
            if label is not None:
                label.fontSize = 7.3
                label.leading = 9.1
                label.textColor = colors.HexColor("#0f4c6e")
            callout = output.get("callout")
            if callout is not None:
                callout.fontSize = 8.4
                callout.leading = 10.8
                callout.textColor = colors.HexColor("#075985")
                callout.backColor = colors.HexColor("#ecfeff")
                callout.borderColor = colors.HexColor("#22d3ee")
                callout.borderWidth = 0.8
                callout.borderPadding = 8
                callout.spaceAfter = 9
            return output

        setattr(styles, _STYLES_MARKER, True)
        setattr(styles, "_nico_previous", styles_current)
        target._styles = styles

    table_current: Callable[..., Any] = target._table
    if not getattr(table_current, _TABLE_MARKER, False):
        @wraps(table_current)
        def table(rows: list[list[Any]], widths: list[float], *, repeat_rows: int = 1):
            from reportlab.lib import colors
            from reportlab.platypus import TableStyle

            widget = table_current(rows, widths, repeat_rows=repeat_rows)
            commands: list[tuple[Any, ...]] = [
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#0891b2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5.5),
            ]
            if repeat_rows:
                commands.extend(
                    [
                        ("BACKGROUND", (0, 0), (-1, repeat_rows - 1), colors.HexColor("#075985")),
                        ("TEXTCOLOR", (0, 0), (-1, repeat_rows - 1), colors.white),
                    ]
                )
            for row in range(repeat_rows, len(rows)):
                commands.append(
                    (
                        "BACKGROUND",
                        (0, row),
                        (-1, row),
                        colors.HexColor("#f8fafc" if (row - repeat_rows) % 2 == 0 else "#eef6fb"),
                    )
                )
            widget.setStyle(TableStyle(commands))
            return widget

        setattr(table, _TABLE_MARKER, True)
        setattr(table, "_nico_previous", table_current)
        target._table = table

    return {
        "status": "installed",
        "version": VERSION,
        "typography_polished": True,
        "navy_table_headers": True,
        "alternating_rows": True,
        "cyan_evidence_callouts": True,
        "content_semantics_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_accurate_green_pdf_polish_v2"]
