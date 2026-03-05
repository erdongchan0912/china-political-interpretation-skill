#!/usr/bin/env python3
"""Render structured PDF report for China political analysis.

Design principles:
- Clear text hierarchy with numbered sections
- Clean table layout with proper borders
- No decorative elements (gradients, animations, etc.)
- A4 format, print-friendly
- Emphasis on readability and information structure
"""

from __future__ import annotations

import argparse
import html
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        PageBreak,
        PageTemplate,
        Paragraph,
        Preformatted,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

try:
    from weasyprint import HTML, CSS
    HAS_WEASYPRINT = True
except ImportError:
    HAS_WEASYPRINT = False


PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_LEFT = 25 * mm
MARGIN_RIGHT = 25 * mm
MARGIN_TOP = 30 * mm
MARGIN_BOTTOM = 25 * mm
CONTENT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render structured PDF report from markdown analysis."
    )
    parser.add_argument("--analysis-md", required=True, help="Input markdown analysis path.")
    parser.add_argument("--output", required=True, help="Output PDF path.")
    parser.add_argument("--title", help="Optional report title override.")
    parser.add_argument(
        "--engine",
        choices=["reportlab", "weasyprint", "auto"],
        default="auto",
        help="PDF engine to use.",
    )
    return parser.parse_args()


def strip_inline_markers(text: str) -> str:
    """Remove markdown inline markers like **, `, etc."""
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    return text


def extract_evidence_tags(text: str) -> list[str]:
    """Extract [F], [I], [S] tags from text."""
    return re.findall(r"\[([FfIiSs])\]", text)


def extract_confidence(text: str) -> str | None:
    """Extract confidence level from text."""
    match = re.search(r"\[confidence=(high|medium|low)\]", text, flags=re.IGNORECASE)
    return match.group(1).lower() if match else None


def clean_text_for_pdf(text: str) -> str:
    """Clean text for PDF display, preserving evidence markers in readable form."""
    # Convert [F]/[I]/[S] to readable format
    text = re.sub(r"\[([Ff])\]", "[事实]", text)
    text = re.sub(r"\[([Ii])\]", "[推断]", text)
    text = re.sub(r"\[([Ss])\]", "[情景]", text)
    # Convert confidence markers
    text = re.sub(r"\[confidence=high\]", "[高置信]", text, flags=re.IGNORECASE)
    text = re.sub(r"\[confidence=medium\]", "[中置信]", text, flags=re.IGNORECASE)
    text = re.sub(r"\[confidence=low\]", "[低置信]", text, flags=re.IGNORECASE)
    return strip_inline_markers(text)


def is_table_separator(line: str) -> bool:
    """Check if line is a markdown table separator."""
    if "|" not in line:
        return False
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def parse_table_row(line: str) -> list[str]:
    """Parse a markdown table row into cells."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_markdown_blocks(markdown_text: str) -> list[dict[str, Any]]:
    """Parse markdown into structured blocks."""
    lines = markdown_text.splitlines()
    blocks: list[dict[str, Any]] = []
    i = 0
    section_number = [0]  # Track section numbering
    
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        
        if not stripped:
            i += 1
            continue
        
        # Code blocks
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
        
        # Headings
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            
            # Update section numbers
            if level == 1:
                section_number = [0]
            elif level == 2:
                section_number = [section_number[0] + 1] if section_number else [1]
            elif level == 3:
                if len(section_number) >= 2:
                    section_number = section_number[:1] + [section_number[1] + 1]
                else:
                    section_number = section_number[:1] + [1]
            
            blocks.append({
                "type": "heading",
                "level": level,
                "text": text,
                "number": ".".join(str(n) for n in section_number) if level > 1 else "",
            })
            i += 1
            continue
        
        # Tables
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
        
        # Unordered lists
        if re.match(r"^[-*]\s+", line):
            items: list[str] = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].rstrip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].rstrip()).strip())
                i += 1
            blocks.append({"type": "list", "ordered": False, "items": items})
            continue
        
        # Ordered lists
        if re.match(r"^\d+\.\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].rstrip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].rstrip()).strip())
                i += 1
            blocks.append({"type": "list", "ordered": True, "items": items})
            continue
        
        # Paragraphs
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
    """Extract title from first H1 heading."""
    for block in blocks:
        if block.get("type") == "heading" and block.get("level") == 1:
            return block.get("text", fallback)
    return fallback


def normalize_table_rows(rows: list[list[str]]) -> list[list[str]]:
    """Ensure all rows have the same number of columns."""
    max_cols = max((len(row) for row in rows), default=0)
    if max_cols == 0:
        return rows
    return [row + [""] * (max_cols - len(row)) for row in rows]


def render_pdf_with_reportlab(
    blocks: list[dict[str, Any]],
    output_path: Path,
    title: str,
) -> None:
    """Render PDF using ReportLab."""
    if not HAS_REPORTLAB:
        raise ImportError("reportlab is required for PDF generation")
    
    # Register Chinese font
    font_name = "Helvetica"
    font_name_bold = "Helvetica-Bold"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        font_name = "STSong-Light"
        font_name_bold = "STSong-Light"
    except Exception:
        pass
    
    # Define styles
    styles = getSampleStyleSheet()
    
    style_title = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName=font_name_bold,
        fontSize=18,
        leading=24,
        spaceAfter=12,
        alignment=1,  # Center
    )
    
    style_h1 = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontName=font_name_bold,
        fontSize=16,
        leading=22,
        spaceBefore=16,
        spaceAfter=8,
        textColor=colors.HexColor("#1a365d"),
    )
    
    style_h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontName=font_name_bold,
        fontSize=13,
        leading=18,
        spaceBefore=14,
        spaceAfter=6,
        textColor=colors.HexColor("#2c5282"),
        leftIndent=0,
    )
    
    style_h3 = ParagraphStyle(
        "H3",
        parent=styles["Heading3"],
        fontName=font_name_bold,
        fontSize=11,
        leading=16,
        spaceBefore=10,
        spaceAfter=4,
        textColor=colors.HexColor("#3182ce"),
        leftIndent=10,
    )
    
    style_body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10,
        leading=15,
        spaceAfter=6,
        leftIndent=10,
    )
    
    style_list_item = ParagraphStyle(
        "ListItem",
        parent=style_body,
        leftIndent=20,
        bulletIndent=10,
    )
    
    style_code = ParagraphStyle(
        "Code",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=8,
        leading=11,
        backColor=colors.HexColor("#f7fafc"),
        borderColor=colors.HexColor("#e2e8f0"),
        borderWidth=0.5,
        borderPadding=6,
        leftIndent=10,
    )
    
    # Build story
    story: list[Any] = []
    
    # Title page header
    story.append(Paragraph(html.escape(title), style_title))
    story.append(Spacer(1, 6))
    
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph(
        f"<para alignment='center' fontSize='9' textColor='#718096'>生成时间: {generated_at}</para>",
        styles["Normal"]
    ))
    story.append(Spacer(1, 20))
    
    # Track if we've skipped the title H1
    skipped_title = False
    
    for block in blocks:
        kind = block["type"]
        
        if kind == "heading":
            level = block.get("level", 1)
            text = clean_text_for_pdf(block.get("text", ""))
            number = block.get("number", "")
            
            # Skip duplicate title
            if level == 1 and not skipped_title:
                if text.lower().strip() == title.lower().strip():
                    skipped_title = True
                    continue
            
            # Format heading with number
            if number and level > 1:
                text = f"{number}. {text}"
            
            if level == 1:
                story.append(Paragraph(html.escape(text), style_h1))
            elif level == 2:
                story.append(Paragraph(html.escape(text), style_h2))
            else:
                story.append(Paragraph(html.escape(text), style_h3))
        
        elif kind == "paragraph":
            text = clean_text_for_pdf(block.get("text", ""))
            story.append(Paragraph(html.escape(text), style_body))
        
        elif kind == "list":
            ordered = block.get("ordered", False)
            for idx, item in enumerate(block.get("items", []), start=1):
                text = clean_text_for_pdf(item)
                prefix = f"{idx}. " if ordered else "• "
                story.append(Paragraph(html.escape(prefix + text), style_list_item))
            story.append(Spacer(1, 4))
        
        elif kind == "code":
            code_text = block.get("text", "")
            story.append(Preformatted(code_text, style_code))
            story.append(Spacer(1, 6))
        
        elif kind == "table":
            rows = normalize_table_rows(block.get("rows", []))
            if not rows:
                continue
            
            # Clean table data
            table_data = []
            for row in rows:
                clean_row = [clean_text_for_pdf(cell) for cell in row]
                table_data.append(clean_row)
            
            # Calculate column widths
            col_count = len(table_data[0]) if table_data else 1
            col_width = (CONTENT_WIDTH - 20) / col_count
            
            table = Table(table_data, colWidths=[col_width] * col_count, repeatRows=1)
            table.setStyle(TableStyle([
                # Header styling
                ("FONTNAME", (0, 0), (-1, 0), font_name_bold),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf2f7")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                
                # Body styling
                ("FONTNAME", (0, 1), (-1, -1), font_name),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("LEADING", (0, 1), (-1, -1), 12),
                ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#2d3748")),
                ("ALIGN", (0, 1), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                
                # Grid
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 1), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
                
                # Alternating row colors
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
            ]))
            
            story.append(Spacer(1, 6))
            story.append(table)
            story.append(Spacer(1, 10))
    
    # Build PDF
    def add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont(font_name, 8)
        canvas.setFillColor(colors.HexColor("#718096"))
        
        # Footer with title and page number
        canvas.drawString(MARGIN_LEFT, 15 * mm, title[:50] + "..." if len(title) > 50 else title)
        canvas.drawRightString(PAGE_WIDTH - MARGIN_RIGHT, 15 * mm, f"第 {doc.page} 页")
        
        canvas.restoreState()
    
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=MARGIN_LEFT,
        rightMargin=MARGIN_RIGHT,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title=title,
        author="China Political Interpretation System",
    )
    
    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)


def render_pdf_with_weasyprint(
    blocks: list[dict[str, Any]],
    output_path: Path,
    title: str,
) -> None:
    """Render PDF using WeasyPrint."""
    if not HAS_WEASYPRINT:
        raise ImportError("weasyprint is required for PDF generation")
    
    # Generate HTML for WeasyPrint
    html_parts = [f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <title>{html.escape(title)}</title>
    <style>
        @page {{
            size: A4;
            margin: 25mm 20mm 20mm 20mm;
            @bottom-center {{
                content: counter(page);
                font-size: 9pt;
                color: #718096;
            }}
        }}
        body {{
            font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
            font-size: 10pt;
            line-height: 1.6;
            color: #2d3748;
        }}
        h1 {{
            font-size: 18pt;
            color: #1a365d;
            border-bottom: 2px solid #2c5282;
            padding-bottom: 8px;
            margin-top: 20px;
        }}
        h2 {{
            font-size: 13pt;
            color: #2c5282;
            margin-top: 16px;
            page-break-after: avoid;
        }}
        h3 {{
            font-size: 11pt;
            color: #3182ce;
            margin-top: 12px;
            margin-left: 10px;
            page-break-after: avoid;
        }}
        p {{
            margin: 6px 0;
            margin-left: 10px;
        }}
        ul, ol {{
            margin-left: 30px;
            margin-top: 4px;
            margin-bottom: 8px;
        }}
        li {{
            margin: 3px 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
            font-size: 9pt;
            page-break-inside: avoid;
        }}
        th {{
            background: #edf2f7;
            color: #1a365d;
            font-weight: bold;
            padding: 8px 6px;
            border: 1px solid #cbd5e0;
            text-align: left;
        }}
        td {{
            padding: 6px;
            border: 1px solid #cbd5e0;
            vertical-align: top;
        }}
        tr:nth-child(even) td {{
            background: #f7fafc;
        }}
        pre {{
            background: #f7fafc;
            border: 1px solid #e2e8f0;
            padding: 10px;
            font-size: 8pt;
            overflow-x: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        code {{
            font-family: "SFMono-Regular", Consolas, monospace;
        }}
        .meta {{
            text-align: center;
            color: #718096;
            font-size: 9pt;
            margin-bottom: 20px;
        }}
        .evidence-tag {{
            font-weight: bold;
            padding: 1px 4px;
            border-radius: 2px;
        }}
        .tag-fact {{ background: #c6f6d5; color: #22543d; }}
        .tag-inference {{ background: #bee3f8; color: #2a4365; }}
        .tag-scenario {{ background: #fed7d7; color: #742a2a; }}
    </style>
</head>
<body>
    <h1 style="text-align: center; border-bottom: none;">{html.escape(title)}</h1>
    <p class="meta">生成时间: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</p>
"""]
    
    skipped_title = False
    
    for block in blocks:
        kind = block["type"]
        
        if kind == "heading":
            level = min(block.get("level", 1), 6)
            text = clean_text_for_pdf(block.get("text", ""))
            number = block.get("number", "")
            
            if level == 1 and not skipped_title:
                if text.lower().strip() == title.lower().strip():
                    skipped_title = True
                    continue
            
            if number and level > 1:
                text = f"{number}. {text}"
            
            html_parts.append(f"<h{level}>{html.escape(text)}</h{level}>")
        
        elif kind == "paragraph":
            text = clean_text_for_pdf(block.get("text", ""))
            html_parts.append(f"<p>{html.escape(text)}</p>")
        
        elif kind == "list":
            tag = "ol" if block.get("ordered") else "ul"
            html_parts.append(f"<{tag}>")
            for item in block.get("items", []):
                text = clean_text_for_pdf(item)
                html_parts.append(f"<li>{html.escape(text)}</li>")
            html_parts.append(f"</{tag}>")
        
        elif kind == "code":
            html_parts.append(f"<pre><code>{html.escape(block.get('text', ''))}</code></pre>")
        
        elif kind == "table":
            rows = normalize_table_rows(block.get("rows", []))
            if not rows:
                continue
            
            html_parts.append("<table>")
            html_parts.append("<thead><tr>")
            for cell in rows[0]:
                html_parts.append(f"<th>{html.escape(clean_text_for_pdf(cell))}</th>")
            html_parts.append("</tr></thead>")
            
            html_parts.append("<tbody>")
            for row in rows[1:]:
                html_parts.append("<tr>")
                for cell in row:
                    html_parts.append(f"<td>{html.escape(clean_text_for_pdf(cell))}</td>")
                html_parts.append("</tr>")
            html_parts.append("</tbody></table>")
    
    html_parts.append("</body></html>")
    html_content = "\n".join(html_parts)
    
    HTML(string=html_content).write_pdf(str(output_path))


def render_pdf(
    analysis_md_path: str,
    output_path: str,
    title: str | None = None,
    engine: str = "auto",
) -> str:
    """
    Main entry point for PDF rendering.
    
    Returns the engine used.
    """
    source_path = Path(analysis_md_path)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    markdown_text = source_path.read_text(encoding="utf-8", errors="ignore")
    blocks = parse_markdown_blocks(markdown_text)
    
    if not title:
        title = infer_title(blocks, source_path.stem.replace("-", " ").strip() or "政策解读报告")
    
    if engine == "auto":
        if HAS_REPORTLAB:
            engine = "reportlab"
        elif HAS_WEASYPRINT:
            engine = "weasyprint"
        else:
            raise ImportError("No PDF engine available. Install reportlab or weasyprint.")
    
    if engine == "reportlab":
        render_pdf_with_reportlab(blocks, out_path, title)
    elif engine == "weasyprint":
        render_pdf_with_weasyprint(blocks, out_path, title)
    else:
        raise ValueError(f"Unknown engine: {engine}")
    
    return engine


def main() -> None:
    args = parse_args()
    
    engine = render_pdf(
        analysis_md_path=args.analysis_md,
        output_path=args.output,
        title=args.title,
        engine=args.engine,
    )
    
    print(f"Wrote PDF: {args.output}")
    print(f"Engine: {engine}")


if __name__ == "__main__":
    main()
