#!/usr/bin/env python3
"""
Test script for company LLM API (gemini-3.1-pro-preview)
"""

import asyncio
import os
from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent / "config" / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    print(f"✅ Loaded .env file: {env_file}")
except ImportError:
    print("⚠️  python-dotenv not installed, using system env")

# Print configuration
print("\n" + "="*60)
print("LLM Configuration")
print("="*60)
print(f"Provider: {os.environ.get('LLM_PROVIDER', 'not set')}")
print(f"API Key: {os.environ.get('LLM_API_KEY', 'not set')[:20]}...")
print(f"API URL: {os.environ.get('LLM_API_URL', 'not set')}")
print(f"Model: {os.environ.get('LLM_MODEL', 'not set')}")
print()

async def test_llm_api():
    """Test the LLM API with a simple prompt."""
    try:
        # Import the client
        import sys
        SCRIPT_DIR = Path(__file__).parent.parent / "backend" / "core"
        sys.path.insert(0, str(SCRIPT_DIR))
        
        from llm_client import LLMClient, LLMConfig
        
        # Create client with config from env
        print("🔧 Creating LLM client...")
        client = LLMClient()
        
        print(f"   Provider: {client.config.provider}")
        print(f"   Model: {client.config.model}")
        print(f"   API URL: {client.config.api_url}")
        print()
        
        # Test prompt
        test_prompt = "请用一句话总结：什么是新质生产力？"
        print(f"📝 Test prompt: {test_prompt}")
        print()
        
        # Call the API
        print("🚀 Calling LLM API...")
        response = await client._call_gemini(test_prompt)
        
        print("\n" + "="*60)
        print("✅ SUCCESS! API call completed")
        print("="*60)
        print(f"\nResponse:\n{response}\n")
        
        return True
        
    except Exception as e:
        print("\n" + "="*60)
        print("❌ FAILED! API call failed")
        print("="*60)
        print(f"\nError type: {type(e).__name__}")
        print(f"Error message: {e}\n")
        return False


async def test_analysis_task():
    """Test a real analysis task."""
    try:
        import sys
        SCRIPT_DIR = Path(__file__).parent.parent / "backend" / "core"
        sys.path.insert(0, str(SCRIPT_DIR))
        
        from llm_client import LLMClient, AnalysisTask
        
        client = LLMClient()
        
        # Test material understanding task
        test_material = """
        中共中央政治局 2026 年 2 月 27 日召开会议，讨论国务院拟提请第十四届全国人民代表大会第三次会议审议的《政府工作报告》稿。
        会议指出，2025 年是党和国家事业发展具有特殊重要意义的一年。
        """
        
        print("\n" + "="*60)
        print("Testing Material Understanding Task")
        print("="*60)
        print(f"Input material: {test_material[:100]}...\n")
        
        result = await client.analyze(
            AnalysisTask.MATERIAL_UNDERSTANDING,
            content=test_material
        )
        
        print("✅ Material understanding result:")
        print(result)
        print()
        
        return True
        
    except Exception as e:
        print("\n" + "="*60)
        print("❌ Material understanding task failed")
        print("="*60)
        print(f"Error: {e}\n")
        return False


async def main():
    print("="*60)
    print("Company LLM API Test - Gemini 3.1 Pro Preview")
    print("="*60)
    print()
    
    # Test 1: Basic API call
    print("Test 1: Basic API Call")
    print("-"*60)
    success1 = await test_llm_api()
    
    # Test 2: Real analysis task
    print("\n\nTest 2: Material Understanding Task")
    print("-"*60)
    success2 = await test_analysis_task()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Basic API Call: {'✅ PASS' if success1 else '❌ FAIL'}")
    print(f"Analysis Task: {'✅ PASS' if success2 else '❌ FAIL'}")
    print("="*60)
    
    if success1 and success2:
        print("\n🎉 All tests passed! Company API is working correctly.")
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")


if __name__ == "__main__":
    asyncio.run(main())
