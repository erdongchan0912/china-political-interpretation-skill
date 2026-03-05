#!/usr/bin/env python3
"""Test the complete LLM-powered analysis pipeline."""

import asyncio
import json
from pathlib import Path
import sys

# Add backend core to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend" / "core"))

from llm_client import LLMClient, AnalysisTask

async def test_material_understanding():
    """Test LLM material understanding with real API."""
    
    # Load environment variables first
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent / "config" / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✅ Loaded .env from: {env_file}")
    else:
        print(f"⚠️  .env file not found at: {env_file}")
    
    # Load test material
    material_path = Path(__file__).parent / "test_material.txt"
    if not material_path.exists():
        print(f"❌ Test material not found: {material_path}")
        return
    
    material_text = material_path.read_text(encoding="utf-8")
    
    print("="*60)
    print("🧪 Testing LLM Material Understanding")
    print("="*60)
    print(f"\nMaterial: {material_path.name}")
    print(f"Length: {len(material_text)} characters\n")
    
    client = LLMClient()
    
    if not client.config.api_key:
        print("❌ GEMINI_API_KEY not configured!")
        print("\nPlease check your .env file:")
        print("  cp .env.example .env")
        print("  # Edit .env and add your API key")
        await client.close()
        return
    
    print(f"✅ API Key: Configured")
    print(f"🤖 Model: {client.config.model}")
    print(f"🌐 API URL: {client.config.api_url}\n")
    
    try:
        print("⏳ Calling Gemini API...")
        result = await client.analyze(
            AnalysisTask.MATERIAL_UNDERSTANDING,
            material_text
        )
        
        print("\n✅ LLM Analysis Result:")
        print("-" * 60)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("-" * 60)
        
        # Validate result structure
        if isinstance(result, dict):
            print("\n✅ Result is valid JSON structure")
            
            if "material_type" in result:
                print(f"   - Material Type: {result.get('material_type', 'N/A')}")
            if "issuing_body" in result:
                print(f"   - Issuing Body: {result.get('issuing_body', 'N/A')}")
            if "core_topic" in result:
                print(f"   - Core Topic: {result.get('core_topic', 'N/A')}")
            
            print("\n✅ LLM Material Understanding Test PASSED")
        else:
            print("\n⚠️  Result is not a dictionary")
        
    except Exception as e:
        print(f"\n❌ LLM API call failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_material_understanding())
