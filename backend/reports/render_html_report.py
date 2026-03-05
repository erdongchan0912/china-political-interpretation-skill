#!/usr/bin/env python3
"""Render modern interactive HTML report for China political analysis.

Design principles:
- Modern, beautiful UI with smooth animations
- Responsive layout for all devices
- Dark/Light theme toggle
- Collapsible sections with smooth transitions
- Floating navigation with scroll highlighting
- Interactive evidence tags with tooltips
- Sortable/filterable tables
"""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render modern interactive HTML report from markdown analysis."
    )
    parser.add_argument("--analysis-md", required=True, help="Input markdown analysis path.")
    parser.add_argument("--output", required=True, help="Output HTML path.")
    parser.add_argument("--title", help="Optional report title override.")
    parser.add_argument("--theme", choices=["light", "dark", "auto"], default="auto", help="Default theme.")
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
            if re.match(r"^#{1,6}\s+", lines[i]) or re.match(r"^[-*]\s+", lines[i]):
                break
            if re.match(r"^\d+\.\s+", lines[i]):
                break
            if "|" in lines[i] and i + 1 < len(lines) and is_table_separator(lines[i + 1]):
                break
            para_lines.append(lines[i].strip())
            i += 1
        blocks.append({"type": "paragraph", "text": " ".join(para_lines).strip()})
    
    return blocks


def infer_title(blocks: list[dict[str, Any]], fallback: str) -> str:
    for block in blocks:
        if block.get("type") == "heading" and block.get("level") == 1:
            return block.get("text", fallback)
    return fallback


def normalize_table_rows(rows: list[list[str]]) -> list[list[str]]:
    max_cols = max((len(row) for row in rows), default=0)
    if max_cols == 0:
        return rows
    return [row + [""] * (max_cols - len(row)) for row in rows]


def strip_inline_markers(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    return text


def render_inline_html(text: str) -> str:
    """Render inline markdown to HTML with evidence tags and tooltips."""
    def render_segment(segment: str) -> str:
        escaped = html.escape(segment)
        
        # Evidence tags with tooltips
        escaped = re.sub(
            r"\[([Ff])\]",
            '<span class="e-tag tag-f" data-tooltip="事实 - 可核验的直接引用">F</span>',
            escaped,
        )
        escaped = re.sub(
            r"\[([Ii])\]",
            '<span class="e-tag tag-i" data-tooltip="推断 - 基于多证据的归纳">I</span>',
            escaped,
        )
        escaped = re.sub(
            r"\[([Ss])\]",
            '<span class="e-tag tag-s" data-tooltip="情景 - 未来走向判断">S</span>',
            escaped,
        )
        
        # Confidence tags
        escaped = re.sub(
            r"\[confidence=high\]",
            '<span class="c-tag c-high" data-tooltip="高置信度">高</span>',
            escaped,
            flags=re.IGNORECASE,
        )
        escaped = re.sub(
            r"\[confidence=medium\]",
            '<span class="c-tag c-medium" data-tooltip="中置信度">中</span>',
            escaped,
            flags=re.IGNORECASE,
        )
        escaped = re.sub(
            r"\[confidence=low\]",
            '<span class="c-tag c-low" data-tooltip="低置信度">低</span>',
            escaped,
            flags=re.IGNORECASE,
        )
        
        # Source tiers
        escaped = re.sub(
            r"\b(T0)\b",
            '<span class="tier-tag tier-0" data-tooltip="核心公报/领袖讲话">T0</span>',
            escaped,
        )
        escaped = re.sub(
            r"\b(T1)\b",
            '<span class="tier-tag tier-1" data-tooltip="中央文件/新华社受权发布">T1</span>',
            escaped,
        )
        escaped = re.sub(
            r"\b(T2)\b",
            '<span class="tier-tag tier-2" data-tooltip="部委规章/央媒评论">T2</span>',
            escaped,
        )
        escaped = re.sub(
            r"\b(T3)\b",
            '<span class="tier-tag tier-3" data-tooltip="地方执行/外围官媒">T3</span>',
            escaped,
        )
        
        return escaped
    
    # Handle inline code
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


def unique_id(text: str, used_ids: set[str], idx: int) -> str:
    base = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip(), flags=re.UNICODE)
    base = re.sub(r"-{2,}", "-", base).strip("-").lower()
    if not base:
        base = f"section-{idx}"
    candidate = base
    seq = 2
    while candidate in used_ids:
        candidate = f"{base}-{seq}"
        seq += 1
    used_ids.add(candidate)
    return candidate


def collect_metrics(blocks: list[dict[str, Any]]) -> dict[str, Any]:
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


def render_html_body(
    blocks: list[dict[str, Any]], 
    title_for_dedup: str | None = None
) -> tuple[str, list[dict[str, str]]]:
    """Render blocks to HTML body content."""
    output: list[str] = []
    sections: list[dict[str, str]] = []
    used_ids: set[str] = set()
    section_idx = 0
    section_open = False
    removed_title = False
    
    for block in blocks:
        kind = block["type"]
        
        if kind == "heading":
            level = min(max(int(block["level"]), 1), 6)
            text = block.get("text", "")
            
            # Skip duplicate title
            if level == 1 and title_for_dedup and not removed_title:
                if strip_inline_markers(text).strip().lower() == title_for_dedup.strip().lower():
                    removed_title = True
                    continue
            
            if level == 2:
                if section_open:
                    output.append("</section>")
                section_idx += 1
                section_open = True
                plain_title = strip_inline_markers(text)
                heading_id = unique_id(plain_title, used_ids, section_idx)
                sections.append({"id": heading_id, "title": plain_title})
                output.append(f'<section class="content-section" id="section-{section_idx}">')
                output.append(f'<h2 id="{heading_id}" class="section-header">')
                output.append(f'<button class="collapse-btn" aria-expanded="true" aria-controls="content-{section_idx}">')
                output.append('<svg class="collapse-icon" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7"/></svg>')
                output.append('</button>')
                output.append(f'<span>{render_inline_html(text)}</span>')
                output.append('</h2>')
                output.append(f'<div class="section-content" id="content-{section_idx}">')
                continue
            
            if not section_open:
                section_idx += 1
                section_open = True
                output.append(f'<section class="content-section" id="section-{section_idx}">')
                output.append(f'<div class="section-content" id="content-{section_idx}">')
            
            output.append(f"<h{level}>{render_inline_html(text)}</h{level}>")
        
        elif kind == "paragraph":
            if not section_open:
                section_idx += 1
                section_open = True
                output.append(f'<section class="content-section" id="section-{section_idx}">')
                output.append(f'<div class="section-content" id="content-{section_idx}">')
            output.append(f"<p>{render_inline_html(block['text'])}</p>")
        
        elif kind == "code":
            if not section_open:
                section_idx += 1
                section_open = True
                output.append(f'<section class="content-section" id="section-{section_idx}">')
                output.append(f'<div class="section-content" id="content-{section_idx}">')
            output.append('<pre class="code-block"><code>')
            output.append(html.escape(block["text"]))
            output.append('</code></pre>')
        
        elif kind == "list":
            if not section_open:
                section_idx += 1
                section_open = True
                output.append(f'<section class="content-section" id="section-{section_idx}">')
                output.append(f'<div class="section-content" id="content-{section_idx}">')
            tag = "ol" if block.get("ordered") else "ul"
            output.append(f"<{tag}>")
            for item in block.get("items", []):
                output.append(f"<li>{render_inline_html(item)}</li>")
            output.append(f"</{tag}>")
        
        elif kind == "table":
            if not section_open:
                section_idx += 1
                section_open = True
                output.append(f'<section class="content-section" id="section-{section_idx}">')
                output.append(f'<div class="section-content" id="content-{section_idx}">')
            rows = normalize_table_rows(block.get("rows", []))
            if not rows:
                continue
            
            output.append('<div class="table-container">')
            output.append('<table class="data-table sortable">')
            output.append("<thead><tr>")
            for idx, cell in enumerate(rows[0]):
                output.append(f'<th data-col="{idx}" class="sortable-header">')
                output.append(render_inline_html(cell))
                output.append('<span class="sort-indicator"></span>')
                output.append('</th>')
            output.append("</tr></thead>")
            output.append("<tbody>")
            for row in rows[1:]:
                output.append("<tr>")
                for cell in row:
                    output.append(f"<td>{render_inline_html(cell)}</td>")
                output.append("</tr>")
            output.append("</tbody></table>")
            output.append('</div>')
    
    if section_open:
        output.append("</div></section>")
    
    return "\n".join(output), sections


def build_html_document(
    title: str,
    body_html: str,
    sections: list[dict[str, str]],
    metrics: dict[str, Any],
    default_theme: str = "auto",
) -> str:
    """Build complete HTML document."""
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    safe_title = html.escape(title)
    
    nav_items = "\n".join(
        f'<a href="#{html.escape(s["id"])}" class="nav-link">{html.escape(s["title"])}</a>'
        for s in sections
    )
    
    f_count = metrics["tag_count"]["F"]
    i_count = metrics["tag_count"]["I"]
    s_count = metrics["tag_count"]["S"]
    high_count = metrics["confidence_count"]["high"]
    medium_count = metrics["confidence_count"]["medium"]
    low_count = metrics["confidence_count"]["low"]
    section_count = metrics["sections"]
    table_count = metrics["tables"]
    t0 = metrics["tier_count"]["T0"]
    t1 = metrics["tier_count"]["T1"]
    t2 = metrics["tier_count"]["T2"]
    t3 = metrics["tier_count"]["T3"]
    
    return f'''<!DOCTYPE html>
<html lang="zh-CN" data-theme="{default_theme}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>{safe_title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg-primary: #ffffff;
      --bg-secondary: #f8fafc;
      --bg-tertiary: #f1f5f9;
      --bg-card: #ffffff;
      --text-primary: #0f172a;
      --text-secondary: #475569;
      --text-muted: #94a3b8;
      --border: #e2e8f0;
      --border-hover: #cbd5e1;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --accent-soft: #dbeafe;
      --success: #22c55e;
      --success-soft: #dcfce7;
      --warning: #f59e0b;
      --warning-soft: #fef3c7;
      --danger: #ef4444;
      --danger-soft: #fee2e2;
      --info: #06b6d4;
      --info-soft: #cffafe;
      --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
      --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1);
      --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -4px rgba(0,0,0,0.1);
      --radius-sm: 6px;
      --radius-md: 10px;
      --radius-lg: 16px;
      --transition: 0.2s ease;
    }}
    
    [data-theme="dark"] {{
      --bg-primary: #0f172a;
      --bg-secondary: #1e293b;
      --bg-tertiary: #334155;
      --bg-card: #1e293b;
      --text-primary: #f1f5f9;
      --text-secondary: #cbd5e1;
      --text-muted: #64748b;
      --border: #334155;
      --border-hover: #475569;
      --accent-soft: #1e3a5f;
      --success-soft: #14532d;
      --warning-soft: #713f12;
      --danger-soft: #7f1d1d;
      --info-soft: #164e63;
      --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
      --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.4);
      --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.5);
    }}
    
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    
    html {{
      scroll-behavior: smooth;
      scroll-padding-top: 80px;
    }}
    
    body {{
      font-family: "Inter", "Noto Sans SC", system-ui, sans-serif;
      background: var(--bg-primary);
      color: var(--text-primary);
      line-height: 1.7;
      -webkit-font-smoothing: antialiased;
      transition: background var(--transition), color var(--transition);
    }}
    
    /* Header */
    .header {{
      position: sticky;
      top: 0;
      z-index: 100;
      background: var(--bg-primary);
      border-bottom: 1px solid var(--border);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
    }}
    
    .header-inner {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 16px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    
    .header-title {{
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--text-primary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 60%;
    }}
    
    .header-actions {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    
    .theme-toggle {{
      width: 40px;
      height: 40px;
      border-radius: 50%;
      border: 1px solid var(--border);
      background: var(--bg-secondary);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all var(--transition);
    }}
    
    .theme-toggle:hover {{
      background: var(--bg-tertiary);
      border-color: var(--border-hover);
    }}
    
    .theme-toggle svg {{
      width: 20px;
      height: 20px;
      fill: var(--text-secondary);
    }}
    
    .sun-icon {{ display: none; }}
    .moon-icon {{ display: block; }}
    [data-theme="dark"] .sun-icon {{ display: block; }}
    [data-theme="dark"] .moon-icon {{ display: none; }}
    
    /* Layout */
    .container {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 24px;
      display: grid;
      grid-template-columns: 280px 1fr;
      gap: 24px;
    }}
    
    @media (max-width: 1024px) {{
      .container {{ grid-template-columns: 1fr; }}
      .sidebar {{ display: none; }}
    }}
    
    /* Sidebar */
    .sidebar {{
      position: sticky;
      top: 100px;
      height: fit-content;
      max-height: calc(100vh - 120px);
      overflow-y: auto;
    }}
    
    .sidebar-card {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 20px;
      box-shadow: var(--shadow-sm);
    }}
    
    .stats-grid {{
      display: grid;
      gap: 12px;
      margin-bottom: 20px;
    }}
    
    .stat-item {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px;
      background: var(--bg-secondary);
      border-radius: var(--radius-md);
    }}
    
    .stat-label {{
      font-size: 0.875rem;
      color: var(--text-secondary);
    }}
    
    .stat-value {{
      font-size: 1.125rem;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      color: var(--accent);
    }}
    
    .nav-title {{
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 12px;
      padding-top: 16px;
      border-top: 1px solid var(--border);
    }}
    
    .nav-links {{
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}
    
    .nav-link {{
      font-size: 0.875rem;
      color: var(--text-secondary);
      text-decoration: none;
      padding: 8px 12px;
      border-radius: var(--radius-sm);
      transition: all var(--transition);
      border-left: 3px solid transparent;
    }}
    
    .nav-link:hover {{
      background: var(--bg-tertiary);
      color: var(--text-primary);
    }}
    
    .nav-link.active {{
      background: var(--accent-soft);
      color: var(--accent);
      border-left-color: var(--accent);
    }}
    
    /* Main Content */
    .main-content {{
      min-width: 0;
    }}
    
    .hero {{
      background: linear-gradient(135deg, var(--accent), var(--info));
      border-radius: var(--radius-lg);
      padding: 32px;
      margin-bottom: 24px;
      color: white;
    }}
    
    .hero h1 {{
      font-size: 1.75rem;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    
    .hero-meta {{
      font-size: 0.875rem;
      opacity: 0.9;
    }}
    
    /* Sections */
    .content-section {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      margin-bottom: 16px;
      overflow: hidden;
      box-shadow: var(--shadow-sm);
      transition: box-shadow var(--transition);
    }}
    
    .content-section:hover {{
      box-shadow: var(--shadow-md);
    }}
    
    .section-header {{
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 16px 20px;
      background: var(--bg-secondary);
      border-bottom: 1px solid var(--border);
      cursor: pointer;
      user-select: none;
      transition: background var(--transition);
    }}
    
    .section-header:hover {{
      background: var(--bg-tertiary);
    }}
    
    .section-header span {{
      font-size: 1rem;
      font-weight: 600;
      color: var(--text-primary);
      flex: 1;
    }}
    
    .collapse-btn {{
      width: 28px;
      height: 28px;
      border-radius: var(--radius-sm);
      border: none;
      background: var(--bg-card);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all var(--transition);
    }}
    
    .collapse-btn:hover {{
      background: var(--accent-soft);
    }}
    
    .collapse-icon {{
      width: 16px;
      height: 16px;
      stroke: var(--text-secondary);
      stroke-width: 2;
      fill: none;
      transition: transform var(--transition);
    }}
    
    .collapse-btn[aria-expanded="false"] .collapse-icon {{
      transform: rotate(-90deg);
    }}
    
    .section-content {{
      padding: 20px;
      transition: all 0.3s ease;
    }}
    
    .section-content.collapsed {{
      display: none;
    }}
    
    /* Typography */
    h3, h4, h5, h6 {{
      color: var(--text-primary);
      margin: 1.5em 0 0.75em;
      font-weight: 600;
    }}
    
    h3 {{ font-size: 1.125rem; }}
    h4 {{ font-size: 1rem; }}
    
    p {{
      margin: 0.75em 0;
      color: var(--text-secondary);
    }}
    
    ul, ol {{
      margin: 0.75em 0;
      padding-left: 1.5em;
    }}
    
    li {{
      margin: 0.5em 0;
      color: var(--text-secondary);
    }}
    
    /* Evidence Tags */
    .e-tag {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 24px;
      height: 24px;
      padding: 0 8px;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 700;
      color: white;
      cursor: help;
      transition: transform var(--transition);
      position: relative;
    }}
    
    .e-tag:hover {{
      transform: scale(1.1);
    }}
    
    .tag-f {{ background: var(--success); }}
    .tag-i {{ background: var(--accent); }}
    .tag-s {{ background: var(--danger); }}
    
    .c-tag {{
      display: inline-flex;
      align-items: center;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 600;
      cursor: help;
    }}
    
    .c-high {{ background: var(--success-soft); color: var(--success); }}
    .c-medium {{ background: var(--warning-soft); color: var(--warning); }}
    .c-low {{ background: var(--danger-soft); color: var(--danger); }}
    
    .tier-tag {{
      display: inline-flex;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 0.7rem;
      font-weight: 700;
      font-family: "JetBrains Mono", monospace;
      cursor: help;
    }}
    
    .tier-0 {{ background: #fef3c7; color: #92400e; }}
    .tier-1 {{ background: #dbeafe; color: #1d4ed8; }}
    .tier-2 {{ background: #e0e7ff; color: #4338ca; }}
    .tier-3 {{ background: #f3e8ff; color: #7c3aed; }}
    
    [data-theme="dark"] .tier-0 {{ background: #451a03; color: #fbbf24; }}
    [data-theme="dark"] .tier-1 {{ background: #1e3a8a; color: #60a5fa; }}
    [data-theme="dark"] .tier-2 {{ background: #312e81; color: #818cf8; }}
    [data-theme="dark"] .tier-3 {{ background: #4c1d95; color: #a78bfa; }}
    
    /* Tooltips */
    [data-tooltip] {{
      position: relative;
    }}
    
    [data-tooltip]::after {{
      content: attr(data-tooltip);
      position: absolute;
      bottom: 100%;
      left: 50%;
      transform: translateX(-50%) translateY(-8px);
      padding: 8px 12px;
      background: var(--bg-tertiary);
      color: var(--text-primary);
      font-size: 0.75rem;
      font-weight: 500;
      white-space: nowrap;
      border-radius: var(--radius-sm);
      box-shadow: var(--shadow-md);
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.2s, transform 0.2s;
      z-index: 1000;
    }}
    
    [data-tooltip]:hover::after {{
      opacity: 1;
      transform: translateX(-50%) translateY(-4px);
    }}
    
    /* Tables */
    .table-container {{
      overflow-x: auto;
      margin: 1em 0;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
    }}
    
    .data-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
    }}
    
    .data-table th {{
      background: var(--bg-secondary);
      color: var(--text-primary);
      font-weight: 600;
      padding: 12px 16px;
      text-align: left;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }}
    
    .sortable-header {{
      cursor: pointer;
      user-select: none;
      transition: background var(--transition);
    }}
    
    .sortable-header:hover {{
      background: var(--bg-tertiary);
    }}
    
    .sort-indicator {{
      margin-left: 8px;
      opacity: 0.3;
    }}
    
    .sort-indicator::after {{
      content: "↕";
    }}
    
    th.sort-asc .sort-indicator::after {{ content: "↑"; opacity: 1; }}
    th.sort-desc .sort-indicator::after {{ content: "↓"; opacity: 1; }}
    
    .data-table td {{
      padding: 12px 16px;
      border-bottom: 1px solid var(--border);
      color: var(--text-secondary);
      vertical-align: top;
    }}
    
    .data-table tr:last-child td {{
      border-bottom: none;
    }}
    
    .data-table tr:hover td {{
      background: var(--bg-secondary);
    }}
    
    /* Code */
    code {{
      font-family: "JetBrains Mono", monospace;
      font-size: 0.875em;
      padding: 2px 6px;
      background: var(--bg-tertiary);
      border-radius: 4px;
      color: var(--danger);
    }}
    
    .code-block {{
      background: var(--bg-secondary);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 16px;
      overflow-x: auto;
      margin: 1em 0;
    }}
    
    .code-block code {{
      background: none;
      padding: 0;
      color: var(--text-primary);
    }}
    
    /* Footer */
    .footer {{
      max-width: 1400px;
      margin: 24px auto;
      padding: 0 24px;
      text-align: center;
      font-size: 0.875rem;
      color: var(--text-muted);
    }}
    
    /* Animations */
    @keyframes fadeIn {{
      from {{ opacity: 0; transform: translateY(10px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    
    .content-section {{
      animation: fadeIn 0.4s ease backwards;
    }}
    
    .content-section:nth-child(1) {{ animation-delay: 0.1s; }}
    .content-section:nth-child(2) {{ animation-delay: 0.15s; }}
    .content-section:nth-child(3) {{ animation-delay: 0.2s; }}
    .content-section:nth-child(4) {{ animation-delay: 0.25s; }}
    .content-section:nth-child(5) {{ animation-delay: 0.3s; }}
    
    /* Responsive */
    @media (max-width: 768px) {{
      .header-inner {{ padding: 12px 16px; }}
      .header-title {{ font-size: 1rem; max-width: 50%; }}
      .container {{ padding: 16px; }}
      .hero {{ padding: 24px; }}
      .hero h1 {{ font-size: 1.5rem; }}
      .section-header {{ padding: 12px 16px; }}
      .section-content {{ padding: 16px; }}
      .data-table {{ font-size: 0.8rem; }}
      .data-table th, .data-table td {{ padding: 8px 12px; }}
    }}
    
    /* Print */
    @media print {{
      .header, .sidebar, .theme-toggle, .collapse-btn {{ display: none !important; }}
      .content-section {{ break-inside: avoid; box-shadow: none; border: 1px solid #ddd; }}
      .section-content.collapsed {{ display: block !important; }}
      body {{ background: white; color: black; }}
    }}
  </style>
</head>
<body>
  <header class="header">
    <div class="header-inner">
      <h1 class="header-title">{safe_title}</h1>
      <div class="header-actions">
        <button class="theme-toggle" onclick="toggleTheme()" aria-label="切换主题">
          <svg class="sun-icon" viewBox="0 0 24 24"><path d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
          <svg class="moon-icon" viewBox="0 0 24 24"><path d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/></svg>
        </button>
      </div>
    </div>
  </header>
  
  <div class="container">
    <aside class="sidebar">
      <div class="sidebar-card">
        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-label">事实标记 F</span>
            <span class="stat-value">{f_count}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">推断标记 I</span>
            <span class="stat-value">{i_count}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">情景标记 S</span>
            <span class="stat-value">{s_count}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">置信度 高/中/低</span>
            <span class="stat-value">{high_count}/{medium_count}/{low_count}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">信源层级 T0-T3</span>
            <span class="stat-value">{t0}/{t1}/{t2}/{t3}</span>
          </div>
        </div>
        
        <div class="nav-title">章节导航</div>
        <nav class="nav-links">
          {nav_items if nav_items else '<span style="color: var(--text-muted); font-size: 0.875rem;">暂无章节</span>'}
        </nav>
      </div>
    </aside>
    
    <main class="main-content">
      <div class="hero">
        <h1>{safe_title}</h1>
        <p class="hero-meta">生成时间: {generated_at} | 章节: {section_count} | 表格: {table_count}</p>
      </div>
      
      {body_html}
    </main>
  </div>
  
  <footer class="footer">
    <p>中国政治解读分析报告 | 所有章节默认展开展示</p>
  </footer>
  
  <script>
    // Theme toggle
    function getPreferredTheme() {{
      const stored = localStorage.getItem('theme');
      if (stored) return stored;
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }}
    
    function setTheme(theme) {{
      document.documentElement.setAttribute('data-theme', theme);
      localStorage.setItem('theme', theme);
    }}
    
    function toggleTheme() {{
      const current = document.documentElement.getAttribute('data-theme');
      const newTheme = current === 'dark' ? 'light' : 'dark';
      setTheme(newTheme);
    }}
    
    // Initialize theme
    const initialTheme = document.documentElement.getAttribute('data-theme');
    if (initialTheme === 'auto') {{
      setTheme(getPreferredTheme());
    }}
    
    // Collapsible sections
    document.querySelectorAll('.collapse-btn').forEach(btn => {{
      btn.addEventListener('click', (e) => {{
        e.stopPropagation();
        const expanded = btn.getAttribute('aria-expanded') === 'true';
        const contentId = btn.getAttribute('aria-controls');
        const content = document.getElementById(contentId);
        
        btn.setAttribute('aria-expanded', !expanded);
        if (content) {{
          content.classList.toggle('collapsed', expanded);
        }}
      }});
    }});
    
    // Also toggle when clicking section header
    document.querySelectorAll('.section-header').forEach(header => {{
      header.addEventListener('click', () => {{
        const btn = header.querySelector('.collapse-btn');
        if (btn) btn.click();
      }});
    }});
    
    // Sortable tables
    document.querySelectorAll('.sortable-header').forEach(header => {{
      header.addEventListener('click', () => {{
        const table = header.closest('table');
        const tbody = table.querySelector('tbody');
        const colIndex = parseInt(header.dataset.col);
        const rows = Array.from(tbody.querySelectorAll('tr'));
        
        // Determine sort direction
        const isAsc = header.classList.contains('sort-asc');
        
        // Reset all headers
        table.querySelectorAll('th').forEach(th => {{
          th.classList.remove('sort-asc', 'sort-desc');
        }});
        
        // Sort rows
        rows.sort((a, b) => {{
          const aVal = a.cells[colIndex]?.textContent || '';
          const bVal = b.cells[colIndex]?.textContent || '';
          return isAsc ? bVal.localeCompare(aVal, 'zh-CN') : aVal.localeCompare(bVal, 'zh-CN');
        }});
        
        // Update header class
        header.classList.add(isAsc ? 'sort-desc' : 'sort-asc');
        
        // Reorder rows
        rows.forEach(row => tbody.appendChild(row));
      }});
    }});
    
    // Navigation highlighting
    const navLinks = document.querySelectorAll('.nav-link');
    const sections = Array.from(navLinks).map(link => {{
      const id = link.getAttribute('href').slice(1);
      return {{ link, el: document.getElementById(id) }};
    }}).filter(item => item.el);
    
    if (sections.length > 0 && 'IntersectionObserver' in window) {{
      const observer = new IntersectionObserver((entries) => {{
        entries.forEach(entry => {{
          const item = sections.find(s => s.el === entry.target);
          if (!item) return;
          
          if (entry.isIntersecting) {{
            navLinks.forEach(l => l.classList.remove('active'));
            item.link.classList.add('active');
          }}
        }});
      }}, {{ rootMargin: '-30% 0px -65% 0px' }});
      
      sections.forEach(item => observer.observe(item.el));
    }}
    
    // Smooth scroll for nav links
    navLinks.forEach(link => {{
      link.addEventListener('click', (e) => {{
        e.preventDefault();
        const id = link.getAttribute('href').slice(1);
        const target = document.getElementById(id);
        if (target) {{
          target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
        }}
      }});
    }});
  </script>
</body>
</html>'''


def render_html(
    analysis_md_path: str,
    output_path: str,
    title: str | None = None,
    default_theme: str = "auto",
) -> None:
    """Main entry point for HTML rendering."""
    source_path = Path(analysis_md_path)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    markdown_text = source_path.read_text(encoding="utf-8", errors="ignore")
    blocks = parse_markdown_blocks(markdown_text)
    
    if not title:
        title = infer_title(blocks, source_path.stem.replace("-", " ").strip() or "政策解读报告")
    
    metrics = collect_metrics(blocks)
    body_html, sections = render_html_body(blocks, title_for_dedup=title)
    document = build_html_document(title, body_html, sections, metrics, default_theme)
    
    out_path.write_text(document + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    
    render_html(
        analysis_md_path=args.analysis_md,
        output_path=args.output,
        title=args.title,
        default_theme=args.theme,
    )
    
    print(f"Wrote HTML: {args.output}")


if __name__ == "__main__":
    main()
