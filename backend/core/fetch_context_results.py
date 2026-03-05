#!/usr/bin/env python3
"""
Fetch context links using the configured search engine (Tavily/Google/Bing).

This module retrieves relevant policy documents for horizontal (cross-regional)
and vertical (historical) comparison analysis.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Dict, Optional

# Import our search engine module
try:
    from search_engine import SearchEngine, SearchResult, SearchConfig, SearchProvider
    SEARCH_ENGINE_AVAILABLE = True
except ImportError:
    SEARCH_ENGINE_AVAILABLE = False
    print("Warning: search_engine module not available, falling back to basic search.")

# Source tier classification markers
T0_TITLE_MARKERS = [
    "中共中央",
    "中央政治局",
    "全会公报",
    "总书记",
    "习近平",
    "中央经济工作会议",
]

T1_DOMAINS = {
    "gov.cn",
    "npc.gov.cn",
    "xinhuanet.com",
    "news.cn",
    "ccdi.gov.cn",
}

T2_DOMAINS = {
    "people.com.cn",
    "cctv.com",
    "moj.gov.cn",
    "stats.gov.cn",
    "ce.cn",
    "gmw.cn",
}

LOCAL_TITLE_MARKERS = ["省", "市", "区", "县", "自治区", "人民政府", "办公厅", "地方"]

# Load environment variables
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent.parent / "config" / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch related context links for horizontal/vertical political analysis."
    )
    parser.add_argument("--queries-json", required=True, help="Path to query matrix JSON.")
    parser.add_argument(
        "--max-per-query", type=int, default=8, help="Max deduplicated items per query entry."
    )
    parser.add_argument(
        "--max-domains-per-query",
        type=int,
        default=3,
        help="How many recommended domains to expand with site: filters.",
    )
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds.")
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument("--markdown", help="Optional markdown summary output path.")
    return parser.parse_args()


def load_query_entries(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load query matrix and extract all query entries."""
    matrix = json.loads(path.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = []
    entries.extend(matrix.get("horizontal_queries", []))
    entries.extend(matrix.get("vertical_queries", []))
    entries.extend(matrix.get("semantic_queries", []))
    entries.extend(matrix.get("business_queries", []))
    return matrix, entries


async def run_search_engine(query: str, max_results: int = 8) -> List[Dict[str, str]]:
    """
    Run search using the configured search engine (Tavily/Google/Bing).
    This is the primary search method that replaces the old Bing RSS approach.
    """
    if not SEARCH_ENGINE_AVAILABLE:
        print(f"  Warning: Search engine not available for query: {query}")
        return []
    
    engine = SearchEngine()
    try:
        results = await engine.search(query, max_results=max_results)
        
        # Convert to standard format
        items = []
        for r in results:
            items.append({
                "title": r.title,
                "link": r.url,
                "published": "",  # Tavily doesn't provide publish date
                "snippet": r.snippet,
                "domain": r.source,
                "source_tier": f"T{r.tier}",
                "tier_reason": f"Source tier {r.tier} based on domain",
            })
        
        print(f"  ✓ Search returned {len(items)} results for: {query[:50]}...")
        return items
        
    except Exception as e:
        print(f"  ✗ Search failed for '{query}': {e}")
        return []
    finally:
        await engine.close()


def dedupe_items(items: List[Dict[str, str]], max_items: int) -> List[Dict[str, str]]:
    """Remove duplicate items based on link URL."""
    seen: set[str] = set()
    deduped: List[Dict[str, str]] = []
    for item in items:
        link = item.get("link", "")
        if not link or link in seen:
            continue
        seen.add(link)
        deduped.append(item)
        if len(deduped) >= max_items:
            break
    return deduped


def classify_source_tier(domain: str, title: str) -> tuple[str, str]:
    """Classify source tier based on domain and title markers."""
    domain = domain.lower().removeprefix("www.")
    title = title.strip()

    if any(marker in title for marker in T0_TITLE_MARKERS):
        return "T0", "顶级政治信号标记（中央核心会议/领导人）"

    if domain in T1_DOMAINS or any(d in domain for d in T1_DOMAINS):
        return "T1", "中央权威发布渠道（新华社/政府网/央视）"

    if domain.endswith(".gov.cn"):
        if any(marker in title for marker in LOCAL_TITLE_MARKERS):
            return "T3", "地方政府执行类文件"
        return "T2", "政府部委实施渠道"

    if domain in T2_DOMAINS or any(d in domain for d in T2_DOMAINS):
        return "T2", "中央媒体评论渠道（人民日报/光明日报）"

    return "T3", "市场化媒体或外部解读渠道"


def write_markdown(path: Path, topic: str, runs: List[Dict[str, Any]], tier_counts: Dict[str, int]) -> None:
    """Write a markdown summary of search results."""
    lines = [
        f"# 参考资料检索报告: {topic}",
        "",
        f"- 生成时间: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- 信源分布: T0(顶级)={tier_counts.get('T0', 0)}, T1(权威)={tier_counts.get('T1', 0)}, T2(官方)={tier_counts.get('T2', 0)}, T3(市场)={tier_counts.get('T3', 0)}",
        "",
        "---",
        "",
    ]
    for run in runs:
        query_type = run.get('type', 'unknown')
        type_label = {
            'horizontal': '横向检索（各地区/部门）',
            'vertical': '纵向检索（历史对比）',
            'semantic': '语义检索',
            'business': '商业影响检索',
        }.get(query_type, query_type)
        
        lines.append(f"## {type_label}")
        lines.append(f"**检索意图**: {run.get('intent', 'N/A')}")
        lines.append(f"**检索关键词**: `{run['seed_query']}`")
        lines.append("")
        
        if run["items"]:
            lines.append("| 标题 | 来源 | 信源等级 | 链接 |")
            lines.append("|---|---|---|---|")
            for item in run["items"]:
                title = item["title"].replace("|", "\\|")[:60] + ("..." if len(item["title"]) > 60 else "")
                domain = item["domain"].replace("|", "\\|")
                tier = item.get("source_tier", "T3")
                tier_reason = item.get("tier_reason", "")
                link = item["link"]
                lines.append(f"| {title} | {domain} | {tier} | [链接]({link}) |")
        else:
            lines.append("*（未找到相关结果）*")
        lines.append("")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


async def async_main(args: argparse.Namespace) -> None:
    """Async main function for search operations."""
    matrix, entries = load_query_entries(Path(args.queries_json))
    
    print("\n" + "="*60)
    print("🔍 开始横纵向资料检索")
    print("="*60)
    print(f"主题: {matrix.get('topic', 'N/A')}")
    print(f"检索条目数: {len(entries)}")
    print()

    all_runs: List[Dict[str, Any]] = []
    global_links: Dict[str, Dict[str, str]] = {}
    tier_counts = {"T0": 0, "T1": 0, "T2": 0, "T3": 0}

    for i, entry in enumerate(entries, 1):
        base_query = entry.get("query", "").strip()
        if not base_query:
            continue
        
        query_type = entry.get("type", "unknown")
        query_intent = entry.get("intent", "")
        
        print(f"\n[{i}/{len(entries)}] {query_type}: {query_intent}")
        print(f"  检索关键词: {base_query}")

        # Use our search engine module
        fetched = await run_search_engine(base_query, max_results=args.max_per_query)
        
        # Classify source tiers if not already done
        for item in fetched:
            if "source_tier" not in item or not item["source_tier"]:
                tier, reason = classify_source_tier(
                    item.get("domain", ""), 
                    item.get("title", "")
                )
                item["source_tier"] = tier
                item["tier_reason"] = reason
            item["matched_query"] = base_query

        items = dedupe_items(fetched, args.max_per_query)
        
        for item in items:
            if item.get("link"):
                global_links[item["link"]] = item
                tier = item.get("source_tier", "T3")
                if tier not in tier_counts:
                    tier_counts[tier] = 0
                tier_counts[tier] += 1

        all_runs.append(
            {
                "type": query_type,
                "intent": query_intent,
                "seed_query": base_query,
                "items": items,
                "result_count": len(items),
            }
        )

    # Build output payload with clear structure for report generation
    payload = {
        "topic": matrix.get("topic", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_query_file": str(Path(args.queries_json).resolve()),
        "search_provider": os.environ.get("SEARCH_API_PROVIDER", "tavily"),
        "query_runs": all_runs,
        "unique_item_count": len(global_links),
        "tier_counts": tier_counts,
        "unique_items": list(global_links.values()),
        # Summary for report generation
        "summary": {
            "total_sources": len(global_links),
            "horizontal_sources": sum(1 for r in all_runs if r["type"] == "horizontal" for _ in r["items"]),
            "vertical_sources": sum(1 for r in all_runs if r["type"] == "vertical" for _ in r["items"]),
            "tier_distribution": tier_counts,
        }
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    
    print("\n" + "="*60)
    print("✅ 检索完成")
    print("="*60)
    print(f"总计检索到 {len(global_links)} 条独立资料")
    print(f"信源分布: T0={tier_counts.get('T0', 0)}, T1={tier_counts.get('T1', 0)}, T2={tier_counts.get('T2', 0)}, T3={tier_counts.get('T3', 0)}")
    print(f"输出文件: {output_path}")

    if args.markdown:
        md_path = Path(args.markdown)
        write_markdown(md_path, matrix.get("topic", "unknown-topic"), all_runs, tier_counts)
        print(f"Markdown报告: {md_path}")


def main() -> None:
    """Main entry point."""
    args = parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
