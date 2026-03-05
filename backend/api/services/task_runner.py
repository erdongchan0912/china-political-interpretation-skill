#!/usr/bin/env python3
"""
Task runner for LLM-powered analysis pipeline.

This module orchestrates the complete analysis flow:
1. Content extraction (URL/PDF/Image)
2. LLM-powered material understanding
3. LLM-generated search strategy
4. Context retrieval
5. LLM deep analysis
6. LLM report generation (HTML + PDF)
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

# Add backend directories to path
BACKEND_DIR = Path(__file__).parent.parent.parent  # backend/
CORE_DIR = BACKEND_DIR / "core"
REPORTS_DIR = BACKEND_DIR / "reports"
PROJECT_ROOT = BACKEND_DIR.parent  # china-political-interpretation/

sys.path.insert(0, str(CORE_DIR))
sys.path.insert(0, str(REPORTS_DIR))

# For backward compatibility, SCRIPT_DIR points to core
SCRIPT_DIR = CORE_DIR

# Load environment variables
try:
    from dotenv import load_dotenv
    env_file = PROJECT_ROOT / "config" / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass


class TaskRunner:
    """Runs the complete LLM-powered analysis pipeline for a task."""
    
    STAGES = [
        ("识别文本", 10),
        ("🤖 LLM 理解材料", 20),
        ("🤖 LLM 生成检索策略", 30),
        ("搜索横向材料", 45),
        ("搜索纵向材料", 55),
        ("🤖 LLM 深度分析", 70),
        ("🤖 LLM 生成 HTML 报告", 85),
        ("🤖 LLM 生成 PDF 报告", 95),
        ("完成", 100),
    ]
    
    def __init__(self, task_id: str, task_data: dict[str, Any], output_dir: Path):
        self.task_id = task_id
        self.task_data = task_data
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self._result: dict[str, Any] = {}
        self._progress_callback: Callable[[str, int, str], None] | None = None
    
    def _report_progress(self, stage: str, progress: int, message: str = "") -> None:
        """Report progress to callback."""
        if self._progress_callback:
            self._progress_callback(stage, progress, message)
    
    async def _run_script(self, script_name: str, args: list[str], script_dir: Path | None = None) -> tuple[int, str, str]:
        """Run a Python script asynchronously."""
        # Use specified directory or default to CORE_DIR
        base_dir = script_dir if script_dir else CORE_DIR
        script_path = base_dir / script_name
        
        if not script_path.exists():
            return 1, "", f"Script not found: {script_path}"
        
        cmd = [sys.executable, str(script_path)] + args
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(base_dir),  # Use the script's directory as working directory
        )
        
        stdout, stderr = await process.communicate()
        
        return (
            process.returncode or 0,
            stdout.decode("utf-8", errors="ignore"),
            stderr.decode("utf-8", errors="ignore"),
        )
    
    async def _extract_content(self) -> str:
        """Extract content from uploaded files/URLs."""
        self._report_progress("识别文本", 5, "正在提取内容...")
        
        all_text_parts: list[str] = []
        
        for file_info in self.task_data.get("files", []):
            file_type = file_info.get("type", "")
            file_path = file_info.get("path", "")
            
            if not file_path:
                continue
            
            args = ["--output", str(self.output_dir / "extracted_content.txt")]
            
            if file_type == "url":
                args.extend(["--url", file_path])
                if self.task_data.get("force_browser"):
                    args.append("--force-browser")
                if self.task_data.get("force_ocr"):
                    args.append("--force-ocr")
            elif file_type == "pdf":
                args.extend(["--pdf", file_path])
            elif file_type == "image":
                args.extend(["--image", file_path])
            else:
                # Try to read as text
                try:
                    text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
                    all_text_parts.append(f"--- {file_info.get('filename', 'File')} ---\n{text}")
                    continue
                except Exception:
                    continue
            
            returncode, stdout, stderr = await self._run_script("content_extractor.py", args)
            
            if returncode == 0:
                output_file = self.output_dir / "extracted_content.txt"
                if output_file.exists():
                    text = output_file.read_text(encoding="utf-8", errors="ignore")
                    all_text_parts.append(
                        f"--- {file_info.get('filename', 'Source')} ---\n{text}"
                    )
            else:
                # Log but continue
                print(f"Warning: Content extraction failed for {file_path}: {stderr}")
        
        combined_text = "\n\n".join(all_text_parts)
        
        if not combined_text.strip():
            raise ValueError("No content could be extracted from the provided files/URLs")
        
        # Save combined content
        material_path = self.output_dir / "material.txt"
        material_path.write_text(combined_text, encoding="utf-8")
        
        self._report_progress("识别文本", 10, f"已提取 {len(combined_text)} 字符")
        return str(material_path)
    
    async def _build_query_matrix(self, material_path: str) -> str:
        """Build research query matrix using LLM."""
        self._report_progress("🤖 LLM理解材料", 12, "大模型正在理解材料内容...")
        
        output_path = self.output_dir / "query_matrix.json"
        
        args = [
            "--file", material_path,
            "--output", str(output_path),
        ]
        
        if self.task_data.get("topic"):
            args.extend(["--topic", self.task_data["topic"]])
        
        if self.task_data.get("user_focus"):
            args.extend(["--user-focus", self.task_data["user_focus"]])
        
        returncode, stdout, stderr = await self._run_script("build_research_queries.py", args)
        
        if returncode != 0:
            raise RuntimeError(f"Query matrix generation failed: {stderr}")
        
        # Check if LLM was used
        try:
            matrix = json.loads(output_path.read_text(encoding="utf-8"))
            if matrix.get("llm_powered"):
                self._report_progress("🤖 LLM生成检索策略", 25, "LLM智能检索策略已生成")
            else:
                self._report_progress("构建检索矩阵", 25, "检索矩阵已生成（规则模式）")
        except Exception:
            self._report_progress("构建检索矩阵", 25, "检索矩阵已生成")
        
        return str(output_path)
    
    async def _fetch_context(self, query_matrix_path: str) -> str:
        """Fetch context results."""
        self._report_progress("搜索横向材料", 30, "正在检索相关资料...")
        
        output_json = self.output_dir / "context_results.json"
        output_md = self.output_dir / "context_results.md"
        
        args = [
            "--queries-json", query_matrix_path,
            "--output", str(output_json),
            "--markdown", str(output_md),
        ]
        
        returncode, stdout, stderr = await self._run_script("fetch_context_results.py", args)
        
        if returncode != 0:
            # Not fatal, continue with whatever we have
            print(f"Warning: Context fetch partially failed: {stderr}")
        
        self._report_progress("搜索纵向材料", 55, "资料检索完成")
        return str(output_json)
    
    async def _generate_outline(
        self, material_path: str, query_matrix_path: str, context_results_path: str
    ) -> str:
        """Generate analysis using LLM."""
        self._report_progress("🤖 LLM深度分析", 60, "大模型正在进行深度政策分析...")
        
        # Output as JSON for LLM-powered analysis
        output_path = self.output_dir / "analysis.json"
        
        args = [
            "--material-file", material_path,
            "--query-matrix", query_matrix_path,
            "--context-results", context_results_path,
            "--output", str(output_path),
            "--output-format", "json",
        ]
        
        if self.task_data.get("topic"):
            args.extend(["--title", self.task_data["topic"]])
        
        if self.task_data.get("user_focus"):
            args.extend(["--user-focus", self.task_data["user_focus"]])
        
        returncode, stdout, stderr = await self._run_script("generate_analysis_outline.py", args)
        
        if returncode != 0:
            raise RuntimeError(f"Analysis generation failed: {stderr}")
        
        # Check if LLM was used
        try:
            analysis = json.loads(output_path.read_text(encoding="utf-8"))
            if analysis.get("llm_powered"):
                self._report_progress("🤖 LLM深度分析", 70, "LLM分析完成")
            else:
                self._report_progress("生成分析大纲", 70, "分析框架已生成")
        except Exception:
            self._report_progress("生成分析大纲", 70, "分析大纲已生成")
        
        return str(output_path)
    
    async def _render_reports(self, analysis_path: str) -> tuple[str, str]:
        """Render HTML and PDF reports using LLM."""
        self._report_progress("🤖 LLM生成HTML报告", 75, "大模型正在生成现代化HTML报告...")
        
        base_name = "policy-brief"
        html_path = self.output_dir / f"{base_name}.html"
        pdf_path = self.output_dir / f"{base_name}.pdf"
        
        # Check if we have JSON analysis (LLM-powered) or MD (fallback)
        is_json = analysis_path.endswith('.json')
        
        if is_json:
            # Use LLM report renderer
            args = [
                "--analysis-json", analysis_path,
                "--output-dir", str(self.output_dir),
                "--base-name", base_name,
            ]
            
            if self.task_data.get("topic"):
                args.extend(["--title", self.task_data["topic"]])
            
            returncode, stdout, stderr = await self._run_script(
                "render_llm_reports.py", args, script_dir=REPORTS_DIR
            )
            
            if returncode != 0:
                print(f"Warning: LLM report generation failed: {stderr}")
                # Try legacy fallback
                await self._render_legacy_reports(analysis_path, base_name)
        else:
            # Use legacy renderer for markdown
            await self._render_legacy_reports(analysis_path, base_name)
        
        self._report_progress("🤖 LLM生成PDF报告", 95, "报告生成完成")
        
        return str(html_path), str(pdf_path) if pdf_path.exists() else ""
    
    async def _render_legacy_reports(self, analysis_md_path: str, base_name: str) -> None:
        """Render reports using legacy methods (fallback)."""
        html_path = self.output_dir / f"{base_name}.html"
        pdf_path = self.output_dir / f"{base_name}.pdf"
        
        # Generate HTML
        try:
            from render_html_report import render_html
            render_html(
                analysis_md_path=analysis_md_path,
                output_path=str(html_path),
                title=self.task_data.get("topic"),
            )
        except Exception as e:
            print(f"Warning: HTML generation failed: {e}")
            # Fallback to legacy
            args = [
                "--analysis-md", analysis_md_path,
                "--output-dir", str(self.output_dir),
                "--base-name", base_name,
                "--no-pdf",
            ]
            await self._run_script("render_analysis_web_pdf.py", args)
        
        # Generate PDF
        try:
            from render_pdf_report import render_pdf
            render_pdf(
                analysis_md_path=analysis_md_path,
                output_path=str(pdf_path),
                title=self.task_data.get("topic"),
            )
        except Exception as e:
            print(f"Warning: PDF generation failed: {e}")
    
    async def run(
        self, on_progress: Callable[[str, int, str], None] | None = None
    ) -> dict[str, Any]:
        """Run the complete analysis pipeline."""
        self._progress_callback = on_progress
        
        try:
            # Stage 1: Extract content
            material_path = await self._extract_content()
            
            # Stage 2: Build query matrix
            query_matrix_path = await self._build_query_matrix(material_path)
            
            # Stage 3-4: Fetch context
            context_results_path = await self._fetch_context(query_matrix_path)
            
            # Stage 5: Generate outline
            analysis_md_path = await self._generate_outline(
                material_path, query_matrix_path, context_results_path
            )
            
            # Stage 6-7: Render reports
            html_path, pdf_path = await self._render_reports(analysis_md_path)
            
            # Read analysis data for summary
            summary_data = {}
            try:
                analysis_json_path = self.output_dir / "analysis.json"
                if analysis_json_path.exists():
                    import json
                    with open(analysis_json_path, 'r', encoding='utf-8') as f:
                        analysis_data = json.load(f)

                    # Extract executive_summary and key_findings for frontend display
                    exec_summary = analysis_data.get("executive_summary", {})
                    one_liner = ""
                    key_findings = []
                    if isinstance(exec_summary, dict):
                        one_liner = exec_summary.get("one_liner", "")
                        key_findings = exec_summary.get("core_conclusions", [])
                    elif isinstance(exec_summary, str):
                        one_liner = exec_summary

                    summary_data = {
                        "title": analysis_data.get("title"),
                        "token_usage": analysis_data.get("token_usage"),
                        "reference_count": analysis_data.get("reference_count"),
                        "executive_summary": one_liner,
                        "key_findings": key_findings[:5],
                    }
            except Exception as e:
                print(f"Warning: Failed to read analysis summary: {e}")

            # Resolve analysis_markdown path: LLM path produces analysis.json,
            # legacy path may produce analysis_outline.md.  Pick whichever exists.
            md_candidates = ["analysis.md", "analysis_outline.md"]
            md_path = ""
            md_exists = False
            for md_name in md_candidates:
                candidate = self.output_dir / md_name
                if candidate.exists():
                    md_path = str(candidate)
                    md_exists = True
                    break
            if not md_path:
                md_path = str(self.output_dir / "analysis_outline.md")

            md_basename = Path(md_path).name

            # Prepare result
            self._result = {
                "task_id": self.task_id,
                "success": True,
                "outputs": {
                    "html": {
                        "path": html_path,
                        "url": f"/outputs/{self.task_id}/policy-brief.html",
                        "exists": Path(html_path).exists() if html_path else False,
                    },
                    "pdf": {
                        "path": pdf_path,
                        "url": f"/outputs/{self.task_id}/policy-brief.pdf",
                        "exists": Path(pdf_path).exists() if pdf_path else False,
                    },
                    "analysis_json": {
                        "path": str(self.output_dir / "analysis.json"),
                        "url": f"/outputs/{self.task_id}/analysis.json",
                        "exists": (self.output_dir / "analysis.json").exists(),
                    },
                    "analysis_markdown": {
                        "path": md_path,
                        "url": f"/outputs/{self.task_id}/{md_basename}",
                        "exists": md_exists,
                    },
                    "query_matrix": {
                        "path": query_matrix_path,
                        "url": f"/outputs/{self.task_id}/query_matrix.json",
                        "exists": Path(query_matrix_path).exists(),
                    },
                },
                "download_urls": {
                    "html": f"/api/download/{self.task_id}/policy-brief.html",
                    "pdf": f"/api/download/{self.task_id}/policy-brief.pdf",
                },
                "summary": summary_data,
            }
            
            # Archive outputs to permanent, title-named folder
            # NOTE: Archive errors should NOT fail the entire task since reports are already generated
            try:
                self._archive_outputs(summary_data.get("title", ""), summary_data)
            except OSError as e:
                # Common on cloud-synced directories (OneDrive/iCloud) - [Errno 5] Input/output error
                print(f"⚠️  Archive failed (non-fatal): {e}")
                self._result["archive_warning"] = f"归档失败（报告已生成）: {e}"

            self._report_progress("完成", 100, "分析完成")
            return self._result
            
        except Exception as e:
            self._result = {
                "task_id": self.task_id,
                "success": False,
                "error": str(e),
            }
            raise
    
    def _archive_outputs(self, title: str, summary_data: dict[str, Any] | None = None) -> None:
        """Copy key outputs to a permanent, title-named archive folder.

        Folder structure:  ARCHIVE_DIR / YYYY-MM-DD_<title> /
            ├── policy-brief.html
            ├── policy-brief.pdf
            ├── source_material.md   ← original text as markdown
            └── analysis.json
        """
        import re
        import shutil
        from datetime import date

        archive_root = os.environ.get("ARCHIVE_DIR", "").strip()
        if not archive_root:
            # Default: ~/Documents/政策分析输出
            archive_root = str(Path.home() / "Documents" / "政策分析输出")

        archive_root = str(Path(archive_root).expanduser().resolve())

        # Sanitise title for filesystem
        safe_title = title.strip() if title else self.task_id
        # Remove characters illegal in most filesystems
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', safe_title)
        # Collapse multiple underscores / spaces
        safe_title = re.sub(r'[\s_]+', '_', safe_title).strip('_')
        # Truncate
        if len(safe_title) > 80:
            safe_title = safe_title[:80].rstrip('_')

        folder_name = f"{date.today().isoformat()}_{safe_title}"
        dest_dir = Path(archive_root) / folder_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Copy HTML
        html_src = self.output_dir / "policy-brief.html"
        if html_src.exists():
            shutil.copy2(html_src, dest_dir / "policy-brief.html")

        # Copy PDF
        pdf_src = self.output_dir / "policy-brief.pdf"
        if pdf_src.exists():
            shutil.copy2(pdf_src, dest_dir / "policy-brief.pdf")

        # Copy analysis JSON
        json_src = self.output_dir / "analysis.json"
        if json_src.exists():
            shutil.copy2(json_src, dest_dir / "analysis.json")

        # Convert material.txt → source_material.md (with markdown header)
        material_src = self.output_dir / "material.txt"
        if material_src.exists():
            raw_text = material_src.read_text(encoding="utf-8", errors="ignore")
            md_header = f"# {title or '原始材料'}\n\n"
            md_header += f"> 分析日期：{date.today().isoformat()}\n\n---\n\n"
            (dest_dir / "source_material.md").write_text(
                md_header + raw_text, encoding="utf-8"
            )

        # Also record archive path in result
        self._result["archive_path"] = str(dest_dir)

        # ── Append summary row to 分析记录.csv ──
        import csv
        csv_path = Path(archive_root) / "分析记录.csv"
        write_header = not csv_path.exists()

        sd = summary_data or {}
        row = {
            "日期": date.today().isoformat(),
            "标题": title or self.task_id,
            "执行摘要": sd.get("executive_summary", ""),
            "核心结论": " | ".join(
                (sd.get("key_findings") or [])[:3]
            ),
            "参考文献数": sd.get("reference_count", ""),
            "Token 用量": sd.get("token_usage", ""),
            "归档路径": str(dest_dir),
        }

        try:
            with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=row.keys())
                if write_header:
                    writer.writeheader()
                writer.writerow(row)
        except Exception as e:
            print(f"Warning: Failed to write CSV record: {e}")

        print(f"📁 Outputs archived to: {dest_dir}")

    def get_result(self) -> dict[str, Any]:
        """Get the analysis result."""
        return self._result
