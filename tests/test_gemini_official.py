#!/usr/bin/env python3
"""Test Gemini API using official google-genai SDK."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_file = Path(__file__).parent.parent / "config" / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"✅ Loaded .env from: {env_file}")
else:
    print(f"⚠️  .env file not found at: {env_file}")

# Get configuration
api_key = os.environ.get("GEMINI_API_KEY", "")
api_url = os.environ.get("GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1")
model = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")

print("="*60)
print("🧪 Testing Gemini API with Official SDK")
print("="*60)
print(f"\nConfiguration:")
print(f"  API Key: {'✅ Configured' if api_key else '❌ Missing'}")
print(f"  API URL: {api_url}")
print(f"  Model: {model}")
print()

if not api_key:
    print("❌ GEMINI_API_KEY is not configured!")
    print("\nPlease edit .env file and add your API key.")
    exit(1)

try:
    # Import official SDK
    from google import genai
    
    # Create client with API key
    client = genai.Client(api_key=api_key)
    
    print("✅ Successfully created Gemini client")
    print()
    
    # Test content generation
    test_prompt = "用一句话总结：什么是政治文本分析？"
    print(f"📝 Test prompt: {test_prompt}")
    print()
    print("⏳ Calling Gemini API...")
    print()
    
    response = client.models.generate_content(
        model=model,
        contents=test_prompt
    )
    
    print("="*60)
    print("✅ Gemini API Response:")
    print("="*60)
    print(response.text)
    print("="*60)
    print()
    print("🎉 SUCCESS! Gemini API is working correctly!")
    print()
    
except Exception as e:
    print("="*60)
    print("❌ Gemini API call failed:")
    print("="*60)
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {e}")
    print("="*60)
    print()
    
    # Provide troubleshooting suggestions
    print("🔍 Possible issues:")
    print()
    print("1. **API Key Invalid**")
    print("   - Check if API key is copied correctly (no extra spaces)")
    print("   - Verify API key at: https://aistudio.google.com/apikey")
    print()
    print("2. **Model Name Incorrect**")
    print(f"   - Current model: {model}")
    print("   - Valid models: gemini-3-pro-preview, gemini-3-flash-preview")
    print()
    print("3. **API Endpoint Issue**")
    print(f"   - Current endpoint: {api_url}")
    print("   - Try changing between /v1 and /v1beta")
    print()
    print("4. **Network/Firewall**")
    print("   - Check if you can access Google APIs")
    print("   - Try using a proxy if needed")
    print()
    
    import traceback
    traceback.print_exc()
