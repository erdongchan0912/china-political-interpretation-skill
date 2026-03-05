#!/usr/bin/env python3
"""FastAPI backend server for China Political Interpretation Web UI.

This server provides:
- File upload API (URL, images, PDFs)
- Analysis task management
- Server-Sent Events for real-time progress
- Static file serving for generated reports
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import uvicorn
from fastapi import (
    FastAPI,
    HTTPException,
    UploadFile,
    File,
    Form,
    BackgroundTasks,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Add backend directories to path
BACKEND_DIR = Path(__file__).parent.parent  # backend/
CORE_DIR = BACKEND_DIR / "core"
REPORTS_DIR = BACKEND_DIR / "reports"
PROJECT_ROOT = BACKEND_DIR.parent  # china-political-interpretation/

sys.path.insert(0, str(CORE_DIR))
sys.path.insert(0, str(REPORTS_DIR))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# App configuration
def _resolve_runtime_dir(env_key: str, default_leaf: str) -> Path:
    value = os.environ.get(env_key, "").strip()
    if value:
        return Path(value).expanduser().resolve()
    return (Path(tempfile.gettempdir()) / "china-political-interpretation" / default_leaf).resolve()


UPLOAD_DIR = _resolve_runtime_dir("UPLOAD_DIR", "uploads")
OUTPUT_DIR = _resolve_runtime_dir("OUTPUT_DIR", "outputs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Task storage – SQLite backed, survives restarts
from api.task_store import TaskStore

_task_store = TaskStore(OUTPUT_DIR / "tasks.db")

# Compatibility shim so that test code doing ``tasks.clear()`` still works.
class _TasksProxy:
    """Dict-like proxy over TaskStore for backward compatibility."""
    def __getitem__(self, task_id: str) -> dict[str, Any]:
        t = _task_store.get(task_id)
        if t is None:
            raise KeyError(task_id)
        return t
    def __contains__(self, task_id: str) -> bool:
        return _task_store.contains(task_id)
    def __delitem__(self, task_id: str) -> None:
        _task_store.delete(task_id)
    def values(self):
        return _task_store.list_all()
    def clear(self) -> None:
        for t in _task_store.list_all():
            _task_store.delete(t["task_id"])

tasks = _TasksProxy()

# Upload constraints
ALLOWED_FILE_TYPES: dict[str, str] = {
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
    ".txt": "text",
    ".md": "text",
}
FILENAME_SAFE_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
FILE_CHUNK_SIZE = 1024 * 1024
MAX_FILE_SIZE_BYTES = int(os.environ.get("MAX_FILE_SIZE_BYTES", 10 * 1024 * 1024))
MAX_TOTAL_UPLOAD_BYTES = int(os.environ.get("MAX_TOTAL_UPLOAD_BYTES", 30 * 1024 * 1024))
MAX_TEXT_CONTENT_BYTES = int(os.environ.get("MAX_TEXT_CONTENT_BYTES", 5 * 1024 * 1024))
MAX_URLS_PER_TASK = int(os.environ.get("MAX_URLS_PER_TASK", 50))
MAX_TEXT_ITEMS_PER_TASK = int(os.environ.get("MAX_TEXT_ITEMS_PER_TASK", 20))

# Create FastAPI app
app = FastAPI(
    title="China Political Interpretation API",
    description="API for analyzing Chinese political documents and news",
    version="1.0.0",
)

# CORS middleware — restrict to known local origins
_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
_cors_env = os.environ.get("CORS_ORIGINS", "").strip()
CORS_ORIGINS = _cors_env.split(",") if _cors_env else _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static directories
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")


# Pydantic models
class AnalysisRequest(BaseModel):
    task_id: str
    urls: list[str] = Field(default_factory=list)
    topic: str | None = None
    user_focus: str | None = None
    force_browser: bool = False
    force_ocr: bool = False


class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: int
    current_stage: str
    message: str
    created_at: str
    updated_at: str
    result: dict | None = None
    error: dict | None = None


class UploadResponse(BaseModel):
    task_id: str
    files: list[dict[str, str]]
    message: str


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: Any | None = None


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        detail: Any | None = None,
    ):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.detail = detail
        super().__init__(message)


def api_error(
    status_code: int,
    error_code: str,
    message: str,
    detail: Any | None = None,
) -> None:
    raise ApiError(status_code, error_code, message, detail)


def _sanitize_filename(filename: str) -> str:
    if not filename:
        api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_FILENAME",
            "文件名不能为空",
        )

    if "/" in filename or "\\" in filename:
        api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_FILENAME",
            "文件名包含非法路径分隔符",
            {"filename": filename},
        )

    if ".." in PurePosixPath(filename).parts or ".." in PureWindowsPath(filename).parts:
        api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_FILENAME",
            "文件名包含非法路径片段",
            {"filename": filename},
        )

    name_only = Path(filename).name
    clean = FILENAME_SAFE_PATTERN.sub("_", name_only).strip("._")
    if not clean:
        api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_FILENAME",
            "文件名不合法",
            {"filename": filename},
        )
    return clean[:180]


def _resolve_unique_path(directory: Path, filename: str) -> Path:
    base = Path(filename).stem
    ext = Path(filename).suffix
    candidate = directory / filename
    index = 1
    while candidate.exists():
        candidate = directory / f"{base}_{index}{ext}"
        index += 1
    return candidate


def _is_valid_file_signature(ext: str, sample: bytes) -> bool:
    if ext == ".pdf":
        return sample.startswith(b"%PDF-")
    if ext == ".png":
        return sample.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in {".jpg", ".jpeg"}:
        return sample.startswith(b"\xff\xd8\xff")
    if ext == ".gif":
        return sample.startswith(b"GIF87a") or sample.startswith(b"GIF89a")
    if ext == ".webp":
        return len(sample) >= 12 and sample.startswith(b"RIFF") and sample[8:12] == b"WEBP"
    if ext in {".txt", ".md"}:
        return True
    return False


@app.exception_handler(ApiError)
async def handle_api_error(_, exc: ApiError):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            detail=exc.detail,
        ).model_dump(),
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(_, exc: HTTPException):
    detail = exc.detail
    message = detail if isinstance(detail, str) else "请求失败"
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error_code="HTTP_ERROR",
            message=message,
            detail=detail if not isinstance(detail, str) else None,
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error_code="VALIDATION_ERROR",
            message="请求参数校验失败",
            detail=exc.errors(),
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(_, exc: Exception):
    logger.exception("Unhandled server error")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error_code="INTERNAL_SERVER_ERROR",
            message="服务器内部错误",
            detail=str(exc),
        ).model_dump(),
    )


# Progress stages
STAGES = [
    {"name": "识别文本", "progress": 10},
    {"name": "🤖 LLM 理解材料", "progress": 20},
    {"name": "🤖 LLM 生成检索策略", "progress": 30},
    {"name": "搜索横向材料", "progress": 45},
    {"name": "搜索纵向材料", "progress": 55},
    {"name": "🤖 LLM 深度分析", "progress": 70},
    {"name": "🤖 LLM 生成 HTML 报告", "progress": 85},
    {"name": "🤖 LLM 生成 PDF 报告", "progress": 95},
    {"name": "完成", "progress": 100},
]


def create_task(task_id: str | None = None) -> str:
    """Create a new analysis task."""
    if not task_id:
        task_id = str(uuid.uuid4())[:8]

    _task_store.create(task_id)

    # Create task directories
    task_upload_dir = UPLOAD_DIR / task_id
    task_output_dir = OUTPUT_DIR / task_id
    task_upload_dir.mkdir(parents=True, exist_ok=True)
    task_output_dir.mkdir(parents=True, exist_ok=True)

    return task_id


def update_task(task_id: str, **kwargs) -> None:
    """Update task status."""
    if not _task_store.contains(task_id):
        return
    _task_store.update(task_id, **kwargs)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "China Political Interpretation API",
        "version": "1.0.0",
        "status": "running",
    }


@app.post("/api/tasks", response_model=dict)
async def create_new_task():
    """Create a new analysis task."""
    task_id = create_task()
    return {"task_id": task_id, "message": "Task created successfully"}


@app.post("/api/upload/{task_id}")
async def upload_files(
    task_id: str,
    files: list[UploadFile] = File(default=[]),
    urls: str = Form(default=""),
    text_contents: str = Form(default=""),  # 新增: 支持粘贴文本
):
    """Upload files for analysis."""
    if task_id not in tasks:
        task_id = create_task(task_id)
    
    task_upload_dir = UPLOAD_DIR / task_id
    task_upload_dir.mkdir(parents=True, exist_ok=True)
    
    uploaded_files = []
    total_upload_bytes = 0
    
    # Handle file uploads
    for file in files:
        if not file.filename:
            continue

        clean_name = _sanitize_filename(file.filename)
        ext = Path(clean_name).suffix.lower()
        if ext not in ALLOWED_FILE_TYPES:
            api_error(
                status.HTTP_400_BAD_REQUEST,
                "UNSUPPORTED_FILE_TYPE",
                "不支持的文件类型",
                {"filename": clean_name, "allowed_types": sorted(ALLOWED_FILE_TYPES.keys())},
            )

        file_type = ALLOWED_FILE_TYPES[ext]
        file_path = _resolve_unique_path(task_upload_dir, clean_name)

        written_size = 0
        signature_checked = False
        try:
            with file_path.open("wb") as out:
                while True:
                    chunk = await file.read(FILE_CHUNK_SIZE)
                    if not chunk:
                        break
                    if not signature_checked:
                        signature_checked = True
                        if not _is_valid_file_signature(ext, chunk[:32]):
                            out.close()
                            file_path.unlink(missing_ok=True)
                            api_error(
                                status.HTTP_400_BAD_REQUEST,
                                "FILE_SIGNATURE_MISMATCH",
                                "文件扩展名与内容不匹配",
                                {"filename": clean_name},
                            )
                    written_size += len(chunk)
                    total_upload_bytes += len(chunk)

                    if written_size > MAX_FILE_SIZE_BYTES:
                        out.close()
                        file_path.unlink(missing_ok=True)
                        api_error(
                            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            "FILE_TOO_LARGE",
                            "单文件大小超出限制",
                            {"filename": clean_name, "max_file_size_bytes": MAX_FILE_SIZE_BYTES},
                        )

                    if total_upload_bytes > MAX_TOTAL_UPLOAD_BYTES:
                        out.close()
                        file_path.unlink(missing_ok=True)
                        api_error(
                            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            "TOTAL_UPLOAD_TOO_LARGE",
                            "上传总大小超出限制",
                            {"max_total_upload_bytes": MAX_TOTAL_UPLOAD_BYTES},
                        )

                    out.write(chunk)

            if written_size == 0:
                file_path.unlink(missing_ok=True)
                api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "EMPTY_FILE",
                    "不允许上传空文件",
                    {"filename": clean_name},
                )
        finally:
            await file.close()

        uploaded_files.append({
            "filename": clean_name,
            "type": file_type,
            "path": str(file_path),
            "size": written_size,
        })
    
    # Handle URLs
    url_list = []
    if urls:
        url_list = [u.strip() for u in urls.split("\n") if u.strip()]
        if len(url_list) > MAX_URLS_PER_TASK:
            api_error(
                status.HTTP_400_BAD_REQUEST,
                "TOO_MANY_URLS",
                "URL 数量超出限制",
                {"max_urls_per_task": MAX_URLS_PER_TASK},
            )

        invalid_urls = [u for u in url_list if not (u.startswith("http://") or u.startswith("https://"))]
        if invalid_urls:
            api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_URL",
                "存在不合法 URL",
                {"invalid_urls": invalid_urls[:10]},
            )

        for url in url_list:
            uploaded_files.append({
                "filename": url,
                "type": "url",
                "path": url,
                "size": 0,
            })
    
    # Handle pasted text contents (new)
    if text_contents:
        text_payload = text_contents.lstrip()
        if text_payload.startswith("[") or text_payload.startswith("{"):
            try:
                parsed = json.loads(text_contents)
            except json.JSONDecodeError as exc:
                api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "INVALID_TEXT_CONTENTS",
                    "text_contents JSON 格式非法",
                    {"error": str(exc)},
                )

            if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
                api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "INVALID_TEXT_CONTENTS",
                    "text_contents 必须是字符串数组",
                )
            text_list = parsed
        else:
            text_list = [text_contents]

        if len(text_list) > MAX_TEXT_ITEMS_PER_TASK:
            api_error(
                status.HTTP_400_BAD_REQUEST,
                "TOO_MANY_TEXT_ITEMS",
                "文本条目数量超出限制",
                {"max_text_items_per_task": MAX_TEXT_ITEMS_PER_TASK},
            )

        for i, text_content in enumerate(text_list):
            if not text_content.strip():
                continue

            text_bytes = len(text_content.encode("utf-8"))
            total_upload_bytes += text_bytes
            if text_bytes > MAX_TEXT_CONTENT_BYTES:
                api_error(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    "TEXT_CONTENT_TOO_LARGE",
                    "单条文本输入过大",
                    {"max_text_content_bytes": MAX_TEXT_CONTENT_BYTES},
                )
            if total_upload_bytes > MAX_TOTAL_UPLOAD_BYTES:
                api_error(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    "TOTAL_UPLOAD_TOO_LARGE",
                    "上传总大小超出限制",
                    {"max_total_upload_bytes": MAX_TOTAL_UPLOAD_BYTES},
                )

            # Save text to file
            text_filename = f"pasted_text_{i+1}.txt"
            text_path = task_upload_dir / text_filename
            text_path.write_text(text_content, encoding="utf-8")
            
            # Generate summary for display
            summary = text_content[:50].replace('\n', ' ') + '...' if len(text_content) > 50 else text_content
            
            uploaded_files.append({
                "filename": summary,
                "type": "text",
                "path": str(text_path),
                "size": text_bytes,
            })
    
    # Update task
    _task_store.append_files(task_id, uploaded_files)
    _task_store.append_urls(task_id, url_list)
    
    return {
        "task_id": task_id,
        "files": uploaded_files,
        "message": f"Uploaded {len(uploaded_files)} file(s)",
    }


@app.get("/api/tasks/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """Get task status."""
    task = _task_store.get(task_id)
    if task is None:
        api_error(status.HTTP_404_NOT_FOUND, "TASK_NOT_FOUND", "任务不存在", {"task_id": task_id})
    return TaskStatus(
        task_id=task["task_id"],
        status=task["status"],
        progress=task["progress"],
        current_stage=task["current_stage"],
        message=task.get("message", ""),
        created_at=task["created_at"],
        updated_at=task["updated_at"],
        result=task.get("result"),
        error=task.get("error"),
    )


@app.post("/api/analyze/{task_id}")
async def start_analysis(
    task_id: str,
    background_tasks: BackgroundTasks,
    request: AnalysisRequest | None = None,
):
    """Start analysis for a task."""
    task = _task_store.get(task_id)
    if task is None:
        api_error(status.HTTP_404_NOT_FOUND, "TASK_NOT_FOUND", "任务不存在", {"task_id": task_id})
    if task["status"] == "running":
        api_error(status.HTTP_400_BAD_REQUEST, "TASK_ALREADY_RUNNING", "任务正在运行")
    
    if not task["files"] and not task["urls"]:
        api_error(status.HTTP_400_BAD_REQUEST, "EMPTY_TASK", "没有可分析的文件或 URL")
    
    # Add any additional URLs from request
    if request and request.urls:
        for url in request.urls:
            if not (url.startswith("http://") or url.startswith("https://")):
                api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "INVALID_URL",
                    "存在不合法 URL",
                    {"invalid_url": url},
                )
            if url not in task["urls"]:
                task["urls"].append(url)
                task["files"].append({
                    "filename": url,
                    "type": "url",
                    "path": url,
                    "size": 0,
                })
    
    # Update task options
    if request:
        task["topic"] = request.topic
        task["user_focus"] = request.user_focus
        task["force_browser"] = request.force_browser
        task["force_ocr"] = request.force_ocr
    
    # Start background analysis
    background_tasks.add_task(run_analysis, task_id)
    
    update_task(task_id, status="running", progress=0, current_stage="准备中", error=None)
    
    return {"task_id": task_id, "message": "Analysis started"}


async def run_analysis(task_id: str):
    """Run the analysis pipeline."""
    from api.services.task_runner import TaskRunner
    
    runner = TaskRunner(task_id, _task_store.get(task_id) or {}, OUTPUT_DIR / task_id)
    
    try:
        await runner.run(
            on_progress=lambda stage, progress, message: update_task(
                task_id,
                current_stage=stage,
                progress=progress,
                message=message,
            )
        )
        
        update_task(
            task_id,
            status="completed",
            progress=100,
            current_stage="完成",
            result=runner.get_result(),
        )
    except Exception as e:
        logger.exception(f"Analysis failed for task {task_id}")
        error_payload = {
            "error_code": "ANALYSIS_FAILED",
            "message": "分析执行失败",
            "detail": str(e),
        }
        update_task(
            task_id,
            status="failed",
            message=error_payload["message"],
            current_stage="失败",
            error=error_payload,
            result=runner.get_result(),
        )


@app.get("/api/progress/{task_id}")
async def get_progress_stream(task_id: str):
    """Server-Sent Events stream for task progress."""
    if not _task_store.contains(task_id):
        api_error(status.HTTP_404_NOT_FOUND, "TASK_NOT_FOUND", "任务不存在", {"task_id": task_id})
    
    async def event_generator():
        last_progress = -1
        last_stage = ""
        
        while True:
            task = _task_store.get(task_id)
            if not task:
                payload = {
                    "error_code": "TASK_NOT_FOUND",
                    "message": "任务不存在",
                    "detail": {"task_id": task_id},
                }
                yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                break
            
            # Send update if changed
            if task["progress"] != last_progress or task["current_stage"] != last_stage:
                last_progress = task["progress"]
                last_stage = task["current_stage"]
                
                data = {
                    "task_id": task_id,
                    "status": task["status"],
                    "progress": task["progress"],
                    "current_stage": task["current_stage"],
                    "message": task.get("message", ""),
                }
                yield f"event: progress\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            
            # Check if completed or failed
            if task["status"] in ("completed", "failed"):
                result_data = {
                    "task_id": task_id,
                    "status": task["status"],
                    "result": task.get("result"),
                    "error": task.get("error"),
                }
                yield f"event: {task['status']}\ndata: {json.dumps(result_data, ensure_ascii=False)}\n\n"
                break
            
            await asyncio.sleep(0.5)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/result/{task_id}")
async def get_result(task_id: str):
    """Get analysis result."""
    task = _task_store.get(task_id)
    if task is None:
        api_error(status.HTTP_404_NOT_FOUND, "TASK_NOT_FOUND", "任务不存在", {"task_id": task_id})
    if task["status"] != "completed":
        api_error(
            status.HTTP_400_BAD_REQUEST,
            "TASK_NOT_COMPLETED",
            "任务尚未完成",
            {"current_status": task["status"]},
        )
    
    return task.get("result", {})


@app.get("/api/download/{task_id}/{filename}")
async def download_file(task_id: str, filename: str):
    """Download generated file."""
    if filename != Path(filename).name:
        api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_FILENAME",
            "下载文件名不合法",
            {"filename": filename},
        )

    file_path = (OUTPUT_DIR / task_id / filename).resolve()
    task_dir = (OUTPUT_DIR / task_id).resolve()
    try:
        file_path.relative_to(task_dir)
    except ValueError:
        api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_FILENAME",
            "下载文件名不合法",
            {"filename": filename},
        )
    
    if not file_path.exists():
        api_error(
            status.HTTP_404_NOT_FOUND,
            "FILE_NOT_FOUND",
            "文件不存在",
            {"filename": filename},
        )
    
    # 用分析标题作为下载文件名（而非通用的 policy-brief）
    download_name = filename
    try:
        task = _task_store.get(task_id)
        if task:
            result = task.get("result")
            if isinstance(result, dict):
                summary = result.get("summary") or {}
                title = summary.get("title", "")
                if title:
                    import re
                    safe_title = re.sub(r'[/\\?%*:|"<>]', '_', title)[:80]
                    ext = Path(filename).suffix  # .html or .pdf
                    download_name = f"{safe_title}{ext}"
    except Exception:
        pass  # fallback to original filename
    
    return FileResponse(
        path=str(file_path),
        filename=download_name,
        media_type="application/octet-stream",
    )


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete a task and its files."""
    if not _task_store.contains(task_id):
        api_error(status.HTTP_404_NOT_FOUND, "TASK_NOT_FOUND", "任务不存在", {"task_id": task_id})
    
    # Clean up directories
    task_upload_dir = UPLOAD_DIR / task_id
    task_output_dir = OUTPUT_DIR / task_id
    
    if task_upload_dir.exists():
        shutil.rmtree(task_upload_dir)
    if task_output_dir.exists():
        shutil.rmtree(task_output_dir)
    
    _task_store.delete(task_id)
    
    return {"message": "Task deleted successfully"}


@app.get("/api/tasks")
async def list_tasks():
    """List all tasks."""
    items = []
    for t in _task_store.list_all():
        # Try to extract title from result
        title = ""
        result = t.get("result")
        if isinstance(result, dict):
            summary = result.get("summary") or {}
            title = summary.get("title", "")
        items.append({
            "task_id": t["task_id"],
            "status": t["status"],
            "progress": t["progress"],
            "created_at": t["created_at"],
            "title": title,
        })
    return {"tasks": items}


def main():
    """Run the server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run the analysis server")
    parser.add_argument("--host", default=os.environ.get("SERVER_HOST", "127.0.0.1"), help="Host to bind to")
    parser.add_argument("--port", type=int, default=int(os.environ.get("SERVER_PORT", 8000)), help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"China Political Interpretation API Server")
    print(f"{'='*60}")
    print(f"Server running at: http://{args.host}:{args.port}")
    print(f"API docs at: http://{args.host}:{args.port}/docs")
    print(f"Upload directory: {UPLOAD_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Task database:    {OUTPUT_DIR / 'tasks.db'}")
    print(f"{'='*60}\n")
    
    uvicorn.run(
        "api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
