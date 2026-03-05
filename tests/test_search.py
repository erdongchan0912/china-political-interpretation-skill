#!/usr/bin/env python3
"""Test Google Custom Search API."""

import asyncio
import sys
from pathlib import Path

# Add backend core to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend" / "core"))

from dotenv import load_dotenv

# Load environment
env_file = Path(__file__).parent.parent / "config" / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"✅ Loaded .env from: {env_file}")

from search_engine import SearchEngine


async def test_search():
    print("=" * 60)
    print("🔍 Testing Google Custom Search API")
    print("=" * 60)
    
    engine = SearchEngine()
    
    print(f"\nConfiguration:")
    print(f"  Provider: {engine.config.provider.value}")
    print(f"  API Key: {'✅ Configured' if engine.config.api_key else '❌ Not set'}")
    print(f"  Engine ID: {'✅ Configured' if engine.config.engine_id else '❌ Not set'}")
    print()
    
    if not engine.config.api_key or not engine.config.engine_id:
        print("❌ Please configure GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID")
        await engine.close()
        return
    
    # Test search
    query = "2024年全国宣传部长会议"
    print(f"🔎 Searching for: {query}")
    print()
    
    results = await engine.search(query, max_results=5)
    
    if results:
        print(f"✅ Found {len(results)} results:\n")
        for r in results:
            tier_emoji = "🥇" if r.tier == 1 else "🥈" if r.tier == 2 else "🥉" if r.tier == 3 else "📌"
            print(f"{tier_emoji} [Tier {r.tier}] {r.title}")
            print(f"   📎 {r.url}")
            print(f"   📝 {r.snippet[:100]}...")
            print(f"   🏛️ {r.source}")
            print()
    else:
        print("❌ No results found. Please check your configuration.")
    
    await engine.close()
    
    print("=" * 60)
    print("🎉 Search test completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_search())
