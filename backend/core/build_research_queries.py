#!/usr/bin/env python3
"""
Build horizontal/vertical research queries for China political analysis.

This module uses LLM (Gemini) to intelligently:
1. Understand the material's type, topic, and key elements
2. Generate smart search strategies for horizontal and vertical research
3. Identify historical peer documents for comparison
4. Identify regional/departmental peer documents

Usage:
    python build_research_queries.py --file /path/to/material.txt --output /tmp/query_matrix.json
    python build_research_queries.py --url https://example.com/news --output /tmp/query_matrix.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Dict, Any

# Import LLM client
try:
    from llm_client import (
        LLMClient,
        AnalysisTask,
        analyze_material,
        generate_search_strategy,
        identify_historical_peers,
        identify_regional_peers,
    )
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    print("Warning: LLM client not available. Using rule-based fallback.")


# Load environment variables from .env if available
try:
    from dotenv import load_dotenv
    from pathlib import Path
    env_file = Path(__file__).parent.parent.parent / "config" / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass


STOPWORDS = {
    "我们",
    "你们",
    "他们",
    "以及",
    "进行",
    "通过",
    "关于",
    "有关",
    "相关",
    "工作",
    "会议",
    "问题",
    "要求",
    "推进",
    "加强",
    "完善",
    "落实",
    "根据",
    "按照",
    "记者",
    "表示",
    "指出",
    "提出",
    "其中",
    "对于",
    "这个",
    "那个",
    "已经",
    "继续",
    "坚持",
    "同时",
    "进一步",
    "中国",
    "全国",
    "今年",
    "本次",
}

ORG_HINTS = [
    "中共中央",
    "中央政治局",
    "国务院",
    "全国人大",
    "全国政协",
    "国家发展改革委",
    "国家发改委",
    "财政部",
    "人民银行",
    "公安部",
    "教育部",
    "工信部",
    "商务部",
    "国家卫健委",
    "中央纪委国家监委",
    "最高人民法院",
    "最高人民检察院",
]

POLICY_SUFFIXES = (
    "意见",
    "通知",
    "方案",
    "规定",
    "办法",
    "条例",
    "决定",
    "公告",
    "通报",
    "白皮书",
    "报告",
)

DOMAIN_GROUPS = {
    "primary_official": [
        "gov.cn",
        "npc.gov.cn",
        "ccdi.gov.cn",
        "moj.gov.cn",
        "stats.gov.cn",
    ],
    "party_state_media": [
        "xinhuanet.com",
        "people.com.cn",
        "cctv.com",
        "china.com.cn",
    ],
    "market_professional_media": [
        "caixin.com",
        "stcn.com",
        "21jingji.com",
        "yicai.com",
    ],
    "international_media": [
        "reuters.com",
        "ft.com",
        "wsj.com",
        "apnews.com",
        "bloomberg.com",
    ],
}

SEMANTIC_SUFFIXES = (
    "思维",
    "理念",
    "导向",
    "机制",
    "体系",
    "格局",
    "治理",
    "发展",
    "安全",
)

MODIFIER_CUES = [
    "严格限制",
    "从严",
    "坚决遏制",
    "规范发展",
    "积极稳妥",
    "有序推进",
    "适度",
    "审慎",
    "鼓励",
    "支持",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a research query matrix for China political interpretation (LLM-powered)."
    )
    parser.add_argument("--file", help="Path to text material.")
    parser.add_argument("--text", help="Raw input text.")
    parser.add_argument("--url", help="URL to extract content from (with anti-crawling bypass).")
    parser.add_argument("--image", help="Image file path for OCR extraction.")
    parser.add_argument("--pdf", help="PDF file path for text extraction.")
    parser.add_argument("--topic", help="Optional explicit topic override.")
    parser.add_argument(
        "--max-keywords", type=int, default=12, help="Max number of extracted keywords (fallback mode)."
    )
    parser.add_argument("--output", help="Output JSON path.")
    parser.add_argument(
        "--force-browser",
        action="store_true",
        help="Force browser extraction for URL (bypass standard fetch)."
    )
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="Force OCR extraction from screenshot."
    )
    parser.add_argument(
        "--extraction-timeout",
        type=int,
        default=30,
        help="Timeout seconds for URL extraction."
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM and use rule-based fallback."
    )
    parser.add_argument(
        "--user-focus",
        default="",
        help="Optional user-provided analysis focus instruction."
    )
    return parser.parse_args()


def load_text(
    file_path: str | None = None,
    raw_text: str | None = None,
    url: str | None = None,
    image_path: str | None = None,
    pdf_path: str | None = None,
    force_browser: bool = False,
    force_ocr: bool = False,
    extraction_timeout: int = 30,
) -> tuple[str, dict]:
    """
    Load text from various sources with fallback strategies.
    Returns (text, extraction_info).
    """
    extraction_info = {"source_type": "unknown", "method": "direct", "success": True}
    
    if file_path:
        text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        extraction_info = {"source_type": "file", "method": "direct_read", "success": True}
        return text, extraction_info
    
    if raw_text:
        extraction_info = {"source_type": "text", "method": "direct_input", "success": True}
        return raw_text, extraction_info
    
    # Try content extractor for URL, image, or PDF
    if url or image_path or pdf_path:
        try:
            from content_extractor import extract_content
            result = extract_content(
                url=url,
                image_path=image_path,
                pdf_path=pdf_path,
                timeout=extraction_timeout,
                force_browser=force_browser,
                force_ocr=force_ocr,
            )
            extraction_info = {
                "source_type": result.get("source_type", "unknown"),
                "method": result.get("method", "unknown"),
                "success": result.get("success", False),
                "error": result.get("error", ""),
            }
            if result.get("success") and result.get("text"):
                return result["text"], extraction_info
            else:
                print(f"Warning: Content extraction partially failed: {result.get('error', 'unknown error')}")
                if result.get("text"):
                    return result["text"], extraction_info
        except ImportError:
            print("Warning: content_extractor module not available, falling back to basic URL fetch.")
            if url:
                # Basic fallback URL fetch
                import urllib.request
                import ssl
                try:
                    req = urllib.request.Request(
                        url,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; PoliticalAnalyzer/1.0)"}
                    )
                    context = ssl.create_default_context()
                    with urllib.request.urlopen(req, timeout=extraction_timeout, context=context) as resp:
                        html = resp.read().decode("utf-8", errors="ignore")
                        # Simple HTML to text conversion
                        import re
                        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
                        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
                        text = re.sub(r"<[^>]+>", " ", text)
                        text = re.sub(r"\s+", " ", text).strip()
                        extraction_info = {"source_type": "url", "method": "basic_fetch", "success": True}
                        return text, extraction_info
                except Exception as e:
                    extraction_info = {"source_type": "url", "method": "basic_fetch", "success": False, "error": str(e)}
                    print(f"Warning: Basic URL fetch failed: {e}")
        except Exception as e:
            extraction_info["error"] = str(e)
            print(f"Warning: Content extraction failed: {e}")
    
    raise ValueError("Provide --file, --text, --url, --image, or --pdf.")


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_years(text: str) -> list[int]:
    years = {int(y) for y in re.findall(r"(20\d{2})", text)}
    return sorted(y for y in years if 1990 <= y <= 2100)


def extract_tokens(text: str) -> Iterable[str]:
    # Use jieba for proper Chinese word segmentation if available
    try:
        import jieba
        raw_tokens = jieba.cut(text, cut_all=False)
    except ImportError:
        # Fallback: regex-based character-range matching
        raw_tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,24}", text)

    for token in raw_tokens:
        cleaned = token.strip("，。；：、（）()《》\"\"'[]【】 \t\n")
        if len(cleaned) < 2:
            continue
        if cleaned in STOPWORDS:
            continue
        if re.fullmatch(r"\d+", cleaned):
            continue
        # Skip pure punctuation / whitespace tokens from jieba
        if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", cleaned):
            continue
        yield cleaned


def top_keywords(text: str, max_keywords: int) -> list[str]:
    counter = Counter(extract_tokens(text))
    return [word for word, _ in counter.most_common(max_keywords)]


def extract_policy_titles(text: str) -> list[str]:
    pattern = (
        r"([《\"]?[\u4e00-\u9fffA-Za-z0-9]{3,50}"
        r"(?:意见|通知|方案|规定|办法|条例|决定|公告|通报|白皮书|报告)[》\"]?)"
    )
    seen: set[str] = set()
    titles: list[str] = []
    for hit in re.findall(pattern, text):
        normalized = hit.strip("《》\"")
        if normalized in seen:
            continue
        seen.add(normalized)
        titles.append(normalized)
        if len(titles) >= 12:
            break
    return titles


def extract_organizations(text: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for hint in ORG_HINTS:
        if hint in text and hint not in seen:
            seen.add(hint)
            ordered.append(hint)
    pattern = r"([\u4e00-\u9fff]{2,30}(?:委员会|部|厅|局|院|办|政府|人大|政协))"
    for hit in re.findall(pattern, text):
        if hit in seen:
            continue
        if len(hit) > 25:
            continue
        seen.add(hit)
        ordered.append(hit)
        if len(ordered) >= 16:
            break
    return ordered


def extract_semantic_phrases(text: str, max_items: int = 12) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    pattern = r"([\u4e00-\u9fff]{2,18}(?:思维|理念|导向|机制|体系|格局|治理|发展|安全))"
    for hit in re.findall(pattern, text):
        if hit in seen:
            continue
        seen.add(hit)
        candidates.append(hit)
        if len(candidates) >= max_items:
            return candidates

    for token in extract_tokens(text):
        if any(token.endswith(suffix) for suffix in SEMANTIC_SUFFIXES):
            if token in seen:
                continue
            seen.add(token)
            candidates.append(token)
            if len(candidates) >= max_items:
                return candidates

    return candidates


def extract_modifier_cues(text: str) -> list[str]:
    hits = [cue for cue in MODIFIER_CUES if cue in text]
    return hits[:8]


def choose_topic(explicit_topic: str | None, titles: list[str], keywords: list[str]) -> str:
    if explicit_topic:
        return explicit_topic.strip()
    if titles:
        return titles[0]
    if keywords:
        return "".join(keywords[:2])
    return "中国政治议题"


def build_horizontal_queries(topic: str, organizations: list[str], keywords: list[str]) -> list[dict]:
    focus_org = organizations[0] if organizations else "国务院"
    focus_kw = keywords[0] if keywords else topic
    return [
        {
            "type": "horizontal",
            "intent": "官方原文和制度依据",
            "query": f"{topic} 原文 通知 规定",
            "recommended_domains": DOMAIN_GROUPS["primary_official"],
        },
        {
            "type": "horizontal",
            "intent": "党媒与官媒叙事重点",
            "query": f"{topic} 权威解读 部署",
            "recommended_domains": DOMAIN_GROUPS["party_state_media"],
        },
        {
            "type": "horizontal",
            "intent": "行业和市场执行反馈",
            "query": f"{topic} 落地 执行 影响 {focus_kw}",
            "recommended_domains": DOMAIN_GROUPS["market_professional_media"],
        },
        {
            "type": "horizontal",
            "intent": "国际观察与外部框架",
            "query": f"{topic} policy impact China",
            "recommended_domains": DOMAIN_GROUPS["international_media"],
        },
        {
            "type": "horizontal",
            "intent": "机构角色与职责边界",
            "query": f"{topic} {focus_org} 发布 印发 职责",
            "recommended_domains": DOMAIN_GROUPS["primary_official"],
        },
    ]


def build_vertical_queries(topic: str, years: list[int], titles: list[str]) -> list[dict]:
    current_year = datetime.now().year
    latest_year = years[-1] if years else current_year
    earliest_year = years[0] if years else max(current_year - 5, 2000)
    predecessor_anchor = max(earliest_year, latest_year - 5)
    policy_name = titles[0] if titles else topic

    vertical = [
        {
            "type": "vertical",
            "intent": "政策沿革与前序文件",
            "query": f"{policy_name} 沿革 历史 {predecessor_anchor} {latest_year}",
            "recommended_domains": DOMAIN_GROUPS["primary_official"],
            "time_hint": {"from_year": predecessor_anchor, "to_year": latest_year},
        },
        {
            "type": "vertical",
            "intent": "实施细则和地方落地节点",
            "query": f"{topic} 实施细则 试点 通报",
            "recommended_domains": DOMAIN_GROUPS["party_state_media"],
            "time_hint": {"from_year": max(latest_year - 3, 2000), "to_year": latest_year},
        },
        {
            "type": "vertical",
            "intent": "督查整改与政策反馈闭环",
            "query": f"{topic} 督查 整改 评估",
            "recommended_domains": DOMAIN_GROUPS["primary_official"],
            "time_hint": {"from_year": max(latest_year - 2, 2000), "to_year": current_year},
        },
        {
            "type": "vertical",
            "intent": "关键会议和人事信号演化",
            "query": f"{topic} 会议 人事 调整 部署",
            "recommended_domains": DOMAIN_GROUPS["party_state_media"],
            "time_hint": {"from_year": max(latest_year - 5, 2000), "to_year": current_year},
        },
    ]
    return vertical


def build_semantic_queries(
    topic: str, years: list[int], titles: list[str], semantic_terms: list[str], modifiers: list[str]
) -> list[dict]:
    current_year = datetime.now().year
    latest_year = years[-1] if years else current_year
    start_year = max(latest_year - 8, 2000)
    peer_doc = titles[0] if titles else topic

    queries: list[dict] = [
        {
            "type": "semantic",
            "intent": "同类文件提法增减与词义迁移",
            "query": f"{peer_doc} 全文 提法 变化 {start_year} {latest_year}",
            "recommended_domains": DOMAIN_GROUPS["primary_official"] + DOMAIN_GROUPS["party_state_media"],
            "time_hint": {"from_year": start_year, "to_year": latest_year},
        },
        {
            "type": "semantic",
            "intent": "修饰语强弱变化与政策口径变化",
            "query": f"{topic} 从严 规范发展 有序推进 变化",
            "recommended_domains": DOMAIN_GROUPS["party_state_media"] + DOMAIN_GROUPS["primary_official"],
            "time_hint": {"from_year": start_year, "to_year": latest_year},
        },
    ]

    for term in semantic_terms[:4]:
        queries.append(
            {
                "type": "semantic",
                "intent": "关键政治提法的历史轨迹",
                "query": f"{term} 提法 变化 {start_year} {latest_year}",
                "recommended_domains": DOMAIN_GROUPS["primary_official"] + DOMAIN_GROUPS["party_state_media"],
                "time_hint": {"from_year": start_year, "to_year": latest_year},
            }
        )

    if modifiers:
        joined = " ".join(modifiers[:3])
        queries.append(
            {
                "type": "semantic",
                "intent": "材料内修饰语对比检索",
                "query": f"{topic} {joined} 政策口径",
                "recommended_domains": DOMAIN_GROUPS["primary_official"] + DOMAIN_GROUPS["party_state_media"],
            }
        )

    return queries


def build_business_queries(topic: str, organizations: list[str]) -> list[dict]:
    focus_org = organizations[0] if organizations else "监管部门"
    return [
        {
            "type": "business",
            "intent": "企业合规边界和执法口径",
            "query": f"{topic} 合规 要求 执法 处罚 指引",
            "recommended_domains": DOMAIN_GROUPS["primary_official"] + DOMAIN_GROUPS["market_professional_media"],
        },
        {
            "type": "business",
            "intent": "行业利好利空与执行节奏",
            "query": f"{topic} 行业 影响 利好 利空",
            "recommended_domains": DOMAIN_GROUPS["market_professional_media"] + DOMAIN_GROUPS["international_media"],
        },
        {
            "type": "business",
            "intent": "与监管机构沟通窗口和执行接口",
            "query": f"{topic} {focus_org} 咨询 通报 申报 指南",
            "recommended_domains": DOMAIN_GROUPS["primary_official"],
        },
    ]


async def build_llm_query_matrix(
    text: str,
    extraction_info: Dict[str, Any],
    topic_override: Optional[str] = None,
    progress_callback: Optional[callable] = None,
    user_focus: str = "",
) -> Dict[str, Any]:
    """
    Build a comprehensive query matrix using LLM for intelligent analysis.
    
    This function uses the LLM to:
    1. Understand the material's type, topic, and key elements
    2. Generate smart search strategies
    3. Identify historical peer documents
    4. Identify regional/departmental peers
    
    Args:
        text: The material text to analyze
        extraction_info: Information about how the text was extracted
        topic_override: Optional topic override
        progress_callback: Optional callback for progress updates
        
    Returns:
        Dict containing the complete query matrix
    """
    client = LLMClient()
    
    try:
        # Step 1: LLM understands the material
        if progress_callback:
            progress_callback("llm_understanding", "大模型正在理解材料内容...")
        
        print("\n[LLM] 正在理解材料内容...")
        _focus_ctx: Dict[str, Any] = {"user_focus": user_focus} if user_focus else {}
        material_understanding = await client.analyze(
            AnalysisTask.MATERIAL_UNDERSTANDING,
            text,
            _focus_ctx if _focus_ctx else None
        )
        print(f"[LLM] 材料类型: {material_understanding.get('material_type', '未识别')}")
        print(f"[LLM] 核心主题: {material_understanding.get('core_topic', '未识别')}")
        print(f"[LLM] 发布主体: {material_understanding.get('issuing_body', '未识别')}")
        
        # Step 2: LLM generates search strategy
        if progress_callback:
            progress_callback("llm_search_strategy", "大模型正在生成检索策略...")
        
        print("\n[LLM] 正在生成智能检索策略...")
        search_strategy = await client.analyze(
            AnalysisTask.GENERATE_SEARCH_STRATEGY,
            text,
            {"material_understanding": json.dumps(material_understanding, ensure_ascii=False), **_focus_ctx}
        )
        
        # Step 3: LLM identifies historical peers
        if progress_callback:
            progress_callback("llm_historical_peers", "大模型正在识别历史同类文件...")
        
        print("\n[LLM] 正在识别历史同类文件...")
        historical_peers = await client.analyze(
            AnalysisTask.IDENTIFY_HISTORICAL_PEERS,
            context={"material_understanding": json.dumps(material_understanding, ensure_ascii=False)}
        )
        if historical_peers.get("historical_peers"):
            print(f"[LLM] 识别到 {len(historical_peers.get('historical_peers', []))} 个历史同类文件")
        
        # Step 4: LLM identifies regional peers
        if progress_callback:
            progress_callback("llm_regional_peers", "大模型正在识别地方/部门同类文件...")
        
        print("\n[LLM] 正在识别地方/部门同类文件...")
        regional_peers = await client.analyze(
            AnalysisTask.IDENTIFY_REGIONAL_PEERS,
            context={"material_understanding": json.dumps(material_understanding, ensure_ascii=False)}
        )
        if regional_peers.get("regional_peers"):
            print(f"[LLM] 识别到 {len(regional_peers.get('regional_peers', []))} 个地方同类文件")
        
        # Determine topic
        topic = topic_override or material_understanding.get("core_topic", "中国政治议题")
        
        # Build the complete matrix
        matrix = {
            "topic": topic,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "extraction_info": extraction_info,
            "llm_powered": True,
            "llm_model": os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
            
            # LLM understanding results
            "material_understanding": material_understanding,
            
            # LLM-generated search strategies
            "search_strategy": search_strategy,
            "vertical_queries": search_strategy.get("vertical_queries", []),
            "horizontal_queries": search_strategy.get("horizontal_queries", []),
            "key_comparison_points": search_strategy.get("key_comparison_points", []),
            
            # LLM-identified peer documents
            "historical_peers": historical_peers,
            "regional_peers": regional_peers,
            
            # Analysis framework
            "analysis_angles": [
                "policy_intent",
                "textual_semantic_shifts",
                "power_structure",
                "implementation_chain",
                "distributional_impact",
                "external_signaling",
                "business_compliance_impact",
                "risk_scenarios",
                "tail_risk",
            ],
            "source_tier_scheme": {
                "T0": "Core communiques and top-leadership authoritative speeches",
                "T1": "Central normative documents and Xinhua authorized releases",
                "T2": "Ministry regulations and central media commentary",
                "T3": "Local implementation files and peripheral official interpretation",
            },
            "source_groups": DOMAIN_GROUPS,
        }
        
        return matrix
        
    finally:
        await client.close()


def build_fallback_query_matrix(
    text: str,
    extraction_info: Dict[str, Any],
    topic_override: Optional[str] = None,
    max_keywords: int = 12,
) -> Dict[str, Any]:
    """
    Build query matrix using rule-based approach (fallback when LLM unavailable).
    """
    years = extract_years(text)
    keywords = top_keywords(text, max_keywords)
    titles = extract_policy_titles(text)
    organizations = extract_organizations(text)
    semantic_terms = extract_semantic_phrases(text)
    modifiers = extract_modifier_cues(text)
    topic = choose_topic(topic_override, titles, keywords)
    
    return {
        "topic": topic,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "extraction_info": extraction_info,
        "llm_powered": False,
        "input_stats": {
            "char_count": len(text),
            "detected_years": years,
            "policy_titles": titles,
            "organizations": organizations,
        },
        "key_terms": keywords,
        "semantic_terms": semantic_terms,
        "modifier_cues": modifiers,
        "horizontal_queries": build_horizontal_queries(topic, organizations, keywords),
        "vertical_queries": build_vertical_queries(topic, years, titles),
        "semantic_queries": build_semantic_queries(topic, years, titles, semantic_terms, modifiers),
        "business_queries": build_business_queries(topic, organizations),
        "source_groups": DOMAIN_GROUPS,
        "analysis_angles": [
            "policy_intent",
            "textual_semantic_shifts",
            "power_structure",
            "implementation_chain",
            "distributional_impact",
            "external_signaling",
            "business_compliance_impact",
            "risk_scenarios",
            "tail_risk",
        ],
        "source_tier_scheme": {
            "T0": "Core communiques and top-leadership authoritative speeches",
            "T1": "Central normative documents and Xinhua authorized releases",
            "T2": "Ministry regulations and central media commentary",
            "T3": "Local implementation files and peripheral official interpretation",
        },
    }


async def async_main(args: argparse.Namespace) -> None:
    """
    Async main function that uses LLM for intelligent query matrix generation.
    """
    # Load text from various sources
    raw_text, extraction_info = load_text(
        file_path=args.file,
        raw_text=args.text,
        url=args.url,
        image_path=args.image,
        pdf_path=args.pdf,
        force_browser=getattr(args, "force_browser", False),
        force_ocr=getattr(args, "force_ocr", False),
        extraction_timeout=getattr(args, "extraction_timeout", 30),
    )
    text = normalize_text(raw_text)
    
    # Print extraction info
    if extraction_info.get("source_type") in ("url", "image", "pdf"):
        print(f"\n内容提取方式: {extraction_info.get('method', 'unknown')}")
        print(f"提取成功: {extraction_info.get('success', False)}")
        if extraction_info.get("error"):
            print(f"注意: {extraction_info.get('error')}")
    
    print(f"\n材料长度: {len(text)} 字符")
    
    # Check if LLM is available and API key is configured
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    use_llm = LLM_AVAILABLE and api_key and not getattr(args, "no_llm", False)
    
    if use_llm:
        print("\n" + "="*60)
        print("🤖 使用大模型进行智能分析")
        print("="*60)
        matrix = await build_llm_query_matrix(
            text,
            extraction_info,
            topic_override=args.topic,
            user_focus=getattr(args, "user_focus", ""),
        )
    else:
        if not api_key:
            print("\n⚠️  GEMINI_API_KEY 未配置，使用规则驱动的回退方案")
        print("\n使用规则驱动的检索矩阵生成...")
        matrix = build_fallback_query_matrix(
            text,
            extraction_info,
            topic_override=args.topic,
            max_keywords=args.max_keywords,
        )
    
    # Output results
    output = json.dumps(matrix, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
        print(f"\n✅ 已写入检索矩阵: {args.output}")
    else:
        print("\n" + "="*60)
        print("检索矩阵结果:")
        print("="*60)
        print(output)


def main() -> None:
    args = parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
