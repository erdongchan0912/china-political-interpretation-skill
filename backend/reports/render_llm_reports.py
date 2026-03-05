#!/usr/bin/env python3
"""
LLM-Powered Report Renderer for China Political Interpretation

This module uses LLM (Gemini) to generate:
1. Modern interactive HTML reports
2. Structured print-friendly PDF reports

The LLM generates the complete report content based on the analysis data.

Usage:
    python render_llm_reports.py \
        --analysis-json /tmp/analysis.json \
        --output-dir /tmp/reports \
        --base-name policy-brief
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Dict

# Add core directory to path for importing llm_client
CORE_DIR = Path(__file__).parent.parent / "core"
sys.path.insert(0, str(CORE_DIR))

# Import LLM client
try:
    from llm_client import LLMClient, AnalysisTask
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    print("Warning: LLM client not available.")

# Load environment variables
try:
    from dotenv import load_dotenv
    from pathlib import Path
    env_file = Path(__file__).parent.parent.parent / "config" / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate HTML and PDF reports using LLM."
    )
    parser.add_argument("--analysis-json", required=True, 
                       help="Input analysis JSON path.")
    parser.add_argument("--output-dir", required=True, 
                       help="Output directory for deliverables.")
    parser.add_argument("--base-name", default="policy-brief", 
                       help="Output file base name.")
    parser.add_argument("--title", help="Optional report title override.")
    parser.add_argument("--no-pdf", action="store_true", 
                       help="Skip PDF output generation.")
    parser.add_argument("--no-html", action="store_true", 
                       help="Skip HTML output generation.")
    parser.add_argument("--html-theme", default="auto",
                       choices=["light", "dark", "auto"],
                       help="Default HTML theme.")
    return parser.parse_args()


def load_analysis(path: str) -> Dict[str, Any]:
    """Load analysis data from JSON file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def clean_html_output(html_content: str, analysis: Optional[Dict[str, Any]] = None) -> str:
    """
    Clean LLM-generated HTML output.
    
    Args:
        html_content: The raw HTML content from LLM
        analysis: Optional analysis data for title correction
    """
    # Remove markdown code blocks if present
    html_content = re.sub(r'^```html?\s*\n?', '', html_content)
    html_content = re.sub(r'\n?```\s*$', '', html_content)
    
    # Ensure it starts with doctype or html tag
    if not html_content.strip().startswith('<!DOCTYPE') and not html_content.strip().startswith('<html'):
        html_content = '<!DOCTYPE html>\n<html lang="zh-CN">\n' + html_content
        if '</html>' not in html_content:
            html_content += '\n</html>'
    
    # [重要修复] 强制所有 <details> 标签默认展开
    def add_open_attr(match):
        tag = match.group(0)
        if 'open' not in tag.lower():
            return tag[:-1] + ' open>'
        return tag
    
    html_content = re.sub(r'<details[^>]*>', add_open_attr, html_content, flags=re.IGNORECASE)
    
    # [重要修复] 强制修正标题 - 确保使用原始标题
    if analysis:
        material = analysis.get("material_understanding", {})
        original_title = material.get("original_title", "")
        publish_date = material.get("publish_date", "")
        
        if original_title:
            # 构建正确的标题格式
            if publish_date:
                correct_title = f"{publish_date} 《{original_title}》解读"
            else:
                correct_title = f"《{original_title}》解读"
            
            # 替换 <h1> 标签中的标题
            def replace_h1_title(match):
                attrs = match.group(1) or ""
                # 保留属性但替换内容
                return f"<h1{attrs}>{correct_title}</h1>"
            
            html_content = re.sub(
                r'<h1([^>]*)>.*?</h1>',
                replace_h1_title,
                html_content,
                count=1,  # 只替换第一个 h1
                flags=re.IGNORECASE | re.DOTALL
            )
            
            # 替换 <title> 标签中的标题
            html_content = re.sub(
                r'<title>.*?</title>',
                f'<title>{correct_title}</title>',
                html_content,
                count=1,
                flags=re.IGNORECASE | re.DOTALL
            )
    
    return html_content.strip()


def clean_markdown_output(md_content: str) -> str:
    """Clean LLM-generated markdown output."""
    # Remove markdown code blocks if present
    md_content = re.sub(r'^```markdown?\s*\n?', '', md_content)
    md_content = re.sub(r'\n?```\s*$', '', md_content)
    return md_content.strip()


async def generate_html_report(
    analysis: Dict[str, Any],
    theme: str = "auto",
    progress_callback: Optional[callable] = None,
) -> str:
    """
    Generate modern interactive HTML report using LLM.
    """
    client = LLMClient()
    
    try:
        if progress_callback:
            progress_callback("generating_html", "大模型正在生成HTML报告...")
        
        print("\n[LLM] 正在生成现代化HTML报告...")
        
        # 设计规范文档（独立变量避免f-string大括号冲突）
        DESIGN_SPEC = '''
## 执行摘要区域设计规范

### HTML结构
<section class="executive-summary">
  <div class="summary-header">
    <h2>执行摘要：[一句话标题]</h2>
  </div>
  <div class="summary-grid">
    <div class="summary-column">
      <h3 class="column-title title-conclusions">核心结论</h3>
      <ul class="summary-list">
        <li><span class="icon icon-dot yellow"></span>结论内容...</li>
        <li><span class="icon icon-dot yellow"></span>结论内容...</li>
      </ul>
    </div>
    <div class="summary-column">
      <h3 class="column-title title-risks">关键风险</h3>
      <ul class="summary-list">
        <li><span class="icon icon-triangle red"></span>风险内容...</li>
        <li><span class="icon icon-triangle red"></span>风险内容...</li>
      </ul>
    </div>
    <div class="summary-column">
      <h3 class="column-title title-actions">行动建议</h3>
      <ul class="summary-list">
        <li><span class="icon icon-check green"></span>建议内容...</li>
        <li><span class="icon icon-check green"></span>建议内容...</li>
      </ul>
    </div>
  </div>
  <div class="summary-footer">
    <p>"一句话总结全文核心观点..."</p>
  </div>
</section>

### CSS样式（必须完整包含）
.executive-summary {
  background: linear-gradient(135deg, #1a2744 0%, #0f172a 100%);
  border-left: 4px solid #dc2626;
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 32px;
}
.summary-header h2 {
  color: #fff;
  font-size: 1.5rem;
  margin-bottom: 24px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.summary-header h2::before {
  content: "";
  width: 4px;
  height: 24px;
  background: #dc2626;
  border-radius: 2px;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}
.summary-column { padding: 0 16px; }
.column-title {
  font-size: 0.875rem;
  font-weight: 600;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}
.title-conclusions { color: #fbbf24; }
.title-risks { color: #f87171; }
.title-actions { color: #4ade80; }
.summary-list { list-style: none; padding: 0; margin: 0; }
.summary-list li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 12px;
  color: rgba(255,255,255,0.9);
  font-size: 0.9rem;
  line-height: 1.5;
}
.icon { flex-shrink: 0; margin-top: 4px; }
.icon-dot { width: 8px; height: 8px; border-radius: 50%; }
.icon-dot.yellow { background: #fbbf24; }
.icon-triangle { width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-bottom: 8px solid; }
.icon-triangle.red { border-bottom-color: #f87171; }
.icon-check::before { content: "✓"; font-weight: bold; }
.icon-check.green { color: #4ade80; }
.summary-footer {
  margin-top: 24px;
  padding: 16px;
  background: rgba(255,255,255,0.05);
  border-radius: 8px;
}
.summary-footer p {
  color: rgba(255,255,255,0.8);
  font-style: italic;
  margin: 0;
  text-align: center;
}

## 政策演进时间轴设计规范

### HTML结构
<section class="timeline-section">
  <h2>政策演进时间轴</h2>
  <div class="timeline-container">
    <div class="timeline-item">
      <div class="timeline-marker"></div>
      <div class="timeline-content">
        <span class="timeline-date">2023年1月</span>
        <h3 class="timeline-title">事件标题</h3>
        <p class="timeline-desc">事件描述...</p>
      </div>
    </div>
    <!-- 更多时间节点 -->
  </div>
</section>

### CSS样式
.timeline-section { margin: 32px 0; }
.timeline-section h2 { color: var(--text-primary); margin-bottom: 24px; }
.timeline-container {
  position: relative;
  padding-left: 40px;
  border-left: 2px solid rgba(59, 130, 246, 0.3);
}
.timeline-item {
  position: relative;
  padding: 16px 0 32px 24px;
}
.timeline-marker {
  position: absolute;
  left: -41px;
  top: 20px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--bg-primary);
  border: 3px solid #3b82f6;
}
.timeline-date { color: #3b82f6; font-size: 0.875rem; font-weight: 600; }
.timeline-title { color: var(--text-primary); font-size: 1.1rem; margin: 8px 0; }
.timeline-desc { color: var(--text-secondary); font-size: 0.9rem; line-height: 1.6; }

## 词汇变化热力图设计规范

### HTML结构
<section class="heatmap-section">
  <h2>词汇变化热力图 (动态年份范围)</h2>
  <table class="heatmap-table">
    <thead>
      <tr>
        <th>核心词汇/概念</th>
        <th>2024 (确立)</th>
        <th>2025 (过渡)</th>
        <th>2026 (变革)</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>媒体融合发展 → 系统性变革</td>
        <td class="heat-low">提及</td>
        <td class="heat-medium">深化</td>
        <td class="heat-high">重塑</td>
      </tr>
    </tbody>
  </table>
  <p class="heatmap-note">注：颜色越深代表该概念在政策文件中的优先级与强制性越高。</p>
</section>

### CSS样式
.heatmap-section { margin: 32px 0; }
.heatmap-table { width: 100%; border-collapse: collapse; }
.heatmap-table th, .heatmap-table td {
  padding: 12px 16px;
  text-align: center;
  border: 1px solid rgba(255,255,255,0.1);
}
.heatmap-table th {
  background: rgba(59, 130, 246, 0.2);
  color: var(--text-primary);
  font-weight: 600;
}
.heatmap-table td:first-child { text-align: left; color: var(--text-secondary); }
.heat-low { background: rgba(59, 130, 246, 0.15); color: var(--text-secondary); }
.heat-medium { background: rgba(59, 130, 246, 0.4); color: #fff; }
.heat-high { background: rgba(59, 130, 246, 0.7); color: #fff; font-weight: 600; }

## 证据引用与参考来源设计规范

### HTML结构
<details class="references-section" open>
  <summary>附录：证据引用与参考来源</summary>
  <table class="references-table">
    <thead>
      <tr>
        <th>来源标题</th>
        <th>权威等级</th>
        <th>核心摘要</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><a href="URL" target="_blank" class="ref-link">文章标题</a></td>
        <td><span class="tier-badge tier-t1">T1</span></td>
        <td class="ref-summary">摘要内容...</td>
      </tr>
    </tbody>
  </table>
</details>

### CSS样式
.references-section { margin: 32px 0; }
.references-section summary {
  cursor: pointer;
  font-size: 1.1rem;
  font-weight: 600;
  color: #f87171;
  padding: 16px;
  background: var(--card-bg);
  border-radius: 8px;
}
.references-table { width: 100%; margin-top: 16px; border-collapse: collapse; }
.references-table th, .references-table td {
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}
.references-table th { color: var(--text-muted); font-weight: 500; }
.ref-link { color: #f472b6; text-decoration: none; }
.ref-link:hover { text-decoration: underline; }
.tier-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}
.tier-t0 { background: linear-gradient(135deg, #fbbf24, #a855f7); color: #000; }
.tier-t1 { background: rgba(74, 222, 128, 0.2); color: #4ade80; border: 1px solid #4ade80; }
.tier-t2 { background: rgba(59, 130, 246, 0.2); color: #3b82f6; border: 1px solid #3b82f6; }
.tier-t3 { background: rgba(156, 163, 175, 0.2); color: #9ca3af; border: 1px solid #9ca3af; }
.ref-summary { color: var(--text-secondary); font-size: 0.9rem; }

## 主题切换支持

### CSS变量（深色主题 - 默认）
:root {
  --bg-primary: #0f172a;
  --bg-secondary: #1e293b;
  --card-bg: rgba(30, 41, 59, 0.8);
  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --accent-color: #dc2626;
  --tech-color: #00d4aa;
}

### CSS变量（浅色主题）
:root.light {
  --bg-primary: #ffffff;
  --bg-secondary: #f1f5f9;
  --card-bg: rgba(255, 255, 255, 0.9);
  --text-primary: #0f172a;
  --text-secondary: #475569;
  --text-muted: #94a3b8;
}
.light .executive-summary {
  background: linear-gradient(135deg, #e0e7ff 0%, #f1f5f9 100%);
  border-left-color: #dc2626;
}
.light .summary-list li { color: #334155; }
.light .summary-footer { background: rgba(0,0,0,0.03); }
.light .summary-footer p { color: #475569; }

### 主题切换按钮
<button id="theme-toggle" onclick="document.documentElement.classList.toggle(\'light\')">
  <span class="theme-icon">🌙</span>
</button>
'''

        # Build comprehensive prompt for HTML generation
        prompt = f"""你是一位专业的前端开发者和中国政治分析专家。请基于以下分析数据生成一个现代化、可交互的 HTML 政治分析报告。

## 分析数据
```json
{json.dumps(analysis, ensure_ascii=False, indent=2)}
```

## 核心设计要求（必须严格遵循）

### 1. 报告标题
- 格式：「[YYYY年M月D日] 《原始文章标题》解读」
- 从 material_understanding.original_title 获取标题
- 从 material_understanding.publish_date 获取日期

### 2. 执行摘要区域（最重要！）
必须严格按照以下规范实现：
- 深蓝渐变背景：linear-gradient(135deg, #1a2744 0%, #0f172a 100%)
- 左侧红色竖线装饰：4px solid #dc2626
- 三列等宽布局（Grid）：核心结论 | 关键风险 | 行动建议
- 核心结论：黄色圆点标记（#fbbf24）
- 关键风险：红色三角形标记（#f87171）
- 行动建议：绿色对勾标记（#4ade80）
- 底部单独一行：显示一句话总结（浅色背景）

### 3. 政策演进时间轴
- 垂直时间轴布局
- 左侧蓝色圆形节点（#3b82f6，带描边）
- 日期标签为蓝色
- 每个节点包含：日期 + 标题 + 描述
- 由你根据搜集到的信息自行整理生成时间节点

### 4. 词汇变化热力图
- 表格形式展示
- 第一列为关键词/概念
- 后续列为不同年份（根据数据动态生成年份范围）
- 使用蓝色深浅表示强度（浅=低优先级、深=高优先级）
- 表头带年份和状态标签

### 5. 证据引用与参考来源
- 可折叠区域（默认展开，必须有 open 属性）
- 表格形式：来源标题 | 权威等级 | 核心摘要
- 来源标题为粉红色可点击链接（#f472b6）
- 权威等级彩色标签：T0=金紫渐变, T1=绿色, T2=蓝色, T3=灰色

### 6. 主题支持
- 默认主题：{theme}
- 必须支持深色/浅色主题切换
- 右上角添加主题切换按钮

### 7. 其他必须包含的章节
- 核心判断（带证据标签）
- 政策意图分析
- 制度地图
- 权力信号
- 语义变化分析
- 风险情景
- 商业影响

### 8. 🔴 分领域分析展示（极其重要！）
如果 policy_analysis 中包含 "chunked_analysis": true，表示这是一篇经过自动切片的长文档（如政府工作报告），其分析结果存储在 per_domain_results 数组中。你必须：
- **遍历 per_domain_results 中的每一个领域**，为每个领域生成一个独立的分析卡片
- 每个领域卡片必须包含：领域标题（_domain）+ 核心判断 + 政策意图 + 具体政策变化列表 + 量化指标
- **绝对不能遗漏任何一个领域！** 如果有10个领域就必须展示10个
- 使用卡片式布局，每个领域用不同颜色的左侧竖线标记
- 在"核心领域判断与政策意图"这个大章节下，按领域逐一展开
- 每个领域的 policy_changes 要完整列出，不要只取前几条

## 设计规范参考
{DESIGN_SPEC}

## 技术要求
- 完整的 HTML 文档，所有 CSS 和 JS 内联
- 响应式设计，支持移动端
- 平滑滚动效果
- 回到顶部按钮

请直接输出完整的 HTML 代码，不要使用代码块包裹："""

        # 直接使用自定义prompt调用LLM（不使用预设任务模板）
        html_content = await client._call_gemini(prompt)
        
        if not html_content:
            print("[LLM] 警告: HTML生成失败，尝试备用方案...")
            result = await client.analyze(
                AnalysisTask.GENERATE_HTML_REPORT,
                context={"analysis_data": json.dumps(analysis, ensure_ascii=False, indent=2)}
            )
            html_content = result.get("html", "")
        
        html_content = clean_html_output(html_content, analysis)  # 传入 analysis 以修正标题
        print("[LLM] HTML报告生成完成")
        
        return html_content
        
    finally:
        await client.close()


async def generate_pdf_content(
    analysis: Dict[str, Any],
    progress_callback: Optional[callable] = None,
) -> str:
    """
    Generate structured PDF content using LLM.
    Returns markdown that will be converted to PDF.
    """
    client = LLMClient()
    
    try:
        if progress_callback:
            progress_callback("generating_pdf", "大模型正在生成PDF内容...")
        
        print("\n[LLM] 正在生成结构化PDF内容...")
        
        result = await client.analyze(
            AnalysisTask.GENERATE_PDF_CONTENT,
            context={"analysis_data": json.dumps(analysis, ensure_ascii=False, indent=2)}
        )
        
        md_content = result.get("markdown", "")
        md_content = clean_markdown_output(md_content)
        print("[LLM] PDF内容生成完成")
        
        return md_content
        
    finally:
        await client.close()


def markdown_to_html(markdown_content: str) -> str:
    """Convert markdown to styled HTML using markdown library."""
    try:
        import markdown
        from markdown.extensions.tables import TableExtension
        from markdown.extensions.fenced_code import FencedCodeExtension
        
        md = markdown.Markdown(extensions=[
            TableExtension(),
            FencedCodeExtension(),
            'nl2br',
        ])
        return md.convert(markdown_content)
    except ImportError:
        # Fallback to basic conversion
        import re
        
        content = markdown_content
        
        # Headers
        content = re.sub(r'^# (.+)$', r'<h1>\1</h1>', content, flags=re.MULTILINE)
        content = re.sub(r'^## (.+)$', r'<h2>\1</h2>', content, flags=re.MULTILINE)
        content = re.sub(r'^### (.+)$', r'<h3>\1</h3>', content, flags=re.MULTILINE)
        content = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', content, flags=re.MULTILINE)
        
        # Bold and italic
        content = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', content)
        content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
        content = re.sub(r'\*(.+?)\*', r'<em>\1</em>', content)
        
        # Code
        content = re.sub(r'`([^`]+)`', r'<code>\1</code>', content)
        
        # Lists
        content = re.sub(r'^- (.+)$', r'<li>\1</li>', content, flags=re.MULTILINE)
        
        # Paragraphs
        paragraphs = content.split('\n\n')
        processed = []
        for p in paragraphs:
            p = p.strip()
            if not p:
                continue
            if not any(p.startswith(tag) for tag in ['<h', '<ul', '<ol', '<li', '<tab', '<pre', '<code']):
                p = f'<p>{p}</p>'
            processed.append(p)
        
        return '\n'.join(processed)


def markdown_to_pdf(markdown_content: str, output_path: Path, title: str = "政治分析报告") -> bool:
    """
    Convert markdown content to PDF using available tools.
    """
    # Try WeasyPrint first (better HTML rendering)
    try:
        import weasyprint
        
        # Convert markdown to HTML
        html_body = markdown_to_html(markdown_content)
        
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        @page {{
            size: A4;
            margin: 2cm;
        }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; 
            line-height: 1.6;
            color: #333;
        }}
        h1 {{ font-size: 22pt; margin-bottom: 16pt; color: #1a365d; border-bottom: 2px solid #1a365d; padding-bottom: 8pt; }}
        h2 {{ font-size: 16pt; margin-top: 20pt; margin-bottom: 10pt; color: #2b6cb0; }}
        h3 {{ font-size: 13pt; margin-top: 16pt; margin-bottom: 8pt; color: #2d3748; }}
        h4 {{ font-size: 11pt; margin-top: 12pt; margin-bottom: 6pt; color: #4a5568; }}
        p {{ font-size: 10pt; margin-bottom: 8pt; text-align: justify; }}
        ul, ol {{ margin-left: 16pt; margin-bottom: 8pt; }}
        li {{ font-size: 10pt; margin-bottom: 4pt; }}
        table {{ border-collapse: collapse; width: 100%; margin: 12pt 0; font-size: 9pt; }}
        th, td {{ border: 1px solid #e2e8f0; padding: 8pt; text-align: left; }}
        th {{ background-color: #edf2f7; font-weight: bold; }}
        code {{ background-color: #f7fafc; padding: 2pt 4pt; border-radius: 2pt; font-size: 9pt; }}
        pre {{ background-color: #f7fafc; padding: 12pt; border-radius: 4pt; overflow-x: auto; font-size: 9pt; }}
        strong {{ color: #1a365d; }}
    </style>
</head>
<body>
{html_body}
</body>
</html>"""
        
        weasyprint.HTML(string=html_content).write_pdf(str(output_path))
        return True
        
    except ImportError:
        print("WeasyPrint not available, trying ReportLab...")
    except Exception as e:
        print(f"WeasyPrint PDF generation failed: {e}")

    # Fallback to ReportLab with proper Markdown rendering
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            PageBreak, ListFlowable, ListItem
        )
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import re
        
        # Try to register Chinese font
        font_name = "Helvetica"
        try:
            import platform
            if platform.system() == "Darwin":  # macOS
                # macOS font paths - try multiple locations
                font_paths = [
                    "/System/Library/Fonts/STHeiti Light.ttc",
                    "/System/Library/Fonts/STHeiti Medium.ttc", 
                    "/Library/Fonts/Arial Unicode.ttf",
                    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                    "/System/Library/Fonts/Hiragino Sans GB.ttc",
                ]
            else:
                font_paths = [
                    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
                    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                    "C:/Windows/Fonts/msyh.ttc",
                    "C:/Windows/Fonts/simsun.ttc",
                ]
            
            for font_path in font_paths:
                if Path(font_path).exists():
                    try:
                        pdfmetrics.registerFont(TTFont("ChineseFont", font_path, subfontIndex=0))
                        font_name = "ChineseFont"
                        print(f"  Using Chinese font: {font_path}")
                        break
                    except Exception as e:
                        print(f"  Font registration failed for {font_path}: {e}")
                        continue
        except Exception as e:
            print(f"  Font detection failed: {e}")
        
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm,
        )
        
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name='ChineseTitle', fontName=font_name, fontSize=18,
            leading=24, spaceAfter=12, textColor=colors.HexColor('#1a365d'),
        ))
        styles.add(ParagraphStyle(
            name='ChineseHeading', fontName=font_name, fontSize=14,
            leading=18, spaceAfter=8, spaceBefore=12, textColor=colors.HexColor('#2b6cb0'),
        ))
        styles.add(ParagraphStyle(
            name='ChineseSubHeading', fontName=font_name, fontSize=12,
            leading=16, spaceAfter=6, spaceBefore=10, textColor=colors.HexColor('#2d3748'),
        ))
        styles.add(ParagraphStyle(
            name='ChineseBody', fontName=font_name, fontSize=10,
            leading=14, spaceAfter=6,
        ))
        styles.add(ParagraphStyle(
            name='ChineseBullet', fontName=font_name, fontSize=10,
            leading=14, spaceAfter=4, leftIndent=20,
        ))
        
        def md_to_reportlab(text):
            """Convert markdown inline formatting to ReportLab HTML."""
            # Bold: **text** -> <b>text</b>
            text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
            # Italic: *text* -> <i>text</i>
            text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
            # Code: `text` -> <font name="Courier">text</font>
            text = re.sub(r'`([^`]+)`', r'<font name="Courier">\1</font>', text)
            # Links: [text](url) -> <link href="url">text</link>
            text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<link href="\2">\1</link>', text)
            return text
        
        story = []
        # 不在这里添加标题，因为 markdown 内容已经包含标题
        # story.append(Paragraph(title, styles['ChineseTitle']))
        # story.append(Spacer(1, 12))
        
        # Process markdown line by line
        lines = markdown_content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                story.append(Spacer(1, 6))
                i += 1
                continue
            
            # Handle tables
            if line.startswith('|') and '|' in line[1:]:
                table_lines = []
                while i < len(lines) and lines[i].strip().startswith('|'):
                    if not re.match(r'^\|[-:\s|]+\|$', lines[i].strip()):  # Skip separator
                        table_lines.append([cell.strip() for cell in lines[i].strip().split('|')[1:-1]])
                    i += 1
                
                if table_lines:
                    t = Table(table_lines)
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#edf2f7')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a365d')),
                        ('FONTNAME', (0, 0), (-1, 0), font_name),
                        ('FONTSIZE', (0, 0), (-1, -1), 9),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                        ('TOPPADDING', (0, 0), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                        ('FONTNAME', (0, 1), (-1, -1), font_name),
                    ]))
                    story.append(t)
                    story.append(Spacer(1, 12))
                continue
            
            # Handle headers
            if line.startswith('# '):
                story.append(Paragraph(md_to_reportlab(line[2:]), styles['ChineseTitle']))
            elif line.startswith('## '):
                story.append(Paragraph(md_to_reportlab(line[3:]), styles['ChineseHeading']))
            elif line.startswith('### '):
                story.append(Paragraph(md_to_reportlab(line[4:]), styles['ChineseSubHeading']))
            elif line.startswith('#### '):
                story.append(Paragraph(md_to_reportlab(line[5:]), styles['ChineseSubHeading']))
            # Handle lists
            elif line.startswith('- ') or line.startswith('* '):
                story.append(Paragraph(f"• {md_to_reportlab(line[2:])}", styles['ChineseBullet']))
            elif re.match(r'^\d+\.\s', line):
                text = re.sub(r'^\d+\.\s', '', line)
                story.append(Paragraph(f"• {md_to_reportlab(text)}", styles['ChineseBullet']))
            # Regular paragraph
            else:
                story.append(Paragraph(md_to_reportlab(line), styles['ChineseBody']))
            
            i += 1
        
        doc.build(story)
        return True
        
    except ImportError:
        print("ReportLab not available")
    except Exception as e:
        print(f"ReportLab PDF generation failed: {e}")
    
    # Save as markdown if PDF generation fails
    md_path = output_path.with_suffix('.md')
    md_path.write_text(markdown_content, encoding='utf-8')
    print(f"PDF generation failed, saved as markdown: {md_path}")
    return False


def generate_fallback_markdown(analysis: Dict[str, Any]) -> str:
    """
    Generate a fallback markdown document from analysis data.
    Used when LLM-powered PDF generation fails.
    """
    lines = []
    title = analysis.get("title", "政策分析报告")
    lines.append(f"# {title}")
    lines.append("")
    
    # Executive summary
    summary = analysis.get("executive_summary", {})
    if summary:
        lines.append("## 执行摘要")
        if summary.get("one_liner"):
            lines.append(f"**一句话总结**: {summary['one_liner']}")
            lines.append("")
        
        if summary.get("core_conclusions"):
            lines.append("### 核心结论")
            for c in summary["core_conclusions"]:
                lines.append(f"- {c}")
            lines.append("")
        
        if summary.get("key_risks"):
            lines.append("### 关键风险")
            for r in summary["key_risks"]:
                lines.append(f"- {r}")
            lines.append("")
    
    # Policy analysis
    policy = analysis.get("policy_analysis", {})
    if policy:
        lines.append("## 政策分析")
        
        if policy.get("core_judgments"):
            lines.append("### 核心判断")
            for j in policy["core_judgments"]:
                tag = f"[{j.get('evidence_type', 'I')}]"
                lines.append(f"- {tag} {j.get('judgment', '')}")
            lines.append("")
        
        intent = policy.get("policy_intent", {})
        if intent:
            lines.append("### 政策意图")
            if intent.get("explicit_goals"):
                lines.append(f"**显性目标**: {', '.join(intent['explicit_goals'])}")
            if intent.get("implicit_goals"):
                lines.append(f"**隐性目标**: {', '.join(intent['implicit_goals'])}")
            lines.append("")
    
    # Risk scenarios
    scenarios = analysis.get("risk_scenarios", {})
    if scenarios and scenarios.get("scenarios"):
        lines.append("## 风险情景")
        for s in scenarios["scenarios"]:
            lines.append(f"### {s.get('name', '情景')} ({s.get('type', '')})")
            lines.append(f"- 概率: {s.get('probability', '')}")
            lines.append(f"- 影响: {s.get('impact_assessment', '')}")
            lines.append("")
    
    # Business impact
    business = analysis.get("business_impact", {})
    if business:
        lines.append("## 商业影响")
        if business.get("winners"):
            lines.append("### 受益行业")
            for w in business["winners"]:
                lines.append(f"- **{w.get('sector', '')}**: {w.get('reason', '')}")
            lines.append("")
        
        if business.get("losers"):
            lines.append("### 受损行业")
            for l in business["losers"]:
                lines.append(f"- **{l.get('sector', '')}**: {l.get('reason', '')}")
            lines.append("")
    
    # Reference sources
    refs = analysis.get("reference_sources", {})
    if refs:
        lines.append("## 参考资料")
        
        horizontal = refs.get("horizontal", [])
        if horizontal:
            lines.append("### 横向检索资料")
            for r in horizontal[:10]:
                tier = r.get("tier", "T3")
                lines.append(f"- [{tier}] {r.get('title', '')} ({r.get('domain', '')})")
            lines.append("")
        
        vertical = refs.get("vertical", [])
        if vertical:
            lines.append("### 纵向检索资料")
            for r in vertical[:10]:
                tier = r.get("tier", "T3")
                lines.append(f"- [{tier}] {r.get('title', '')} ({r.get('domain', '')})")
            lines.append("")
    
    # Metadata
    lines.append("---")
    lines.append(f"*生成时间: {analysis.get('generated_at', '')}*")
    
    return "\n".join(lines)


async def async_main(args: argparse.Namespace) -> None:
    """Async main function for LLM-powered report generation."""
    # Load analysis data
    analysis = load_analysis(args.analysis_json)
    title = args.title or analysis.get("title", "中国政治分析报告")
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n分析主题: {analysis.get('topic', 'N/A')}")
    print(f"LLM模型: {analysis.get('llm_model', 'N/A')}")
    
    # Check if LLM is available
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    if not LLM_AVAILABLE or not api_key:
        print("\n⚠️  LLM API Key 未配置，无法使用LLM生成报告")
        print("请配置 LLM_API_KEY 或 GEMINI_API_KEY 环境变量后重试")
        return
    
    print("\n" + "="*60)
    print("🤖 使用大模型生成报告")
    print("="*60)
    
    # Generate HTML report
    if not args.no_html:
        html_content = await generate_html_report(analysis, theme=args.html_theme)
        html_path = output_dir / f"{args.base_name}.html"
        html_path.write_text(html_content, encoding="utf-8")
        print(f"✅ HTML报告: {html_path}")
    
    # Generate PDF report
    if not args.no_pdf:
        pdf_path = output_dir / f"{args.base_name}.pdf"
        pdf_generated = False
        
        try:
            pdf_content = await generate_pdf_content(analysis)
            if pdf_content and len(pdf_content.strip()) > 100:
                pdf_generated = markdown_to_pdf(pdf_content, pdf_path, title)
        except Exception as e:
            print(f"⚠️  LLM生成PDF内容失败: {e}")
        
        # Fallback: Generate PDF directly from analysis data
        if not pdf_generated:
            print("🔄 尝试使用备用方案生成PDF...")
            fallback_md = generate_fallback_markdown(analysis)
            pdf_generated = markdown_to_pdf(fallback_md, pdf_path, title)
        
        if pdf_generated and pdf_path.exists() and pdf_path.stat().st_size > 0:
            print(f"✅ PDF报告: {pdf_path}")
        else:
            # Save markdown as final fallback
            md_path = output_dir / f"{args.base_name}_content.md"
            fallback_md = generate_fallback_markdown(analysis)
            md_path.write_text(fallback_md, encoding="utf-8")
            print(f"⚠️  PDF生成失败，已保存Markdown: {md_path}")
    
    print(f"\n✅ 报告生成完成: {output_dir.resolve()}")


def main() -> None:
    args = parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
