#!/usr/bin/env python3
"""
Search Engine Module for China Political Interpretation
========================================================

This module provides a unified interface for searching historical policy documents.
Supports multiple search providers: Google Custom Search, Bing, SerpAPI.

Configuration:
- Set GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID in environment variables
- Or use other providers by setting SEARCH_API_PROVIDER
"""

import os
import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent.parent / "config" / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass


class SearchProvider(Enum):
    """Supported search providers."""
    TAVILY = "tavily"
    GOOGLE = "google"
    BING = "bing"
    SERPAPI = "serpapi"


@dataclass
class SearchResult:
    """A single search result."""
    title: str
    url: str
    snippet: str
    source: str  # Domain name
    rank: int
    relevance_score: float = 0.0
    tier: int = 3  # 1=highest trust, 4=lowest trust


@dataclass
class SearchConfig:
    """Configuration for the search client."""
    provider: SearchProvider = SearchProvider.TAVILY
    api_key: str = ""
    engine_id: str = ""  # For Google Custom Search
    max_results: int = 10
    timeout: int = 30


class SearchEngine:
    """
    Unified search engine for retrieving historical policy documents.
    
    Usage:
        engine = SearchEngine()
        results = await engine.search("2023年全国宣传部长会议")
    """
    
    # Trusted source tiers (based on V4 architecture document)
    TIER_1_SOURCES = [
        "xinhuanet.com", "news.cn",  # 新华社
        "gov.cn", "www.gov.cn",  # 中国政府网
        "cctv.com", "cntv.cn",  # 央视网
        "people.com.cn", "paper.people.com.cn",  # 人民日报
    ]
    
    TIER_2_SOURCES = [
        "ce.cn",  # 经济日报
        "gmw.cn",  # 光明日报
        "china.com.cn",  # 中国网
        "chinadaily.com.cn",  # 中国日报
        "legaldaily.com.cn",  # 法治日报
    ]
    
    TIER_3_SOURCES = [
        # 省级党报和地方政府网站
        "bjnews.com.cn", "bjd.com.cn",  # 北京
        "jfdaily.com", "shobserver.com",  # 上海
        "southcn.com", "gd.gov.cn",  # 广东
        "enorth.com.cn",  # 天津
        "cqnews.net",  # 重庆
    ]
    
    def __init__(self, config: Optional[SearchConfig] = None):
        """Initialize the search engine with configuration."""
        if config:
            self.config = config
        else:
            # Load from environment variables - Default to Tavily
            provider_str = os.environ.get("SEARCH_API_PROVIDER", "tavily").lower()
            provider = SearchProvider.TAVILY
            if provider_str == "google":
                provider = SearchProvider.GOOGLE
            elif provider_str == "bing":
                provider = SearchProvider.BING
            elif provider_str == "serpapi":
                provider = SearchProvider.SERPAPI
            
            # Tavily API Key (优先)
            tavily_key = os.environ.get("TAVILY_API_KEY", "")
            google_key = os.environ.get("GOOGLE_SEARCH_API_KEY", "")
            
            # If Tavily key is set, use Tavily regardless of provider setting
            if tavily_key:
                provider = SearchProvider.TAVILY
            
            self.config = SearchConfig(
                provider=provider,
                api_key=tavily_key or google_key,
                engine_id=os.environ.get("GOOGLE_SEARCH_ENGINE_ID", ""),
            )
        
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _get_source_tier(self, url: str) -> int:
        """Determine the trust tier for a source URL."""
        url_lower = url.lower()
        
        for source in self.TIER_1_SOURCES:
            if source in url_lower:
                return 1
        
        for source in self.TIER_2_SOURCES:
            if source in url_lower:
                return 2
        
        for source in self.TIER_3_SOURCES:
            if source in url_lower:
                return 3
        
        return 4  # Default to lowest tier
    
    async def search(
        self,
        query: str,
        max_results: Optional[int] = None,
        site_restriction: Optional[str] = None,
        date_range: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Perform a search and return ranked results.
        
        Args:
            query: Search query string
            max_results: Maximum number of results to return
            site_restriction: Restrict search to specific site (e.g., "gov.cn")
            date_range: Date range filter (e.g., "d365" for past year)
        
        Returns:
            List of SearchResult objects, sorted by relevance and tier
        """
        if not self.config.api_key:
            print("Warning: Search API key not configured. Returning empty results.")
            return []
        
        max_results = max_results or self.config.max_results
        
        # Modify query with site restriction
        if site_restriction:
            query = f"site:{site_restriction} {query}"
        
        # Call appropriate provider
        if self.config.provider == SearchProvider.TAVILY:
            raw_results = await self._search_tavily(query, max_results, date_range)
        elif self.config.provider == SearchProvider.GOOGLE:
            raw_results = await self._search_google(query, max_results, date_range)
        elif self.config.provider == SearchProvider.BING:
            raw_results = await self._search_bing(query, max_results, date_range)
        else:
            raw_results = await self._search_serpapi(query, max_results, date_range)
        
        # Process and rank results
        results = []
        for i, item in enumerate(raw_results[:max_results]):
            url = item.get("link", item.get("url", ""))
            result = SearchResult(
                title=item.get("title", ""),
                url=url,
                snippet=item.get("snippet", item.get("description", "")),
                source=self._extract_domain(url),
                rank=i + 1,
                tier=self._get_source_tier(url),
            )
            results.append(result)
        
        # Sort by tier first, then by rank
        results.sort(key=lambda x: (x.tier, x.rank))
        
        return results
    
    async def _search_tavily(
        self,
        query: str,
        max_results: int,
        date_range: Optional[str] = None,
    ) -> List[Dict]:
        """Search using Tavily API - Optimized for AI applications."""
        session = await self._get_session()
        
        url = "https://api.tavily.com/search"
        
        # Tavily API payload
        payload = {
            "api_key": self.config.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",  # or "advanced" for more detail
            "include_answer": False,
            "include_raw_content": False,
        }
        
        # Add time range if specified
        # Tavily API uses `time_range` with values: "day", "week", "month", "year"
        if date_range:
            tavily_range = self._date_range_to_tavily(date_range)
            if tavily_range:
                payload["time_range"] = tavily_range
        
        try:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"Tavily API error ({response.status}): {error_text}")
                    return []
                
                data = await response.json()
                
                # Convert Tavily results to standard format
                results = []
                for item in data.get("results", []):
                    results.append({
                        "title": item.get("title", ""),
                        "link": item.get("url", ""),
                        "snippet": item.get("content", ""),
                    })
                
                return results
                
        except asyncio.TimeoutError:
            print(f"Tavily API timeout after {self.config.timeout} seconds")
            return []
        except Exception as e:
            print(f"Tavily API error: {e}")
            return []
    
    async def _search_google(
        self,
        query: str,
        max_results: int,
        date_range: Optional[str] = None,
    ) -> List[Dict]:
        """Search using Google Custom Search API."""
        if not self.config.engine_id:
            print("Warning: Google Search Engine ID not configured.")
            return []
        
        session = await self._get_session()
        
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": self.config.api_key,
            "cx": self.config.engine_id,
            "q": query,
            "num": max_results,
        }
        
        if date_range:
            params["dateRestrict"] = date_range
        
        try:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"Google Search API error ({response.status}): {error_text}")
                    return []
                
                data = await response.json()
                return data.get("items", [])
                
        except asyncio.TimeoutError:
            print(f"Google Search API timeout after {self.config.timeout} seconds")
            return []
        except Exception as e:
            print(f"Google Search API error: {e}")
            return []
    
    async def _search_bing(
        self,
        query: str,
        max_results: int,
        date_range: Optional[str] = None,
    ) -> List[Dict]:
        """Search using Bing Search API."""
        session = await self._get_session()
        
        url = "https://api.bing.microsoft.com/v7.0/search"
        headers = {
            "Ocp-Apim-Subscription-Key": self.config.api_key
        }
        params = {
            "q": query,
            "count": max_results,
            "responseFilter": "Webpages",
        }
        
        try:
            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"Bing Search API error ({response.status}): {error_text}")
                    return []
                
                data = await response.json()
                return data.get("webPages", {}).get("value", [])
                
        except Exception as e:
            print(f"Bing Search API error: {e}")
            return []
    
    async def _search_serpapi(
        self,
        query: str,
        max_results: int,
        date_range: Optional[str] = None,
    ) -> List[Dict]:
        """Search using SerpAPI."""
        session = await self._get_session()
        
        url = "https://serpapi.com/search"
        params = {
            "api_key": self.config.api_key,
            "q": query,
            "num": max_results,
            "engine": "google",
        }
        
        try:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"SerpAPI error ({response.status}): {error_text}")
                    return []
                
                data = await response.json()
                return data.get("organic_results", [])
                
        except Exception as e:
            print(f"SerpAPI error: {e}")
            return []

    def _date_range_to_days(self, date_range: str) -> int:
        """Convert compact date range token to days."""
        token = date_range.strip().lower()
        if not token:
            return 365
        try:
            if token.startswith("d"):
                return max(int(token[1:]), 1)
            if token.startswith("m"):
                return max(int(token[1:]), 1) * 30
            if token.startswith("y"):
                return max(int(token[1:]), 1) * 365
        except ValueError:
            return 365
        return 365

    def _date_range_to_tavily(self, date_range: str) -> Optional[str]:
        """Convert compact date range token to Tavily time_range value.

        Tavily accepts: "day", "week", "month", "year".
        We map our internal tokens (d7, m1, y1, etc.) to the closest match.
        """
        days = self._date_range_to_days(date_range)
        if days <= 1:
            return "day"
        if days <= 7:
            return "week"
        if days <= 31:
            return "month"
        return "year"
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain name from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return (parsed.netloc or url).lower()
        except Exception:
            return url.lower()
    
    async def search_policy_history(
        self,
        policy_name: str,
        years: int = 5,
    ) -> List[SearchResult]:
        """
        Search for historical versions of a policy/meeting.
        
        Args:
            policy_name: Name of the policy or meeting (e.g., "全国宣传部长会议")
            years: Number of years to search back
        
        Returns:
            List of historical policy documents
        """
        results = []
        
        # Search for each year
        current_year = datetime.now().year
        for year in range(current_year, current_year - years, -1):
            query = f"{year}年 {policy_name}"
            year_results = await self.search(
                query,
                max_results=5,
                date_range=f"y{current_year - year + 1}",
            )
            
            for result in year_results:
                # Verify the year is in the title or snippet
                if str(year) in result.title or str(year) in result.snippet:
                    results.append(result)
        
        return results
    
    async def search_regional_policies(
        self,
        policy_name: str,
        regions: Optional[List[str]] = None,
    ) -> List[SearchResult]:
        """
        Search for regional versions of a policy.
        
        Args:
            policy_name: Name of the central policy
            regions: List of provinces/cities to search (default: all major regions)
        
        Returns:
            List of regional policy documents
        """
        if not regions:
            regions = [
                "北京", "上海", "广东", "江苏", "浙江",
                "山东", "四川", "湖北", "河南", "福建",
            ]
        
        results = []
        
        for region in regions:
            query = f"{region} {policy_name}"
            region_results = await self.search(query, max_results=3)
            results.extend(region_results)
        
        return results


# Convenience functions
_engine: Optional[SearchEngine] = None


def get_engine() -> SearchEngine:
    """Get or create the global search engine."""
    global _engine
    if _engine is None:
        _engine = SearchEngine()
    return _engine


async def search(query: str, max_results: int = 10) -> List[SearchResult]:
    """Quick search function."""
    engine = get_engine()
    return await engine.search(query, max_results)


async def search_policy_history(policy_name: str, years: int = 5) -> List[SearchResult]:
    """Search for historical policy documents."""
    engine = get_engine()
    return await engine.search_policy_history(policy_name, years)


# CLI interface for testing
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Search Engine for Policy Documents")
    parser.add_argument("--query", type=str, help="Search query")
    parser.add_argument("--test", action="store_true", help="Run test")
    
    args = parser.parse_args()
    
    async def test():
        engine = SearchEngine()
        
        print("="*60)
        print("Search Engine Test")
        print("="*60)
        print(f"Provider: {engine.config.provider.value}")
        print(f"API Key: {'Configured' if engine.config.api_key else 'Not set'}")
        print(f"Engine ID: {'Configured' if engine.config.engine_id else 'Not set'}")
        print()
        
        if engine.config.api_key and engine.config.engine_id:
            print("Testing search: 2023年全国宣传部长会议")
            results = await engine.search("2023年全国宣传部长会议", max_results=5)
            
            print(f"\nFound {len(results)} results:")
            for r in results:
                print(f"  [{r.tier}] {r.title}")
                print(f"      {r.url}")
                print(f"      {r.snippet[:100]}...")
                print()
        else:
            print("Please configure GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID")
        
        await engine.close()
    
    if args.test or args.query:
        asyncio.run(test())
