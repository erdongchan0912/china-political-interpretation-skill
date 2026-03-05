#!/usr/bin/env python3
"""Simple test for LLM API"""

import asyncio
import aiohttp
import json
import os
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent / "config" / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass

async def test_api():
    # Configuration from environment
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    api_url = os.environ.get("LLM_API_URL") or os.environ.get("GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta")
    model = os.environ.get("LLM_MODEL") or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    provider = os.environ.get("LLM_PROVIDER", "gemini")
    
    if not api_key:
        print("❌ Error: No API key found!")
        print("Please set LLM_API_KEY or GEMINI_API_KEY in your environment or config/.env file")
        return False
    
    print("="*60)
    print("Testing LLM API")
    print("="*60)
    print(f"Provider: {provider}")
    print(f"URL: {api_url}")
    print(f"Model: {model}")
    print(f"API Key: {'*' * 8}...{api_key[-4:]}")
    print()
    
    test_prompt = "请用一句话总结：什么是新质生产力？"
    print(f"📝 Prompt: {test_prompt}")
    print("\n🚀 Sending request...\n")
    
    try:
        async with aiohttp.ClientSession() as session:
            if provider == "openai":
                # OpenAI format
                url = f"{api_url}/chat/completions"
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "user", "content": test_prompt}
                    ],
                    "temperature": 0.7,
                }
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                }
            else:
                # Gemini format
                url = f"{api_url}/models/{model}:generateContent"
                payload = {
                    "contents": [{"parts": [{"text": test_prompt}]}],
                    "generationConfig": {"temperature": 0.7}
                }
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key
                }
            
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
                print(f"Status Code: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    print("\n✅ SUCCESS!\n")
                    
                    # Extract answer based on provider
                    if provider == "openai":
                        if "choices" in data and len(data["choices"]) > 0:
                            answer = data["choices"][0]["message"]["content"]
                    else:
                        if "candidates" in data and len(data["candidates"]) > 0:
                            answer = data["candidates"][0]["content"]["parts"][0]["text"]
                    
                    print(f"📖 Answer:\n{answer}\n")
                    return True
                else:
                    error_text = await response.text()
                    print(f"\n❌ FAILED!\n")
                    print(f"Error Status: {response.status}")
                    print(f"Error Response: {error_text}")
                    return False
                    
    except Exception as e:
        print(f"\n❌ EXCEPTION!\n")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_api())
    print("\n" + "="*60)
    if result:
        print("🎉 TEST PASSED - API is working!")
    else:
        print("⚠️  TEST FAILED - Check errors above")
    print("="*60)
