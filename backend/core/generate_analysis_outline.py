#!/usr/bin/env python3
"""
Generate a comprehensive analysis outline for China political interpretation.

This module uses LLM (Gemini) to perform deep analysis:
1. Policy analysis with horizontal and vertical context
2. Semantic diff analysis comparing current and historical documents
3. Risk scenario analysis
4. Business impact analysis
5. Executive summary generation

Usage:
    python generate_analysis_outline.py \
        --material-file /path/to/material.txt \
        --query-matrix /tmp/query_matrix.json \
        --context-results /tmp/context_results.json \
        --output /tmp/analysis_outline.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Dict

# Import LLM client
try:
    from llm_client import (
        LLMClient,
        AnalysisTask,
        analyze_policy,
        analyze_semantic_diff,
        generate_risk_scenarios,
        analyze_business_impact,
        generate_executive_summary,
    )
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    print("Warning: LLM client not available. Using template-based fallback.")

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
        description="Generate a comprehensive LLM-powered analysis from material and retrieval context."
    )
    parser.add_argument("--material-file", help="Path to source material text file.")
    parser.add_argument("--material-text", help="Inline source material text.")
    parser.add_argument("--query-matrix", help="Optional query matrix JSON path.")
    parser.add_argument("--context-results", help="Optional retrieval results JSON path.")
    parser.add_argument("--title", help="Optional output title.")
    parser.add_argument("--output", help="Output JSON path. Prints to stdout if omitted.")
    parser.add_argument("--output-format", choices=["json", "markdown"], default="json",
                       help="Output format: json or markdown")
    parser.add_argument("--package-dir", help="Optional output directory for HTML/PDF package.")
    parser.add_argument(
        "--package-base-name",
        default="policy-brief",
        help="Base name for packaged markdown/html/pdf files.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM and use template-based fallback."
    )
    parser.add_argument(
        "--user-focus",
        default="",
        help="Optional user-provided analysis focus instruction."
    )
    return parser.parse_args()


def load_text(material_file: str | None, material_text: str | None) -> str:
    if material_file:
        return Path(material_file).read_text(encoding="utf-8", errors="ignore")
    if material_text:
        return material_text
    raise ValueError("Provide --material-file or --material-text.")


def load_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def extract_horizontal_context(context_results: Dict[str, Any]) -> str:
    """Extract horizontal context from retrieval results."""
    lines = []
    for run in context_results.get("query_runs", []):
        if run.get("type") == "horizontal":
            lines.append(f"\n### {run.get('intent', '横向来源')}")
            for item in run.get("items", [])[:5]:
                lines.append(f"- [{item.get('source_tier', 'T3')}] {item.get('title', '')} ({item.get('domain', '')})")
                if item.get("snippet"):
                    lines.append(f"  摘要: {item.get('snippet', '')[:200]}...")
    
    if not lines:
        return "暂无横向检索结果"
    return "\n".join(lines)


def extract_vertical_context(context_results: Dict[str, Any]) -> str:
    """Extract vertical context from retrieval results."""
    lines = []
    for run in context_results.get("query_runs", []):
        if run.get("type") == "vertical":
            lines.append(f"\n### {run.get('intent', '纵向来源')}")
            for item in run.get("items", [])[:5]:
                lines.append(f"- [{item.get('source_tier', 'T3')}] {item.get('title', '')} ({item.get('domain', '')})")
                if item.get("snippet"):
                    lines.append(f"  摘要: {item.get('snippet', '')[:200]}...")
    
    if not lines:
        return "暂无纵向检索结果"
    return "\n".join(lines)


def extract_historical_content(context_results: Dict[str, Any]) -> str:
    """Extract historical document content for semantic diff."""
    lines = []
    for run in context_results.get("query_runs", []):
        if run.get("type") in ("vertical", "semantic"):
            for item in run.get("items", [])[:3]:
                if item.get("snippet"):
                    lines.append(f"## {item.get('title', '历史文件')}")
                    lines.append(item.get("snippet", ""))
                    lines.append("")
    
    if not lines:
        return "暂无历史对比文件"
    return "\n".join(lines)


def build_reference_sources(context_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a structured reference sources object for display in reports.
    This is critical for showing users what sources were consulted.
    """
    horizontal_sources = []
    vertical_sources = []
    other_sources = []
    
    for run in context_results.get("query_runs", []):
        query_type = run.get("type", "unknown")
        query_intent = run.get("intent", "")
        
        for item in run.get("items", []):
            source_entry = {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "domain": item.get("domain", ""),
                "tier": item.get("source_tier", "T3"),
                "tier_reason": item.get("tier_reason", ""),
                "snippet": item.get("snippet", "")[:200] + "..." if len(item.get("snippet", "")) > 200 else item.get("snippet", ""),
                "query_intent": query_intent,
            }
            
            if query_type == "horizontal":
                horizontal_sources.append(source_entry)
            elif query_type == "vertical":
                vertical_sources.append(source_entry)
            else:
                other_sources.append(source_entry)
    
    # Deduplicate by URL
    def dedupe_sources(sources):
        seen_urls = set()
        deduped = []
        for s in sources:
            if s["url"] and s["url"] not in seen_urls:
                seen_urls.add(s["url"])
                deduped.append(s)
        return deduped
    
    return {
        "horizontal": dedupe_sources(horizontal_sources),
        "vertical": dedupe_sources(vertical_sources),
        "other": dedupe_sources(other_sources),
        "total_count": context_results.get("unique_item_count", 0),
        "tier_distribution": context_results.get("tier_counts", {}),
        "search_provider": context_results.get("search_provider", "tavily"),
    }


async def _chunk_and_analyze_parallel(
    client,
    material: str,
    horizontal_context: str,
    vertical_context: str,
    focus_ctx: Dict[str, Any],
    progress_callback=None,
) -> Optional[Dict[str, Any]]:
    """
    Phase 3: For long documents (e.g. 政府工作报告), split into domain chunks
    and run POLICY_ANALYSIS on each chunk in parallel.
    Returns merged policy_analysis dict, or None if chunking fails.
    """
    if progress_callback:
        progress_callback("llm_chunking", "大模型正在对长文档进行领域切分...")
    print("\n[LLM] 📑 长文档检测，正在自动切分领域...")

    chunking_result = await client.analyze(
        AnalysisTask.DOCUMENT_CHUNKING,
        material,
    )

    chunks = chunking_result.get("chunks", [])
    if not chunks:
        print("[LLM] ⚠️ 切分结果为空，改用整体分析")
        return None

    print(f"[LLM] 切分完成，共 {len(chunks)} 个领域：{', '.join(c.get('domain', '?') for c in chunks)}")

    if progress_callback:
        progress_callback("llm_parallel_analysis", f"大模型正在并行分析 {len(chunks)} 个领域...")
    print(f"\n[LLM] 🚀 并行启动 {len(chunks)} 个领域的深度分析...")

    async def _analyze_chunk(chunk: Dict[str, Any], idx: int) -> Dict[str, Any]:
        domain = chunk.get("domain", f"领域{idx+1}")
        content = chunk.get("content", "")
        chunk_title = chunk.get("title", "")
        chunk_header = (
            f"## 领域: {domain}\n### 议题: {chunk_title}\n\n{content}\n\n"
            f"---\n⚠️ 此为长篇政策文件的【领域切片】分析。请对该领域进行深入、详尽的分析：\n"
            f"1. core_judgment 至少3-5句，涵盖该领域的核心政策方向、关键数字和变化趋势\n"
            f"2. policy_changes 至少列出3-5条具体的政策变化，每条都附带 evidence 引用原文\n"
            f"3. power_signals 至少2条权力信号（如有人事、机构方面的内容）\n"
            f"4. quantitative_kpis 提取该领域所有可量化的指标和目标数字\n"
            f"5. policy_intent 详细解读政策意图，不少于3句话\n"
        )
        try:
            result = await client.analyze(
                AnalysisTask.POLICY_ANALYSIS,
                chunk_header,
                {
                    "horizontal_context": horizontal_context,
                    "vertical_context": vertical_context,
                    **focus_ctx,
                }
            )
            result["_domain"] = domain
            result["_title"] = chunk_title
            print(f"  ✅ [{domain}] 分析完成")
            return result
        except Exception as e:
            print(f"  ⚠️ [{domain}] 分析失败: {e}")
            return {"_domain": domain, "_title": chunk_title, "_error": str(e)}

    tasks = [_analyze_chunk(chunk, i) for i, chunk in enumerate(chunks)]
    chunk_results = await asyncio.gather(*tasks)

    merged: Dict[str, Any] = {
        "chunked_analysis": True,
        "total_chunks": len(chunks),
        "domains_analyzed": [r.get("_domain", "") for r in chunk_results],
        "per_domain_results": chunk_results,
        "policy_changes": [],
        "power_signals": [],
        "institutional_changes": [],
        "quantitative_kpis": [],
    }
    for r in chunk_results:
        if "_error" in r:
            continue
        for key in ("policy_changes", "power_signals", "institutional_changes", "quantitative_kpis"):
            items = r.get(key, [])
            if isinstance(items, list):
                merged[key].extend(items)

    print(f"[LLM] 并行分析完成，已合并 {len(chunk_results)} 个领域的结果")
    return merged


async def build_llm_analysis(
    material: str,
    query_matrix: Dict[str, Any],
    context_results: Dict[str, Any],
    title: Optional[str] = None,
    progress_callback: Optional[callable] = None,
    user_focus: str = "",
) -> Dict[str, Any]:
    """
    Build comprehensive analysis using LLM for all analysis tasks.
    
    This function orchestrates multiple LLM calls to:
    1. Perform deep policy analysis
    2. Analyze semantic differences
    3. Generate risk scenarios
    4. Analyze business impact
    5. Generate executive summary
    """
    client = LLMClient()
    
    try:
        # Get material understanding from query matrix
        material_understanding = query_matrix.get("material_understanding", {})
        topic = query_matrix.get("topic", material_understanding.get("core_topic", "中国政治议题"))
        
        # Build title using original_title + publish_date (format: "YYYY年M月D日 《原始标题》解读")
        original_title = material_understanding.get("original_title", "")
        publish_date = material_understanding.get("publish_date", "")
        if original_title and publish_date:
            analysis_title = title or f"{publish_date} 《{original_title}》解读"
        elif original_title:
            analysis_title = title or f"《{original_title}》解读"
        else:
            analysis_title = title or f"{topic}：多维政治解读"
        
        # Extract context
        horizontal_context = extract_horizontal_context(context_results)
        vertical_context = extract_vertical_context(context_results)
        historical_content = extract_historical_content(context_results)
        
        # ---- Smart routing: detect material type for specialized tasks ----
        material_type = material_understanding.get("material_type", "")
        core_topic = material_understanding.get("core_topic", "")
        material_type_lower = (material_type + " " + core_topic).lower()
        
        is_economic_doc = any(kw in material_type_lower for kw in [
            "政府工作报告", "经济工作会议", "预算", "财政", "发改委",
            "统计公报", "gdp", "货币政策", "金融"
        ])
        is_cadre_doc = any(kw in material_type_lower for kw in [
            "人事", "任免", "分工", "调整", "班子", "任命", "领导"
        ])
        
        _focus_ctx: Dict[str, Any] = {"user_focus": user_focus} if user_focus else {}
        
        # ---- Phase 3: Auto-chunking for long documents ----
        is_long_doc = len(material) > 10000
        policy_analysis = None
        
        if is_long_doc:
            print(f"\n[LLM] 📏 文档长度 {len(material)} 字，超过 10000 字阈值，启动自动切片+并行分析")
            policy_analysis = await _chunk_and_analyze_parallel(
                client, material, horizontal_context, vertical_context,
                _focus_ctx, progress_callback,
            )
        
        # Fallback: single analysis (short docs or chunking failure)
        if policy_analysis is None:
            # Context compression (Phase 2) for medium-length docs
            material_for_analysis = material
            if len(material) > 8000:
                material_understanding_json = json.dumps(material_understanding, ensure_ascii=False, indent=2)
                material_for_analysis = (
                    f"## 材料理解摘要（已由前序分析提取）\n{material_understanding_json}\n\n"
                    f"## 原文节选（前8000字）\n{material[:8000]}...\n\n"
                    f"[全文共 {len(material)} 字，已截断。核心信息见上方材料理解摘要。]"
                )
                print(f"[LLM] 原文 {len(material)} 字，已压缩为摘要+节选模式 → {len(material_for_analysis)} 字")
            
            if progress_callback:
                progress_callback("llm_policy_analysis", "大模型正在进行深度政策分析...")
            print("\n[LLM] 正在进行深度政策分析...")
            policy_analysis = await client.analyze(
                AnalysisTask.POLICY_ANALYSIS,
                material_for_analysis,
                {
                    "horizontal_context": horizontal_context,
                    "vertical_context": vertical_context,
                    **_focus_ctx,
                }
            )
            print("[LLM] 政策分析完成")
        
        # Step 1.5a: KPI Extraction (for economic/fiscal documents)
        kpi_extraction = None
        if is_economic_doc:
            if progress_callback:
                progress_callback("llm_kpi_extraction", "大模型正在提取量化指标...")
            print("\n[LLM] 检测到经济类文件，正在提取量化指标...")
            kpi_extraction = await client.analyze(
                AnalysisTask.KPI_EXTRACTION,
                material,
                {"historical_content": historical_content, **_focus_ctx}
            )
            print("[LLM] 量化指标提取完成")
        
        # Step 1.5b: Cadre Analysis (for personnel/leadership documents)
        cadre_analysis = None
        if is_cadre_doc:
            if progress_callback:
                progress_callback("llm_cadre_analysis", "大模型正在分析人事变动...")
            print("\n[LLM] 检测到人事类文件，正在分析人事变动...")
            cadre_analysis = await client.analyze(
                AnalysisTask.CADRE_ANALYSIS,
                material,
                {**_focus_ctx}
            )
            print("[LLM] 人事分析完成")
        
        # Step 2: Semantic diff analysis
        if progress_callback:
            progress_callback("llm_semantic_diff", "大模型正在分析语义变化...")
        
        print("\n[LLM] 正在分析语义变化...")
        semantic_diff = await client.analyze(
            AnalysisTask.SEMANTIC_DIFF,
            material,
            {"historical_content": historical_content, **_focus_ctx}
        )
        print("[LLM] 语义分析完成")
        
        # Step 3: Risk scenario analysis
        if progress_callback:
            progress_callback("llm_risk_scenarios", "大模型正在构建风险情景...")
        
        print("\n[LLM] 正在构建风险情景...")
        risk_scenarios = await client.analyze(
            AnalysisTask.RISK_SCENARIO,
            context={"policy_analysis": json.dumps(policy_analysis, ensure_ascii=False), **_focus_ctx}
        )
        print("[LLM] 风险情景分析完成")
        
        # Step 4: Business impact analysis
        if progress_callback:
            progress_callback("llm_business_impact", "大模型正在分析商业影响...")
        
        print("\n[LLM] 正在分析商业影响...")
        business_impact = await client.analyze(
            AnalysisTask.BUSINESS_IMPACT,
            context={"policy_analysis": json.dumps(policy_analysis, ensure_ascii=False), **_focus_ctx}
        )
        print("[LLM] 商业影响分析完成")
        
        # Step 5: Generate executive summary
        if progress_callback:
            progress_callback("llm_executive_summary", "大模型正在生成执行摘要...")
        
        print("\n[LLM] 正在生成执行摘要...")
        full_analysis = {
            "policy_analysis": policy_analysis,
            "semantic_diff": semantic_diff,
            "risk_scenarios": risk_scenarios,
            "business_impact": business_impact,
        }
        executive_summary = await client.analyze(
            AnalysisTask.GENERATE_EXECUTIVE_SUMMARY,
            context={"full_analysis": json.dumps(full_analysis, ensure_ascii=False), **_focus_ctx}
        )
        print("[LLM] 执行摘要生成完成")
        
        # Build complete analysis result
        reference_sources = build_reference_sources(context_results)
        unique_reference_urls = set()
        for source_group in ("horizontal", "vertical", "other"):
            for item in reference_sources.get(source_group, []):
                url = item.get("url", "")
                if url:
                    unique_reference_urls.add(url)
        reference_count = len(unique_reference_urls)

        analysis_result = {
            "title": analysis_title,
            "topic": topic,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "llm_powered": True,
            "llm_model": os.environ.get("LLM_MODEL") or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
            
            # Material info
            "material_understanding": material_understanding,
            "material_length": len(material),
            
            # LLM analysis results
            "executive_summary": executive_summary,
            "policy_analysis": policy_analysis,
            "semantic_diff": semantic_diff,
            "risk_scenarios": risk_scenarios,
            "business_impact": business_impact,
            
            # Specialized analysis (conditional)
            "kpi_extraction": kpi_extraction,      # Only for economic docs
            "cadre_analysis": cadre_analysis,       # Only for personnel docs
            
            # Context info - IMPORTANT: Include full reference list
            "context_stats": {
                "unique_items": context_results.get("unique_item_count", 0),
                "tier_counts": context_results.get("tier_counts", {}),
            },
            
            # Reference sources - Full list for display in report
            "reference_sources": reference_sources,
            "reference_count": reference_count,  # 参考文献数量
            
            # Token usage - 从LLM客户端获取总计
            "token_usage": getattr(client, 'total_token_usage', 0),  # Token总消耗
            
            # Query matrix info
            "search_strategy": query_matrix.get("search_strategy", {}),
            "historical_peers": query_matrix.get("historical_peers", {}),
            "regional_peers": query_matrix.get("regional_peers", {}),
        }
        
        return analysis_result
        
    finally:
        await client.close()


def build_fallback_analysis(
    material: str,
    query_matrix: Dict[str, Any],
    context_results: Dict[str, Any],
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """Build analysis using template-based approach (fallback when LLM unavailable)."""
    topic = query_matrix.get("topic", "中国政治议题")
    analysis_title = title or f"{topic}：多维政治解读"
    reference_sources = build_reference_sources(context_results)
    unique_reference_urls = set()
    for source_group in ("horizontal", "vertical", "other"):
        for item in reference_sources.get(source_group, []):
            url = item.get("url", "")
            if url:
                unique_reference_urls.add(url)
    
    return {
        "title": analysis_title,
        "topic": topic,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "llm_powered": False,
        "material_length": len(material),
        "note": "LLM 未配置，仅提供模板框架。请配置 GEMINI_API_KEY 以启用智能分析。",
        "template_sections": [
            "1. 核心判断",
            "2. 事实层：发生了什么",
            "3. 政治逻辑层：为何此时推进",
            "4. 权力与执行链条",
            "5. 文本与提法差分",
            "6. 纵向演化",
            "7. 横向对照",
            "8. 风险与情景",
            "9. 待验证问题",
            "10. 业务/合规影响",
            "11. 证据登记表",
        ],
        "context_stats": {
            "unique_items": context_results.get("unique_item_count", 0),
            "tier_counts": context_results.get("tier_counts", {}),
        },
        "reference_sources": reference_sources,
        "reference_count": len(unique_reference_urls),
        "token_usage": 0,
    }


def convert_to_markdown(analysis: Dict[str, Any]) -> str:
    """Convert analysis JSON to markdown format."""
    lines = [f"# {analysis.get('title', '政治分析报告')}", ""]
    
    # Executive summary
    summary = analysis.get("executive_summary", {})
    if summary:
        lines.append("## 执行摘要")
        lines.append(f"**一句话总结**: {summary.get('one_liner', '')}")
        lines.append("")
        lines.append("### 核心结论")
        for conclusion in summary.get("core_conclusions", []):
            lines.append(f"- {conclusion}")
        lines.append("")
        lines.append("### 关键风险")
        for risk in summary.get("key_risks", []):
            lines.append(f"- {risk}")
        lines.append("")
        lines.append("### 行动建议")
        for action in summary.get("action_items", []):
            lines.append(f"- {action}")
        lines.append("")
    
    # Policy analysis
    policy = analysis.get("policy_analysis", {})
    if policy:
        lines.append("## 政策分析")
        lines.append("")
        
        # Core judgments
        lines.append("### 核心判断")
        for judgment in policy.get("core_judgments", []):
            tag = f"[{judgment.get('evidence_type', 'I')}][{judgment.get('confidence', 'medium')}]"
            lines.append(f"- {tag} {judgment.get('judgment', '')}")
        lines.append("")
        
        # Policy intent
        intent = policy.get("policy_intent", {})
        if intent:
            lines.append("### 政策意图")
            lines.append(f"**显性目标**: {', '.join(intent.get('explicit_goals', []))}")
            lines.append(f"**隐性目标**: {', '.join(intent.get('implicit_goals', []))}")
            lines.append(f"**政治逻辑**: {intent.get('political_logic', '')}")
            lines.append("")
        
        # Institutional map
        inst = policy.get("institutional_map", {})
        if inst:
            lines.append("### 制度地图")
            lines.append(f"- **牵头机构**: {inst.get('lead_agency', '')}")
            lines.append(f"- **协调机构**: {', '.join(inst.get('coordination_bodies', []))}")
            lines.append(f"- **潜在否决点**: {', '.join(inst.get('veto_points', []))}")
            lines.append(f"- **执行路径**: {inst.get('execution_path', '')}")
            lines.append("")
        
        # Power signals
        power = policy.get("power_signals", {})
        if power:
            lines.append("### 权力信号")
            if power.get("personnel_signals"):
                lines.append(f"- **人事信号**: {', '.join(power.get('personnel_signals', []))}")
            if power.get("campaign_language"):
                lines.append(f"- **运动式语言**: {', '.join(power.get('campaign_language', []))}")
            if power.get("center_local_clues"):
                lines.append(f"- **中央-地方线索**: {', '.join(power.get('center_local_clues', []))}")
            lines.append("")
    
    # Semantic diff
    semantic = analysis.get("semantic_diff", {})
    if semantic:
        lines.append("## 文本与语义变化")
        lines.append("")
        
        if semantic.get("new_expressions"):
            lines.append("### 新增表述")
            for expr in semantic.get("new_expressions", []):
                lines.append(f"- **{expr.get('expression', '')}**: {expr.get('political_meaning', '')}")
            lines.append("")
        
        if semantic.get("dropped_expressions"):
            lines.append("### 消失表述")
            for expr in semantic.get("dropped_expressions", []):
                lines.append(f"- **{expr.get('expression', '')}**: {expr.get('political_meaning', '')}")
            lines.append("")
        
        if semantic.get("modifier_changes"):
            lines.append("### 修饰语变化")
            lines.append("| 概念 | 原修饰语 | 新修饰语 | 方向 | 解读 |")
            lines.append("|---|---|---|---|---|")
            for change in semantic.get("modifier_changes", []):
                lines.append(f"| {change.get('concept', '')} | {change.get('old_modifier', '')} | {change.get('new_modifier', '')} | {change.get('direction', '')} | {change.get('interpretation', '')} |")
            lines.append("")
        
        if semantic.get("overall_shift"):
            lines.append(f"**总体语义变化**: {semantic.get('overall_shift', '')}")
            lines.append("")
    
    # Risk scenarios
    scenarios = analysis.get("risk_scenarios", {})
    if scenarios:
        lines.append("## 风险情景分析")
        lines.append("")
        
        for scenario in scenarios.get("scenarios", []):
            lines.append(f"### {scenario.get('name', '')} ({scenario.get('type', '')})")
            lines.append(f"- **概率**: {scenario.get('probability', '')}")
            lines.append(f"- **触发条件**: {', '.join(scenario.get('trigger_conditions', []))}")
            lines.append(f"- **发展路径**: {scenario.get('development_path', '')}")
            lines.append(f"- **影响评估**: {scenario.get('impact_assessment', '')}")
            lines.append(f"- **时间窗口**: {scenario.get('timeline', '')}")
            lines.append("")
        
        if scenarios.get("watch_list"):
            lines.append("### 观察清单")
            lines.append("| 指标 | 阈值 | 触发情景 |")
            lines.append("|---|---|---|")
            for watch in scenarios.get("watch_list", []):
                lines.append(f"| {watch.get('indicator', '')} | {watch.get('threshold', '')} | {watch.get('scenario_triggered', '')} |")
            lines.append("")
    
    # Business impact
    business = analysis.get("business_impact", {})
    if business:
        lines.append("## 商业/合规影响")
        lines.append("")
        
        if business.get("winners"):
            lines.append("### 受益行业")
            for winner in business.get("winners", []):
                lines.append(f"- **{winner.get('sector', '')}**: {winner.get('reason', '')}")
                if winner.get("specific_opportunities"):
                    for opp in winner.get("specific_opportunities", []):
                        lines.append(f"  - {opp}")
            lines.append("")
        
        if business.get("losers"):
            lines.append("### 受损行业")
            for loser in business.get("losers", []):
                lines.append(f"- **{loser.get('sector', '')}** [{loser.get('risk_level', '')}]: {loser.get('reason', '')}")
            lines.append("")
        
        if business.get("compliance_risks"):
            lines.append("### 合规风险")
            for risk in business.get("compliance_risks", []):
                lines.append(f"- **{risk.get('risk', '')}**")
                lines.append(f"  - 受影响主体: {', '.join(risk.get('affected_entities', []))}")
                lines.append(f"  - 缓解措施: {risk.get('mitigation', '')}")
            lines.append("")
        
        if business.get("action_items"):
            lines.append("### 行动建议")
            lines.append("| 紧急程度 | 建议行动 | 理由 |")
            lines.append("|---|---|---|")
            for action in business.get("action_items", []):
                lines.append(f"| {action.get('urgency', '')} | {action.get('action', '')} | {action.get('rationale', '')} |")
            lines.append("")
    
    # Metadata
    lines.append("---")
    lines.append(f"*生成时间: {analysis.get('generated_at', '')}*")
    lines.append(f"*LLM模型: {analysis.get('llm_model', 'N/A')}*")
    
    return "\n".join(lines)


async def async_main(args: argparse.Namespace) -> None:
    """Async main function that uses LLM for comprehensive analysis."""
    material = load_text(args.material_file, args.material_text)
    query_matrix = load_json(args.query_matrix)
    context_results = load_json(args.context_results)
    
    print(f"\n材料长度: {len(material)} 字符")
    print(f"检索结果: {context_results.get('unique_item_count', 0)} 条去重链接")
    
    # Check if LLM is available
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    use_llm = LLM_AVAILABLE and api_key and not getattr(args, "no_llm", False)
    
    if use_llm:
        print("\n" + "="*60)
        print("🤖 使用大模型进行深度分析")
        print("="*60)
        analysis = await build_llm_analysis(
            material,
            query_matrix,
            context_results,
            title=args.title,
            user_focus=getattr(args, "user_focus", ""),
        )
    else:
        if not api_key:
            print("\n⚠️  GEMINI_API_KEY 未配置，使用模板框架")
        print("\n使用模板生成分析框架...")
        analysis = build_fallback_analysis(
            material,
            query_matrix,
            context_results,
            title=args.title,
        )
    
    # Output results
    if args.output_format == "markdown":
        output = convert_to_markdown(analysis)
    else:
        output = json.dumps(analysis, ensure_ascii=False, indent=2)
    
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output + "\n", encoding="utf-8")
        print(f"\n✅ 已写入分析结果: {output_path}")
    else:
        print("\n" + "="*60)
        print("分析结果:")
        print("="*60)
        print(output)
    
    # Generate package if requested
    if args.package_dir:
        analysis_json_path = Path(args.package_dir) / f"{args.package_base_name}_analysis.json"
        analysis_json_path.parent.mkdir(parents=True, exist_ok=True)
        analysis_json_path.write_text(
            json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8"
        )
        print(f"✅ 已写入分析JSON: {analysis_json_path}")
        
        # Call render script to generate HTML/PDF
        render_script = Path(__file__).with_name("render_analysis_web_pdf.py")
        if render_script.exists():
            cmd = [
                sys.executable,
                str(render_script),
                "--analysis-json",
                str(analysis_json_path),
                "--output-dir",
                str(Path(args.package_dir)),
                "--base-name",
                args.package_base_name,
            ]
            if args.title:
                cmd.extend(["--title", args.title])
            subprocess.run(cmd, check=True)
            print(f"✅ 已生成交付包: {Path(args.package_dir).resolve()}")


def main() -> None:
    args = parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
