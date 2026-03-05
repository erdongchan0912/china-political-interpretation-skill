#!/usr/bin/env python3
"""Smart content extractor with anti-crawling bypass for China political analysis."""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import re
import ssl
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

try:
    from paddleocr import PaddleOCR
    HAS_PADDLEOCR = True
except ImportError:
    HAS_PADDLEOCR = False

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    from pdf2image import convert_from_path
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False

try:
    from wechat_article_to_markdown import (
        extract_metadata,
        process_content,
        convert_to_markdown,
        build_markdown,
    )
    from camoufox.async_api import AsyncCamoufox
    HAS_WECHAT_TOOL = True
except ImportError:
    HAS_WECHAT_TOOL = False


USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

CONTENT_SELECTORS = [
    "article",
    "main",
    ".article-content",
    ".post-content",
    ".entry-content",
    ".content",
    "#content",
    ".article-body",
    ".news-content",
    ".TRS_Editor",
    ".pages_content",
    ".article",
]

MIN_CONTENT_LENGTH = 200


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract content from URL, image, or PDF with anti-crawling bypass."
    )
    parser.add_argument("--url", help="URL to extract content from.")
    parser.add_argument("--image", help="Image file path for OCR extraction.")
    parser.add_argument("--pdf", help="PDF file path for text extraction.")
    parser.add_argument("--output", help="Output file path for extracted text.")
    parser.add_argument("--output-json", help="Output JSON with metadata.")
    parser.add_argument(
        "--ocr-engine",
        choices=["tesseract", "paddle", "auto"],
        default="auto",
        help="OCR engine preference.",
    )
    parser.add_argument(
        "--force-browser",
        action="store_true",
        help="Force browser extraction even if standard fetch works.",
    )
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="Force OCR extraction from screenshot.",
    )
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout seconds.")
    return parser.parse_args()


def normalize_text(text: str) -> str:
    """Normalize extracted text by removing excessive whitespace."""
    text = re.sub(r"[\r\n]+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def try_standard_fetch(url: str, timeout: int = 30) -> tuple[str, str]:
    """Try standard HTTP request to fetch content."""
    import random
    
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        context = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            content_type = resp.headers.get("Content-Type", "")
            
            if "gzip" in resp.headers.get("Content-Encoding", ""):
                import gzip
                payload = gzip.decompress(resp.read())
            else:
                payload = resp.read()
            
            encoding = "utf-8"
            if "charset=" in content_type:
                charset_match = re.search(r"charset=([^\s;]+)", content_type)
                if charset_match:
                    encoding = charset_match.group(1)
            
            html = payload.decode(encoding, errors="ignore")
            return html, "standard"
    except Exception as e:
        return "", f"standard_failed: {e}"


def extract_main_content(html: str) -> str:
    """Extract main content from HTML using BeautifulSoup."""
    if not HAS_BS4:
        # Fallback: simple regex extraction
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        return normalize_text(text)
    
    soup = BeautifulSoup(html, "html.parser")
    
    # Remove unwanted elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
        tag.decompose()
    
    # Try content selectors
    for selector in CONTENT_SELECTORS:
        if selector.startswith("."):
            element = soup.find(class_=selector[1:])
        elif selector.startswith("#"):
            element = soup.find(id=selector[1:])
        else:
            element = soup.find(selector)
        
        if element:
            text = element.get_text(separator="\n", strip=True)
            if len(text) >= MIN_CONTENT_LENGTH:
                return normalize_text(text)
    
    # Fallback: get body text
    body = soup.find("body")
    if body:
        text = body.get_text(separator="\n", strip=True)
        return normalize_text(text)
    
    return normalize_text(soup.get_text(separator="\n", strip=True))


async def fetch_with_playwright(url: str, timeout: int = 30) -> tuple[str, bytes | None, str]:
    """Fetch content using Playwright headless browser."""
    if not HAS_PLAYWRIGHT:
        return "", None, "playwright_not_installed"
    
    text = ""
    screenshot = None
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=USER_AGENTS[0],
                locale="zh-CN",
            )
            page = await context.new_page()
            
            # Navigate to URL
            await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            
            # Wait for content to load
            await page.wait_for_timeout(2000)
            
            # Try to extract text from DOM
            for selector in CONTENT_SELECTORS:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        text = await element.inner_text()
                        if len(text) >= MIN_CONTENT_LENGTH:
                            break
                except Exception:
                    continue
            
            # Fallback: get body text
            if len(text) < MIN_CONTENT_LENGTH:
                text = await page.evaluate("document.body.innerText")
            
            # Take screenshot for potential OCR
            screenshot = await page.screenshot(full_page=True, type="png")
            
            await browser.close()
            return normalize_text(text), screenshot, "playwright"
    except Exception as e:
        return "", None, f"playwright_failed: {e}"


def ocr_image(image_data: bytes, engine: str = "auto") -> tuple[str, str]:
    """Perform OCR on image data."""
    if engine == "auto":
        if HAS_PADDLEOCR:
            engine = "paddle"
        elif HAS_TESSERACT:
            engine = "tesseract"
        else:
            return "", "no_ocr_engine_available"
    
    if engine == "paddle" and HAS_PADDLEOCR:
        try:
            ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
            
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(image_data)
                temp_path = f.name
            
            result = ocr.ocr(temp_path, cls=True)
            Path(temp_path).unlink(missing_ok=True)
            
            lines = []
            if result and result[0]:
                for line in result[0]:
                    if line and len(line) >= 2:
                        text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                        lines.append(text)
            
            return normalize_text("\n".join(lines)), "paddle_ocr"
        except Exception as e:
            return "", f"paddle_ocr_failed: {e}"
    
    if engine == "tesseract" and HAS_TESSERACT:
        try:
            image = Image.open(io.BytesIO(image_data))
            text = pytesseract.image_to_string(image, lang="chi_sim+eng")
            return normalize_text(text), "tesseract_ocr"
        except Exception as e:
            return "", f"tesseract_ocr_failed: {e}"
    
    return "", f"ocr_engine_{engine}_not_available"


def extract_from_image(image_path: str, ocr_engine: str = "auto") -> tuple[str, str]:
    """Extract text from image file."""
    try:
        image_data = Path(image_path).read_bytes()
        return ocr_image(image_data, ocr_engine)
    except Exception as e:
        return "", f"image_read_failed: {e}"


def extract_from_pdf(pdf_path: str, ocr_engine: str = "auto") -> tuple[str, str]:
    """Extract text from PDF file."""
    text_parts = []
    
    # Try PyMuPDF first (text extraction)
    if HAS_PYMUPDF:
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)
            doc.close()
            
            combined = normalize_text("\n".join(text_parts))
            if len(combined) >= MIN_CONTENT_LENGTH:
                return combined, "pymupdf_text"
        except Exception:
            pass
    
    # Fallback: OCR from PDF images
    if HAS_PDF2IMAGE:
        try:
            images = convert_from_path(pdf_path, dpi=200)
            for i, image in enumerate(images):
                with io.BytesIO() as buffer:
                    image.save(buffer, format="PNG")
                    image_data = buffer.getvalue()
                
                page_text, _ = ocr_image(image_data, ocr_engine)
                if page_text:
                    text_parts.append(f"--- Page {i + 1} ---\n{page_text}")
            
            return normalize_text("\n".join(text_parts)), "pdf_ocr"
        except Exception as e:
            return "", f"pdf_ocr_failed: {e}"
    
    return "", "no_pdf_extraction_method"


def is_wechat_url(url: str) -> bool:
    """Check if a URL is a WeChat Official Account article."""
    return "mp.weixin.qq.com" in url


async def extract_wechat_article(url: str) -> dict[str, Any]:
    """
    Extract WeChat article with lightweight-first strategy:
      1. Try urllib + BeautifulSoup (fast, no browser, no Dock icon)
      2. Fallback to Camoufox browser only if step 1 fails
    """
    result: dict[str, Any] = {
        "url": url,
        "text": "",
        "method": "",
        "success": False,
        "error": "",
        "attempts": [],
        "wechat_metadata": {},
    }

    # ---- Step 1: Lightweight extraction (urllib + BS4, no browser) ----
    if HAS_BS4:
        try:
            print("\n🌐 尝试轻量级提取微信文章（无需启动浏览器）...")
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            })
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            soup = BeautifulSoup(html, "html.parser")
            content_div = soup.find("div", id="js_content")
            title_el = soup.find("h1", id="activity-name") or soup.find("h1")

            if content_div and title_el:
                title = title_el.get_text(strip=True)
                body_text = content_div.get_text("\n", strip=True)

                if len(body_text) >= 100:
                    # Use wechat_article_to_markdown for better Markdown formatting
                    if HAS_WECHAT_TOOL:
                        try:
                            meta = extract_metadata(soup, html)
                            meta["source_url"] = url
                            result["wechat_metadata"] = meta
                            content_html, code_blocks, img_urls = process_content(soup)
                            if content_html:
                                md = convert_to_markdown(content_html, code_blocks)
                                full_md = build_markdown(meta, md)
                                result["text"] = full_md
                                result["method"] = "wechat_lightweight_md"
                                result["success"] = True
                                result["attempts"].append({"method": "lightweight_md", "status": "success"})
                                print(f"✅ 轻量级提取成功（Markdown），约 {len(full_md)} 字符")
                                return result
                        except Exception:
                            pass

                    # Plain text fallback
                    full_text = f"# {title}\n\n{body_text}"
                    result["text"] = full_text
                    result["method"] = "wechat_lightweight"
                    result["success"] = True
                    result["attempts"].append({"method": "lightweight", "status": "success"})
                    print(f"✅ 轻量级提取成功（纯文本），约 {len(full_text)} 字符")
                    return result

            result["attempts"].append({"method": "lightweight", "status": "content_insufficient"})
            print("⚠️ 轻量级提取内容不足，尝试浏览器方式...")

        except Exception as e:
            result["attempts"].append({"method": "lightweight", "status": f"error: {e}"})
            print(f"⚠️ 轻量级提取失败: {e}，尝试浏览器方式...")

    # ---- Step 2: Camoufox browser fallback ----
    if not HAS_WECHAT_TOOL:
        result["error"] = "wechat_tool_not_installed"
        result["attempts"].append({"method": "wechat_tool", "status": "not_installed"})
        return result

    try:
        print("\n🦊 使用 Camoufox 浏览器抓取微信文章...")

        async with AsyncCamoufox(headless=True) as browser:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded")
            try:
                await page.wait_for_selector("#js_content", timeout=15000)
            except Exception:
                pass
            await asyncio.sleep(2)
            html = await page.content()

        soup = BeautifulSoup(html, "html.parser")
        meta = extract_metadata(soup, html)
        if not meta.get("title"):
            result["error"] = "wechat_no_title_extracted"
            result["attempts"].append({"method": "wechat_tool", "status": "no_title"})
            return result

        meta["source_url"] = url
        result["wechat_metadata"] = meta

        print(f"📄 标题: {meta['title']}")
        print(f"👤 公众号: {meta.get('author', '未知')}")
        print(f"📅 时间: {meta.get('publish_time', '未知')}")

        content_html, code_blocks, img_urls = process_content(soup)
        if not content_html:
            result["error"] = "wechat_no_content"
            result["attempts"].append({"method": "wechat_tool", "status": "no_content"})
            return result

        md = convert_to_markdown(content_html, code_blocks)
        full_md = build_markdown(meta, md)

        result["text"] = full_md
        result["method"] = "wechat_camoufox"
        result["success"] = True
        result["attempts"].append({"method": "wechat_tool", "status": "success"})

        print(f"✅ 微信文章提取成功（浏览器），Markdown 约 {len(full_md)} 字符")
        return result

    except Exception as e:
        result["error"] = f"wechat_extraction_failed: {e}"
        result["attempts"].append({"method": "wechat_tool", "status": f"error: {e}"})
        print(f"⚠️ 微信文章提取失败: {e}，将 fallback 到通用提取")
        return result


async def extract_from_url(
    url: str,
    timeout: int = 30,
    force_browser: bool = False,
    force_ocr: bool = False,
    ocr_engine: str = "auto",
) -> dict[str, Any]:
    """
    Extract content from URL with multiple fallback strategies.
    
    Returns dict with: text, method, success, error
    """
    result = {
        "url": url,
        "text": "",
        "method": "",
        "success": False,
        "error": "",
        "attempts": [],
    }
    
    # Strategy 0: WeChat article — use dedicated extractor
    if is_wechat_url(url):
        wechat_result = await extract_wechat_article(url)
        if wechat_result["success"]:
            return wechat_result
        # WeChat extraction failed, fallback to generic strategies
        result["attempts"].extend(wechat_result.get("attempts", []))
        print("\n🔄 Fallback 到通用提取策略...")
    
    # Strategy 1: Standard HTTP fetch
    if not force_browser:
        html, method = try_standard_fetch(url, timeout)
        result["attempts"].append({"method": "standard_fetch", "status": method})
        
        if html:
            text = extract_main_content(html)
            if len(text) >= MIN_CONTENT_LENGTH and not force_ocr:
                result["text"] = text
                result["method"] = "standard_fetch"
                result["success"] = True
                return result
    
    # Strategy 2: Playwright browser
    if HAS_PLAYWRIGHT:
        text, screenshot, method = await fetch_with_playwright(url, timeout)
        result["attempts"].append({"method": "playwright", "status": method})
        
        if text and len(text) >= MIN_CONTENT_LENGTH and not force_ocr:
            result["text"] = text
            result["method"] = "playwright"
            result["success"] = True
            return result
        
        # Strategy 3: OCR from screenshot
        if screenshot and (force_ocr or len(text) < MIN_CONTENT_LENGTH):
            ocr_text, ocr_method = ocr_image(screenshot, ocr_engine)
            result["attempts"].append({"method": "screenshot_ocr", "status": ocr_method})
            
            if ocr_text and len(ocr_text) >= MIN_CONTENT_LENGTH:
                result["text"] = ocr_text
                result["method"] = "screenshot_ocr"
                result["success"] = True
                return result
    
    # If we have some text but it's short, use it anyway
    if result.get("text") or text:
        result["text"] = result.get("text") or text
        result["method"] = result["method"] or "partial"
        result["success"] = len(result["text"]) > 50
        if not result["success"]:
            result["error"] = "content_too_short"
    else:
        result["error"] = "all_extraction_methods_failed"
    
    return result


def extract_content(
    url: str | None = None,
    image_path: str | None = None,
    pdf_path: str | None = None,
    timeout: int = 30,
    force_browser: bool = False,
    force_ocr: bool = False,
    ocr_engine: str = "auto",
) -> dict[str, Any]:
    """
    Main entry point for content extraction.
    
    Supports URL, image file, or PDF file.
    Returns dict with: text, method, success, error, source_type
    """
    if url:
        result = asyncio.run(
            extract_from_url(url, timeout, force_browser, force_ocr, ocr_engine)
        )
        result["source_type"] = "url"
        return result
    
    if image_path:
        text, method = extract_from_image(image_path, ocr_engine)
        return {
            "source_type": "image",
            "source_path": image_path,
            "text": text,
            "method": method,
            "success": len(text) >= 50,
            "error": "" if len(text) >= 50 else "extraction_failed",
        }
    
    if pdf_path:
        text, method = extract_from_pdf(pdf_path, ocr_engine)
        return {
            "source_type": "pdf",
            "source_path": pdf_path,
            "text": text,
            "method": method,
            "success": len(text) >= 50,
            "error": "" if len(text) >= 50 else "extraction_failed",
        }
    
    return {
        "source_type": "none",
        "text": "",
        "method": "",
        "success": False,
        "error": "no_input_provided",
    }


def main() -> None:
    args = parse_args()
    
    result = extract_content(
        url=args.url,
        image_path=args.image,
        pdf_path=args.pdf,
        timeout=args.timeout,
        force_browser=args.force_browser,
        force_ocr=args.force_ocr,
        ocr_engine=args.ocr_engine,
    )
    
    if args.output:
        Path(args.output).write_text(result["text"], encoding="utf-8")
        print(f"Wrote extracted text: {args.output}")
        print(f"Method: {result['method']}")
        print(f"Success: {result['success']}")
        print(f"Length: {len(result['text'])} characters")
    
    if args.output_json:
        # Remove large binary data before JSON output
        output_result = {k: v for k, v in result.items() if k != "screenshot"}
        Path(args.output_json).write_text(
            json.dumps(output_result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote extraction metadata: {args.output_json}")
    
    if not args.output and not args.output_json:
        print(result["text"])
        print(f"\n--- Extraction Info ---")
        print(f"Method: {result['method']}")
        print(f"Success: {result['success']}")
        if result.get("error"):
            print(f"Error: {result['error']}")


if __name__ == "__main__":
    main()
