#!/usr/bin/env python3
"""Render a completed political analysis markdown report into HTML and PDF.

This module now delegates to:
- render_html_report.py for modern interactive HTML
- render_pdf_report.py for structured print-friendly PDF

The original rendering code is preserved as fallback.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Try to import new modules
try:
    from render_html_report import render_html
    HAS_NEW_HTML = True
except ImportError:
    HAS_NEW_HTML = False

try:
    from render_pdf_report import render_pdf
    HAS_NEW_PDF = True
except ImportError:
    HAS_NEW_PDF = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render markdown analysis into polished HTML and PDF deliverables."
    )
    parser.add_argument("--analysis-md", required=True, help="Input markdown analysis path.")
    parser.add_argument("--output-dir", required=True, help="Output directory for deliverables.")
    parser.add_argument("--base-name", default="policy-brief", help="Output file base name.")
    parser.add_argument("--title", help="Optional report title override.")
    parser.add_argument(
        "--pdf-engine",
        default="auto",
        choices=["auto", "weasyprint", "browser", "reportlab"],
        help="PDF engine preference order.",
    )
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF output generation.")
    parser.add_argument(
        "--use-legacy",
        action="store_true",
        help="Use legacy rendering instead of new modules.",
    )
    parser.add_argument(
        "--html-theme",
        default="auto",
        choices=["light", "dark", "auto"],
        help="Default HTML theme.",
    )
    return parser.parse_args()


def is_table_separator(line: str) -> bool:
    if "|" not in line:
        return False
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def parse_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_block_start(lines: list[str], idx: int) -> bool:
    line = lines[idx].rstrip()
    if line.startswith("```"):
        return True
    if re.match(r"^#{1,6}\s+", line):
        return True
    if re.match(r"^[-*]\s+", line):
        return True
    if re.match(r"^\d+\.\s+", line):
        return True
    if "|" in line and idx + 1 < len(lines) and is_table_separator(lines[idx + 1]):
        return True
    return False


def parse_markdown_blocks(markdown_text: str) -> list[dict[str, Any]]:
    lines = markdown_text.splitlines()
    blocks: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        if line.startswith("```"):
            i += 1
            code_lines: list[str] = []
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i].rstrip("\n"))
                i += 1
            if i < len(lines):
                i += 1
            blocks.append({"type": "code", "text": "\n".join(code_lines)})
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            blocks.append({"type": "heading", "level": level, "text": text})
            i += 1
            continue

        if "|" in line and i + 1 < len(lines) and is_table_separator(lines[i + 1]):
            table_rows: list[list[str]] = [parse_table_row(line)]
            i += 2
            while i < len(lines):
                maybe = lines[i].rstrip()
                if not maybe.strip() or "|" not in maybe:
                    break
                table_rows.append(parse_table_row(maybe))
                i += 1
            blocks.append({"type": "table", "rows": table_rows})
            continue

        if re.match(r"^[-*]\s+", line):
            items: list[str] = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].rstrip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].rstrip()).strip())
                i += 1
            blocks.append({"type": "list", "ordered": False, "items": items})
            continue

        if re.match(r"^\d+\.\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].rstrip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].rstrip()).strip())
                i += 1
            blocks.append({"type": "list", "ordered": True, "items": items})
            continue

        para_lines = [stripped]
        i += 1
        while i < len(lines):
            if not lines[i].strip():
                break
            if is_block_start(lines, i):
                break
            para_lines.append(lines[i].strip())
            i += 1
        blocks.append({"type": "paragraph", "text": " ".join(para_lines).strip()})
    return blocks


def render_inline_html(text: str) -> str:
    def render_segment(segment: str) -> str:
        escaped = html.escape(segment)
        escaped = re.sub(
            r"\[([FfIiSs])\]",
            lambda m: (
                f'<span class="e-tag tag-{m.group(1).lower()}" '
                f'aria-label="evidence {m.group(1).upper()}">{m.group(1).upper()}</span>'
            ),
            escaped,
        )
        escaped = re.sub(
            r"\[confidence=(high|medium|low)\]",
            lambda m: f'<span class="c-tag c-{m.group(1).lower()}">{m.group(1).upper()}</span>',
            escaped,
            flags=re.IGNORECASE,
        )
        return escaped

    parts = re.split(r"(`[^`]+`)", text)
    rendered: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.startswith("`") and part.endswith("`") and len(part) >= 2:
            rendered.append(f"<code>{html.escape(part[1:-1])}</code>")
            continue
        rendered.append(render_segment(part))
    return "".join(rendered)


def normalize_table_rows(rows: list[list[str]]) -> list[list[str]]:
    max_cols = max((len(row) for row in rows), default=0)
    if max_cols == 0:
        return rows
    return [row + [""] * (max_cols - len(row)) for row in rows]


def same_heading(a: str, b: str) -> bool:
    squeeze = lambda t: re.sub(r"\s+", "", t or "")
    return squeeze(a) == squeeze(b)


def collect_outline_metrics(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    text_fragments: list[str] = []
    h2_count = 0
    table_count = 0

    for block in blocks:
        kind = block.get("type")
        if kind == "heading" and int(block.get("level", 0)) == 2:
            h2_count += 1
        if kind == "table":
            table_count += 1
            for row in block.get("rows", []):
                text_fragments.extend(str(cell) for cell in row)
        if kind == "paragraph":
            text_fragments.append(str(block.get("text", "")))
        if kind == "list":
            text_fragments.extend(str(item) for item in block.get("items", []))

    merged = "\n".join(text_fragments)
    tags = re.findall(r"\[([FfIiSs])\]", merged)
    confidence = re.findall(r"\[confidence=(high|medium|low)\]", merged, flags=re.IGNORECASE)
    tier = re.findall(r"\bT([0-3])\b", merged)

    tag_count = {"F": 0, "I": 0, "S": 0}
    for tag in tags:
        tag_count[tag.upper()] += 1

    confidence_count = {"high": 0, "medium": 0, "low": 0}
    for value in confidence:
        confidence_count[value.lower()] += 1

    tier_count = {"T0": 0, "T1": 0, "T2": 0, "T3": 0}
    for value in tier:
        key = f"T{value}"
        if key in tier_count:
            tier_count[key] += 1

    return {
        "sections": h2_count,
        "tables": table_count,
        "tag_count": tag_count,
        "confidence_count": confidence_count,
        "tier_count": tier_count,
    }


def unique_heading_id(text: str, used_ids: set[str], fallback_index: int) -> str:
    base = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip(), flags=re.UNICODE)
    base = re.sub(r"-{2,}", "-", base).strip("-").lower()
    if not base:
        base = f"section-{fallback_index}"
    candidate = base
    seq = 2
    while candidate in used_ids:
        candidate = f"{base}-{seq}"
        seq += 1
    used_ids.add(candidate)
    return candidate


def render_html_body(
    blocks: list[dict[str, Any]], title_for_dedup: str | None = None
) -> tuple[str, list[dict[str, str]]]:
    output: list[str] = []
    removed_title_h1 = False
    section_open = False
    section_index = 0
    used_ids: set[str] = set()
    sections: list[dict[str, str]] = []

    def ensure_section_open() -> None:
        nonlocal section_open, section_index
        if section_open:
            return
        section_index += 1
        output.append('<section class="panel section-card reveal" aria-label="摘要导读">')
        section_open = True

    for block in blocks:
        kind = block["type"]
        if kind == "heading":
            level = min(max(int(block["level"]), 1), 6)
            if (
                level == 1
                and title_for_dedup
                and not removed_title_h1
                and same_heading(block["text"], title_for_dedup)
            ):
                removed_title_h1 = True
                continue
            if level == 2:
                if section_open:
                    output.append("</section>")
                section_index += 1
                section_open = True
                plain_title = strip_inline_markers(block["text"])
                heading_id = unique_heading_id(plain_title, used_ids, section_index)
                sections.append({"id": heading_id, "title": plain_title})
                output.append(f'<section class="panel section-card reveal" aria-labelledby="{heading_id}">')
                output.append(f'<h2 id="{heading_id}">{render_inline_html(block["text"])}</h2>')
                continue
            ensure_section_open()
            output.append(f"<h{level}>{render_inline_html(block['text'])}</h{level}>")
            continue
        if kind == "paragraph":
            ensure_section_open()
            output.append(f"<p>{render_inline_html(block['text'])}</p>")
            continue
        if kind == "code":
            ensure_section_open()
            output.append("<pre><code>")
            output.append(html.escape(block["text"]))
            output.append("</code></pre>")
            continue
        if kind == "list":
            ensure_section_open()
            tag = "ol" if block.get("ordered") else "ul"
            output.append(f"<{tag}>")
            for item in block.get("items", []):
                output.append(f"<li>{render_inline_html(item)}</li>")
            output.append(f"</{tag}>")
            continue
        if kind == "table":
            ensure_section_open()
            rows = normalize_table_rows(block.get("rows", []))
            if not rows:
                continue
            output.append('<div class="table-wrap">')
            output.append("<table>")
            output.append("<thead><tr>")
            for cell in rows[0]:
                output.append(f"<th>{render_inline_html(cell)}</th>")
            output.append("</tr></thead>")
            output.append("<tbody>")
            for row in rows[1:]:
                output.append("<tr>")
                for cell in row:
                    output.append(f"<td>{render_inline_html(cell)}</td>")
                output.append("</tr>")
            output.append("</tbody></table></div>")
            continue
    if section_open:
        output.append("</section>")
    return "\n".join(output).strip(), sections


def build_html_document(
    title: str,
    body_html: str,
    sections: list[dict[str, str]],
    metrics: dict[str, Any],
) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    safe_title = html.escape(title)
    outline_html = "\n".join(
        f'<a href="#{html.escape(item["id"])}">{html.escape(item["title"])}</a>'
        for item in sections
    )
    if not outline_html:
        outline_html = '<span class="outline-empty">无可导航章节</span>'

    f_count = int(metrics["tag_count"]["F"])
    i_count = int(metrics["tag_count"]["I"])
    s_count = int(metrics["tag_count"]["S"])
    high_count = int(metrics["confidence_count"]["high"])
    medium_count = int(metrics["confidence_count"]["medium"])
    low_count = int(metrics["confidence_count"]["low"])
    section_count = int(metrics["sections"])
    table_count = int(metrics["tables"])
    tier_t0 = int(metrics["tier_count"]["T0"])
    tier_t1 = int(metrics["tier_count"]["T1"])
    tier_t2 = int(metrics["tier_count"]["T2"])
    tier_t3 = int(metrics["tier_count"]["T3"])

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#103a52">
  <title>{safe_title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;800&family=Noto+Serif+SC:wght@600;700;900&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #f5f1e8;
      --paper: #fffdf7;
      --ink: #17262f;
      --muted: #4f6471;
      --line: #dacfbf;
      --brand: #103a52;
      --brand-soft: #d5e5ef;
      --brand-2: #1e6a75;
      --accent: #bc6e2a;
      --ok: #16663b;
      --risk: #8f2626;
      --warn: #8f5916;
      --radius-lg: 20px;
      --radius-md: 12px;
      --radius-sm: 8px;
      --safe-top: env(safe-area-inset-top, 0px);
      --safe-right: env(safe-area-inset-right, 0px);
      --safe-bottom: env(safe-area-inset-bottom, 0px);
      --safe-left: env(safe-area-inset-left, 0px);
      --max: 1220px;
    }}
    * {{ box-sizing: border-box; }}
    html {{
      color-scheme: light;
      scroll-behavior: smooth;
      -webkit-tap-highlight-color: rgba(16, 58, 82, 0.2);
    }}
    body {{
      margin: 0;
      font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(1200px 560px at 85% -5%, #d9ebf3 0%, rgba(217, 235, 243, 0) 58%),
        radial-gradient(980px 530px at -10% 16%, #f2ddc5 0%, rgba(242, 221, 197, 0) 56%),
        var(--bg);
      color: var(--ink);
      line-height: 1.68;
      -webkit-font-smoothing: antialiased;
      text-rendering: optimizeLegibility;
      overflow-x: hidden;
      padding-bottom: calc(18px + var(--safe-bottom));
    }}
    .skip-link {{
      position: absolute;
      left: 10px;
      top: -46px;
      background: #fff;
      color: var(--brand);
      border: 2px solid var(--brand);
      border-radius: var(--radius-sm);
      padding: 9px 12px;
      font-weight: 700;
      text-decoration: none;
      z-index: 999;
      transition: top 0.2s ease;
    }}
    .skip-link:focus-visible {{
      top: calc(8px + var(--safe-top));
    }}
    .top {{
      padding: calc(24px + var(--safe-top)) calc(18px + var(--safe-right)) 20px calc(18px + var(--safe-left));
    }}
    .hero {{
      max-width: var(--max);
      margin: 0 auto;
      background:
        linear-gradient(135deg, rgba(16, 58, 82, 0.97), rgba(30, 106, 117, 0.93)),
        url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120' viewBox='0 0 120 120'%3E%3Cg fill='none' stroke='rgba(255,255,255,.08)' stroke-width='1'%3E%3Cpath d='M0 60h120M60 0v120'/%3E%3C/g%3E%3C/svg%3E");
      border-radius: var(--radius-lg);
      box-shadow: 0 18px 44px rgba(23, 38, 47, 0.14);
      color: #f4fcff;
      padding: 30px 26px 24px;
      position: relative;
      overflow: hidden;
    }}
    .hero::after {{
      content: "";
      position: absolute;
      width: 320px;
      height: 320px;
      right: -90px;
      top: -130px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(255, 221, 189, 0.28), rgba(255, 221, 189, 0));
      pointer-events: none;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 6px 12px;
      background: rgba(255, 255, 255, 0.14);
      border: 1px solid rgba(255, 255, 255, 0.22);
      margin-bottom: 12px;
      font-size: 0.82rem;
      font-weight: 700;
      letter-spacing: 0.01em;
    }}
    header h1 {{
      margin: 0;
      font-family: "Noto Serif SC", "Songti SC", serif;
      font-size: clamp(1.7rem, 3.1vw, 2.7rem);
      line-height: 1.25;
      text-wrap: balance;
      max-width: 21ch;
    }}
    .meta {{
      margin-top: 14px;
      display: flex;
      flex-wrap: wrap;
      gap: 10px 14px;
      color: rgba(244, 252, 255, 0.92);
      font-size: 0.93rem;
      font-variant-numeric: tabular-nums;
    }}
    .meta span {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 9px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.14);
    }}
    .shell {{
      max-width: var(--max);
      margin: 0 auto;
      padding: 0 calc(18px + var(--safe-right)) 0 calc(18px + var(--safe-left));
      display: grid;
      grid-template-columns: 310px minmax(0, 1fr);
      gap: 16px;
    }}
    .panel {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: var(--radius-lg);
      box-shadow: 0 8px 28px rgba(22, 41, 54, 0.08);
    }}
    .sticky {{
      position: sticky;
      top: 12px;
      align-self: start;
      padding: 14px;
    }}
    main {{
      min-width: 0;
      display: grid;
      gap: 14px;
      align-self: start;
    }}
    .kpi-grid {{
      display: grid;
      gap: 10px;
      margin-bottom: 12px;
    }}
    .kpi {{
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      background: linear-gradient(160deg, #fff, #f7f1e4);
      padding: 11px 12px;
    }}
    .kpi strong {{
      font-family: "Space Grotesk", "Noto Sans SC", sans-serif;
      font-size: 1.35rem;
      font-variant-numeric: tabular-nums;
      color: var(--brand);
      display: block;
      line-height: 1.12;
    }}
    .kpi span {{
      font-size: 0.84rem;
      color: var(--muted);
    }}
    .legend {{
      border-top: 1px dashed #c8bda9;
      padding-top: 10px;
      display: grid;
      gap: 8px;
      font-size: 0.85rem;
      color: #445865;
      margin-bottom: 12px;
    }}
    .legend b {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 22px;
      height: 22px;
      border-radius: 999px;
      color: #fff;
      margin-right: 6px;
      font-size: 0.72rem;
      vertical-align: middle;
    }}
    .f {{ background: var(--ok); }}
    .i {{ background: var(--brand); }}
    .s {{ background: var(--risk); }}
    .outline {{
      border-top: 1px dashed #c8bda9;
      padding-top: 10px;
      display: grid;
      gap: 7px;
    }}
    .outline-title {{
      font-size: 0.85rem;
      font-weight: 800;
      color: #3e5361;
    }}
    .outline a {{
      font-size: 0.9rem;
      color: #13405f;
      text-decoration: none;
      padding: 8px 10px;
      border-radius: var(--radius-sm);
      border: 1px solid transparent;
      background: #f4f9fc;
      transition: transform 0.18s ease, border-color 0.18s ease, background-color 0.18s ease;
    }}
    .outline a:hover {{
      background: #e7f1f7;
      border-color: #acc1cd;
      transform: translateY(-1px);
    }}
    .outline a.active {{
      background: #dceaf3;
      border-color: #7fa0b2;
      color: #11344b;
    }}
    .outline-empty {{
      font-size: 0.85rem;
      color: var(--muted);
    }}
    section.section-card {{
      padding: 18px;
      content-visibility: auto;
      contain-intrinsic-size: 640px;
    }}
    h1, h2, h3, h4, h5, h6 {{
      line-height: 1.35;
      margin: 1.25em 0 0.45em;
      color: #17384f;
      text-wrap: balance;
      scroll-margin-top: 20px;
    }}
    h2 {{
      padding-left: 10px;
      border-left: 4px solid var(--brand);
      font-size: clamp(1.05rem, 2.1vw, 1.4rem);
      margin-top: 0;
    }}
    h3 {{
      font-size: 1rem;
      color: #1f4f73;
    }}
    p {{
      margin: 0.5em 0 0.9em;
      color: #20313d;
      overflow-wrap: break-word;
    }}
    ul, ol {{
      margin: 0.45em 0 0.95em 1.2em;
      padding: 0;
    }}
    li {{ margin: 0.3em 0; }}
    li:has(.e-tag), p:has(.e-tag) {{
      background: linear-gradient(90deg, rgba(16, 58, 82, 0.06), rgba(16, 58, 82, 0));
      border-left: 3px solid rgba(16, 58, 82, 0.38);
      padding-left: 8px;
      border-radius: 4px;
    }}
    code {{
      background: #eef4f9;
      border: 1px solid #d8e7f3;
      border-radius: 5px;
      padding: 1px 6px;
      font-family: "SFMono-Regular", "Menlo", "Monaco", monospace;
      font-size: 0.92em;
    }}
    .e-tag {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 24px;
      height: 24px;
      margin: 0 4px 0 1px;
      padding: 0 8px;
      border-radius: 999px;
      color: #fff;
      font-family: "Space Grotesk", "Noto Sans SC", sans-serif;
      font-size: 0.78rem;
      font-weight: 800;
      letter-spacing: 0.02em;
      vertical-align: middle;
    }}
    .tag-f {{ background: var(--ok); }}
    .tag-i {{ background: var(--brand); }}
    .tag-s {{ background: var(--risk); }}
    .c-tag {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      padding: 2px 8px;
      margin-left: 4px;
      font-size: 0.72rem;
      font-weight: 800;
      letter-spacing: 0.02em;
      color: #fff;
      vertical-align: middle;
    }}
    .c-high {{ background: var(--ok); }}
    .c-medium {{ background: var(--warn); }}
    .c-low {{ background: var(--risk); }}
    pre {{
      overflow-x: auto;
      padding: 14px;
      border-radius: 10px;
      border: 1px solid #d7e4ee;
      background: #f6fbff;
      line-height: 1.55;
    }}
    pre code {{
      border: none;
      background: transparent;
      padding: 0;
    }}
    .table-wrap {{
      overflow-x: auto;
      margin: 0.95em 0 1.15em;
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      background: #fff;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 700px;
      font-size: 0.95rem;
    }}
    th, td {{
      border-bottom: 1px solid #e7dfcf;
      padding: 10px 12px;
      text-align: left;
      vertical-align: top;
      min-width: 0;
      word-break: break-word;
    }}
    th {{
      background: #eff4f8;
      color: #14384e;
      font-weight: 700;
      position: sticky;
      top: 0;
      z-index: 1;
    }}
    tr:last-child td {{ border-bottom: none; }}
    a {{
      color: #0a4f7b;
      text-underline-offset: 2px;
      touch-action: manipulation;
      -webkit-tap-highlight-color: rgba(10, 79, 123, 0.12);
    }}
    a:hover {{ color: #093b5b; }}
    a:focus-visible {{
      outline: 3px solid #f1a855;
      outline-offset: 2px;
      border-radius: 4px;
    }}
    .reveal {{
      opacity: 0;
      transform: translateY(12px);
      transition: opacity 0.46s ease, transform 0.46s ease;
    }}
    .reveal.visible {{
      opacity: 1;
      transform: translateY(0);
    }}
    footer {{
      max-width: var(--max);
      margin: 12px auto 0;
      padding: 0 calc(18px + var(--safe-right)) 12px calc(18px + var(--safe-left));
      color: #60707a;
      font-size: 0.83rem;
      font-variant-numeric: tabular-nums;
    }}
    .footer-inner {{
      padding: 10px 14px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.7);
    }}
    @media (max-width: 1020px) {{
      .shell {{
        grid-template-columns: 1fr;
      }}
      .sticky {{ position: static; }}
      table {{ min-width: 560px; }}
    }}
    @media (max-width: 720px) {{
      .top {{
        padding: calc(16px + var(--safe-top)) calc(10px + var(--safe-right)) 14px calc(10px + var(--safe-left));
      }}
      .shell {{
        padding: 0 calc(10px + var(--safe-right)) 0 calc(10px + var(--safe-left));
      }}
      .hero {{
        border-radius: 14px;
        padding: 22px 15px 18px;
      }}
      section.section-card {{
        padding: 14px;
      }}
      .meta {{
        font-size: 0.86rem;
      }}
      h2 {{
        font-size: 1.03rem;
      }}
      table {{
        font-size: 0.86rem;
      }}
      footer {{
        padding: 0 calc(10px + var(--safe-right)) 10px calc(10px + var(--safe-left));
      }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      html {{ scroll-behavior: auto; }}
      * {{
        animation: none !important;
        transition: none !important;
      }}
    }}
    @media print {{
      body {{
        background: #fff;
        padding-bottom: 0;
      }}
      .top {{
        padding: 0;
      }}
      .hero {{
        background: #fff;
        color: #1b2d39;
        box-shadow: none;
        border: 1px solid #ced7de;
      }}
      .hero::after {{
        display: none;
      }}
      .shell {{
        grid-template-columns: 1fr;
        gap: 10px;
        padding: 0;
        max-width: none;
      }}
      .sticky {{
        position: static;
        page-break-inside: avoid;
      }}
      .skip-link {{
        display: none;
      }}
      .outline a {{
        color: inherit;
        text-decoration: none;
        background: #fff;
      }}
      .panel, .footer-inner {{
        box-shadow: none;
      }}
      .reveal {{
        opacity: 1;
        transform: none;
      }}
    }}
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">跳转到正文</a>
  <div class="top">
    <header class="hero reveal">
      <span class="eyebrow">政策解读可交付简报</span>
      <h1>{safe_title}</h1>
      <p class="meta">
        <span>生成时间: {generated_at}</span>
        <span>章节: {section_count}</span>
        <span>表格: {table_count}</span>
      </p>
    </header>
  </div>
  <div class="shell">
    <aside class="panel sticky reveal" aria-label="摘要导航">
      <div class="kpi-grid">
        <div class="kpi"><strong>{f_count}</strong><span>事实标记 F</span></div>
        <div class="kpi"><strong>{i_count}</strong><span>推断标记 I</span></div>
        <div class="kpi"><strong>{s_count}</strong><span>情景标记 S</span></div>
        <div class="kpi"><strong>{high_count}/{medium_count}/{low_count}</strong><span>置信度 高/中/低</span></div>
        <div class="kpi"><strong>{tier_t0}/{tier_t1}/{tier_t2}/{tier_t3}</strong><span>信源层级 T0/T1/T2/T3</span></div>
      </div>
      <div class="legend">
        <div><b class="f">F</b>事实（可核验）</div>
        <div><b class="i">I</b>推断（多证据归纳）</div>
        <div><b class="s">S</b>情景（未来判断）</div>
      </div>
      <nav class="outline" aria-label="章节导航">
        <span class="outline-title">全文导航（默认全部展开）</span>
        {outline_html}
      </nav>
    </aside>
    <main id="main-content" tabindex="-1">
      {body_html}
    </main>
  </div>
  <footer>
    <div class="footer-inner">Political interpretation brief package (HTML + PDF). 所有解读模块均默认展开展示，避免漏读。</div>
  </footer>
  <script>
    (() => {{
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const revealEls = Array.from(document.querySelectorAll(".reveal"));
      if (!reduceMotion && "IntersectionObserver" in window) {{
        const observer = new IntersectionObserver((entries) => {{
          entries.forEach((entry) => {{
            if (entry.isIntersecting) {{
              entry.target.classList.add("visible");
              observer.unobserve(entry.target);
            }}
          }});
        }}, {{ threshold: 0.06 }});
        revealEls.forEach((el, idx) => {{
          el.style.transitionDelay = `${{Math.min(idx * 40, 260)}}ms`;
          observer.observe(el);
        }});
      }} else {{
        revealEls.forEach((el) => el.classList.add("visible"));
      }}

      const links = Array.from(document.querySelectorAll(".outline a[href^='#']"));
      const sections = links
        .map((link) => {{
          const id = link.getAttribute("href").slice(1);
          const el = document.getElementById(id);
          return el ? {{ link, el }} : null;
        }})
        .filter(Boolean);
      if (!sections.length || !("IntersectionObserver" in window)) return;
      const highlighter = new IntersectionObserver((entries) => {{
        entries.forEach((entry) => {{
          const item = sections.find((s) => s.el === entry.target);
          if (!item) return;
          if (entry.isIntersecting) {{
            links.forEach((l) => l.classList.remove("active"));
            item.link.classList.add("active");
          }}
        }});
      }}, {{ rootMargin: "-40% 0px -55% 0px", threshold: 0 }});
      sections.forEach((item) => highlighter.observe(item.el));
    }})();
  </script>
</body>
</html>
"""


def browser_binary_candidates() -> list[str]:
    candidates = [
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("chrome"),
        shutil.which("msedge"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    existing = []
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists() and str(path) not in existing:
            existing.append(str(path))
    return existing


def write_pdf_with_weasyprint(html_path: Path, pdf_path: Path) -> None:
    from weasyprint import HTML  # type: ignore

    HTML(filename=str(html_path)).write_pdf(str(pdf_path))


def write_pdf_with_browser(html_path: Path, pdf_path: Path) -> None:
    html_uri = html_path.resolve().as_uri()
    errors = []
    for browser in browser_binary_candidates():
        cmd = [
            browser,
            "--headless",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            f"--print-to-pdf={pdf_path}",
            html_uri,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 0:
            return
        errors.append((browser, proc.returncode, (proc.stderr or proc.stdout).strip()))
    raise RuntimeError(f"Browser PDF generation failed: {errors}")


def strip_inline_markers(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    return text


def write_pdf_with_reportlab(blocks: list[dict[str, Any]], pdf_path: Path, title: str) -> None:
    from reportlab.lib import colors  # type: ignore
    from reportlab.lib.pagesizes import A4  # type: ignore
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
    from reportlab.pdfbase import pdfmetrics  # type: ignore
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # type: ignore
    from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle  # type: ignore

    font_name = "Helvetica"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        font_name = "STSong-Light"
    except Exception:
        pass

    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10.5,
        leading=16,
        spaceAfter=6,
    )
    h1 = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontName=font_name,
        fontSize=18,
        leading=24,
        spaceAfter=10,
    )
    h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=14,
        leading=20,
        spaceAfter=8,
        textColor=colors.HexColor("#154b78"),
    )
    h3 = ParagraphStyle(
        "H3",
        parent=styles["Heading3"],
        fontName=font_name,
        fontSize=12,
        leading=18,
        spaceAfter=6,
        textColor=colors.HexColor("#1f4f73"),
    )
    code_style = ParagraphStyle(
        "Code",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=8.5,
        leading=11,
        backColor=colors.HexColor("#f3f8fc"),
        borderColor=colors.HexColor("#d5e2ec"),
        borderWidth=0.5,
        borderPadding=6,
    )

    story: list[Any] = [Paragraph(html.escape(title), h1), Spacer(1, 6)]
    skipped_title_h1 = False
    for block in blocks:
        kind = block["type"]
        if kind == "heading":
            level = int(block.get("level", 1))
            if level == 1 and not skipped_title_h1 and same_heading(block.get("text", ""), title):
                skipped_title_h1 = True
                continue
            text = html.escape(strip_inline_markers(block.get("text", "")))
            style = h1 if level <= 1 else h2 if level == 2 else h3
            story.append(Paragraph(text, style))
            continue
        if kind == "paragraph":
            text = html.escape(strip_inline_markers(block.get("text", "")))
            story.append(Paragraph(text, body))
            continue
        if kind == "list":
            ordered = bool(block.get("ordered"))
            for idx, item in enumerate(block.get("items", []), start=1):
                prefix = f"{idx}. " if ordered else "• "
                text = html.escape(prefix + strip_inline_markers(item))
                story.append(Paragraph(text, body))
            story.append(Spacer(1, 4))
            continue
        if kind == "code":
            code_text = block.get("text", "")
            story.append(Preformatted(code_text, code_style))
            story.append(Spacer(1, 6))
            continue
        if kind == "table":
            rows = normalize_table_rows(block.get("rows", []))
            if not rows:
                continue
            table_data = [
                [strip_inline_markers(cell) for cell in row]
                for row in rows
            ]
            table = Table(table_data, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, -1), font_name),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("LEADING", (0, 0), (-1, -1), 12),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf3fb")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#113b5a")),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1dce6")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(table)
            story.append(Spacer(1, 8))

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=40,
        bottomMargin=34,
        title=title,
    )

    def draw_footer(canvas, document) -> None:  # type: ignore
        canvas.saveState()
        canvas.setFont(font_name, 8)
        canvas.setFillColor(colors.HexColor("#6c7b88"))
        canvas.drawString(36, 18, f"{title}")
        canvas.drawRightString(A4[0] - 36, 18, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)


def generate_pdf(
    html_path: Path,
    blocks: list[dict[str, Any]],
    pdf_path: Path,
    title: str,
    preferred_engine: str,
) -> str:
    attempted: list[str] = []

    def try_engine(name: str) -> bool:
        attempted.append(name)
        try:
            if name == "weasyprint":
                write_pdf_with_weasyprint(html_path, pdf_path)
            elif name == "browser":
                write_pdf_with_browser(html_path, pdf_path)
            elif name == "reportlab":
                write_pdf_with_reportlab(blocks, pdf_path, title)
            else:
                return False
            return pdf_path.exists() and pdf_path.stat().st_size > 0
        except Exception:
            return False

    if preferred_engine == "auto":
        for name in ("weasyprint", "browser", "reportlab"):
            if try_engine(name):
                return name
    else:
        if try_engine(preferred_engine):
            return preferred_engine

    attempted_text = ", ".join(attempted) if attempted else preferred_engine
    raise RuntimeError(
        "Failed to generate PDF. Tried engines: "
        + attempted_text
        + ". Install `reportlab` or `weasyprint`, or install a headless browser."
    )


def infer_title(blocks: list[dict[str, Any]], fallback: str) -> str:
    for block in blocks:
        if block.get("type") == "heading" and int(block.get("level", 2)) == 1:
            text = block.get("text", "").strip()
            if text:
                return text
    return fallback


def main() -> None:
    args = parse_args()
    source_path = Path(args.analysis_md)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    markdown_text = source_path.read_text(encoding="utf-8", errors="ignore")
    blocks = parse_markdown_blocks(markdown_text)

    fallback_title = source_path.stem.replace("-", " ").strip() or "政策解读报告"
    title = args.title or infer_title(blocks, fallback_title)

    html_path = output_dir / f"{args.base_name}.html"
    pdf_path = output_dir / f"{args.base_name}.pdf"
    meta_path = output_dir / f"{args.base_name}.package.json"
    
    use_legacy = getattr(args, "use_legacy", False)
    html_theme = getattr(args, "html_theme", "auto")
    
    # Generate HTML
    if HAS_NEW_HTML and not use_legacy:
        # Use new modern HTML renderer
        try:
            render_html(
                analysis_md_path=str(source_path),
                output_path=str(html_path),
                title=title,
                default_theme=html_theme,
            )
            print(f"Wrote HTML (modern): {html_path}")
        except Exception as e:
            print(f"Warning: New HTML renderer failed ({e}), falling back to legacy")
            # Fallback to legacy
            metrics = collect_outline_metrics(blocks)
            body_html, sections = render_html_body(blocks, title_for_dedup=title)
            document = build_html_document(title, body_html, sections, metrics)
            html_path.write_text(document + "\n", encoding="utf-8")
            print(f"Wrote HTML (legacy): {html_path}")
    else:
        # Use legacy HTML renderer
        metrics = collect_outline_metrics(blocks)
        body_html, sections = render_html_body(blocks, title_for_dedup=title)
        document = build_html_document(title, body_html, sections, metrics)
        html_path.write_text(document + "\n", encoding="utf-8")
        print(f"Wrote HTML (legacy): {html_path}")

    # Generate PDF
    pdf_engine = "skipped"
    if not args.no_pdf:
        if HAS_NEW_PDF and not use_legacy:
            # Use new structured PDF renderer
            try:
                pdf_engine = render_pdf(
                    analysis_md_path=str(source_path),
                    output_path=str(pdf_path),
                    title=title,
                    engine=args.pdf_engine if args.pdf_engine != "browser" else "auto",
                )
                print(f"Wrote PDF (structured): {pdf_path}")
                print(f"PDF engine: {pdf_engine}")
            except Exception as e:
                print(f"Warning: New PDF renderer failed ({e}), falling back to legacy")
                pdf_engine = generate_pdf(
                    html_path=html_path,
                    blocks=blocks,
                    pdf_path=pdf_path,
                    title=title,
                    preferred_engine=args.pdf_engine,
                )
                print(f"Wrote PDF (legacy): {pdf_path}")
                print(f"PDF engine: {pdf_engine}")
        else:
            # Use legacy PDF renderer
            pdf_engine = generate_pdf(
                html_path=html_path,
                blocks=blocks,
                pdf_path=pdf_path,
                title=title,
                preferred_engine=args.pdf_engine,
            )
            print(f"Wrote PDF (legacy): {pdf_path}")
            print(f"PDF engine: {pdf_engine}")

    meta = {
        "title": title,
        "source_markdown": str(source_path.resolve()),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "html_output": str(html_path.resolve()),
        "pdf_output": str(pdf_path.resolve()) if not args.no_pdf else "",
        "pdf_engine": pdf_engine,
        "renderer": {
            "html": "modern" if (HAS_NEW_HTML and not use_legacy) else "legacy",
            "pdf": "structured" if (HAS_NEW_PDF and not use_legacy) else "legacy",
        },
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote package metadata: {meta_path}")


if __name__ == "__main__":
    main()
