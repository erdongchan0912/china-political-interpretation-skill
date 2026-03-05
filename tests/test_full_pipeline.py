#!/usr/bin/env python3
"""Test complete LLM analysis pipeline with a news URL."""

import asyncio
import json
from pathlib import Path
import sys
import os
from dotenv import load_dotenv

# Load environment variables
env_file = Path(__file__).parent.parent / "config" / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"✅ Loaded .env from: {env_file}")

# Add backend core to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend" / "core"))

from llm_client import LLMClient, AnalysisTask

async def test_url_analysis():
    """Test LLM analysis with the provided news URL."""
    
    # Test URL
    url = "https://www.news.cn/politics/leaders/20260105/4eabcc465aa14e868bd568858b8f434c/c.html"
    
    print("="*60)
    print("🧪 Testing Complete LLM Analysis Pipeline")
    print("="*60)
    print(f"\nTest URL: {url}")
    print()
    
    client = LLMClient()
    
    if not client.config.api_key:
        print("❌ GEMINI_API_KEY not configured!")
        await client.close()
        return
    
    print(f"✅ API Key: Configured")
    print(f"🤖 Model: {client.config.model}")
    print(f"🌐 API URL: {client.config.api_url}\n")
    
    try:
        # Step 1: Material Understanding
        print("="*60)
        print("Step 1/4: 🤖 LLM Understanding Material")
        print("="*60)
        
        material_text = f"""
        新闻链接：{url}
        
        请分析这个政治新闻链接的内容，识别：
        1. 材料类型（会议/讲话/政策文件等）
        2. 发布主体（中共中央/国务院/部委等）
        3. 核心主题
        4. 关键人物
        5. 关键机构
        6. 政策信号
        7. 新提法/新表述
        """
        
        result = await client.analyze(
            AnalysisTask.MATERIAL_UNDERSTANDING,
            material_text
        )
        
        print("\n✅ Material Understanding Result:")
        print("-" * 60)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("-" * 60)
        print()
        
        # Step 2: Generate Search Strategy
        print("="*60)
        print("Step 2/4: 🤖 LLM Generating Search Strategy")
        print("="*60)
        
        search_strategy = await client.analyze(
            AnalysisTask.GENERATE_SEARCH_STRATEGY,
            material_text,
            {"material_understanding": json.dumps(result, ensure_ascii=False)}
        )
        
        print("\n✅ Search Strategy Generated:")
        print("-" * 60)
        if "vertical_queries" in search_strategy:
            print(f"Vertical queries: {len(search_strategy['vertical_queries'])} items")
        if "horizontal_queries" in search_strategy:
            print(f"Horizontal queries: {len(search_strategy['horizontal_queries'])} items")
        print("-" * 60)
        print()
        
        # Step 3: Policy Analysis (simulated context)
        print("="*60)
        print("Step 3/4: 🤖 LLM Deep Policy Analysis")
        print("="*60)
        
        policy_analysis = await client.analyze(
            AnalysisTask.POLICY_ANALYSIS,
            material_text,
            {
                "horizontal_context": "暂无横向检索结果",
                "vertical_context": "暂无纵向检索结果"
            }
        )
        
        print("\n✅ Policy Analysis Result:")
        print("-" * 60)
        if "core_judgments" in policy_analysis:
            print(f"Core judgments: {len(policy_analysis['core_judgments'])} items")
            for judgment in policy_analysis.get("core_judgments", [])[:3]:
                print(f"  - [{judgment.get('evidence_type', 'I')}] {judgment.get('judgment', '')[:80]}...")
        print("-" * 60)
        print()
        
        # Step 4: Generate Executive Summary
        print("="*60)
        print("Step 4/4: 🤖 LLM Generating Executive Summary")
        print("="*60)
        
        full_analysis = {
            "policy_analysis": policy_analysis,
            "search_strategy": search_strategy,
            "material_understanding": result
        }
        
        executive_summary = await client.analyze(
            AnalysisTask.GENERATE_EXECUTIVE_SUMMARY,
            context={"full_analysis": json.dumps(full_analysis, ensure_ascii=False)}
        )
        
        print("\n✅ Executive Summary:")
        print("-" * 60)
        if "one_liner" in executive_summary:
            print(f"One-liner: {executive_summary.get('one_liner', 'N/A')}")
        if "core_conclusions" in executive_summary:
            print(f"Core conclusions: {len(executive_summary.get('core_conclusions', []))} items")
        print("-" * 60)
        print()
        
        print("="*60)
        print("🎉 SUCCESS! Complete LLM Analysis Pipeline Test PASSED")
        print("="*60)
        print()
        print("Next steps:")
        print("1. Open Web UI: http://localhost:5173")
        print("2. Upload this URL or other materials")
        print("3. Watch real-time LLM analysis progress")
        print("4. Download HTML/PDF reports")
        
    except Exception as e:
        print("="*60)
        print("❌ LLM Analysis Pipeline failed:")
        print("="*60)
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {e}")
        print("="*60)
        import traceback
        traceback.print_exc()
    
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_url_analysis())
