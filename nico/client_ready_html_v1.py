from __future__ import annotations

import html
from typing import Any

from nico.comprehensive_client_ready_projection_v1 import EN_BOUNDARY, ES_BOUNDARY

VERSION = "nico.client-ready-html.v1"


def render_client_html(markdown: str, title: str, *, spanish: bool) -> str:
    blocks: list[str] = []
    list_items: list[str] = []

    def flush() -> None:
        nonlocal list_items
        if list_items:
            blocks.append("<ul>" + "".join(list_items) + "</ul>")
            list_items = []

    for raw in str(markdown or "").splitlines():
        line = raw.strip()
        if not line:
            flush()
        elif line.startswith("<!--"):
            blocks.append(line)
        elif line.startswith("#### "):
            flush(); blocks.append(f"<h4>{html.escape(line[5:])}</h4>")
        elif line.startswith("### "):
            flush(); blocks.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            flush(); blocks.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            flush(); blocks.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("- [ ] "):
            list_items.append(f"<li class='check'>☐ {html.escape(line[6:])}</li>")
        elif line.startswith("- ") or line.startswith("  - "):
            list_items.append(f"<li>{html.escape(line.lstrip()[2:])}</li>")
        elif line.startswith("**") and line.endswith("**"):
            flush(); blocks.append(f"<p class='warning'>{html.escape(line.strip('*'))}</p>")
        else:
            flush(); blocks.append(f"<p>{html.escape(line)}</p>")
    flush()
    language = "es-MX" if spanish else "en"
    badge = ES_BOUNDARY if spanish else EN_BOUNDARY
    return f"""<!doctype html><html lang='{language}'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;background:#050b18;color:#dce8fa;font:15px/1.6 Inter,system-ui,sans-serif}}main{{max-width:1120px;margin:auto;padding:34px 20px 80px}}header{{position:relative;overflow:hidden;padding:42px;border:1px solid #18304f;border-radius:26px;background:linear-gradient(145deg,#071224,#0b1f39)}}header:after{{content:'';position:absolute;width:440px;height:440px;border-radius:50%;right:-180px;top:-260px;background:#0c4a6e55}}header h1{{position:relative;margin:0;color:white;font-size:clamp(30px,5vw,50px);line-height:1.06}}.badge{{position:relative;display:inline-block;margin-top:18px;padding:8px 13px;border:1px solid #f59e0b;border-radius:999px;background:#3b2108;color:#fde68a;font-weight:800}}article{{margin-top:24px;padding:30px;border:1px solid #18304f;border-radius:24px;background:#081426}}h1{{color:white}}h2{{margin-top:40px;padding-top:25px;border-top:1px solid #18304f;color:#55d7f4}}h3{{margin-top:26px;color:#dff8ff}}h4{{margin-top:22px;color:#dff8ff}}p,li{{color:#bdcbe0}}ul{{padding-left:24px}}li{{margin:7px 0}}.check{{list-style:none;margin-left:-20px}}.warning{{padding:15px;border:1px solid #f59e0b;border-radius:14px;background:#3b2108;color:#fde68a;font-weight:800}}</style></head><body><main><header><h1>{html.escape(title)}</h1><span class='badge'>{html.escape(badge)}</span></header><article>{''.join(blocks)}</article></main></body></html>"""


__all__ = ["VERSION", "render_client_html"]
