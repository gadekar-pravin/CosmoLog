from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, field_validator
from sse_starlette.sse import EventSourceResponse

from agent_prompt import SYSTEM_PROMPT
from logging_config import (
    CorrelationFilter,
    SSELogHandler,
    _truncate,
    configure_logging,
    get_correlation_id,
    set_correlation_id,
)
from mcp_server import fetch_space_data, manage_space_journal, show_space_dashboard

configure_logging()
logger = logging.getLogger(__name__)

load_dotenv()

TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "fetch_space_data": fetch_space_data,
    "manage_space_journal": manage_space_journal,
    "show_space_dashboard": show_space_dashboard,
}

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
MAX_ITERATIONS = 10

_gemini_client: genai.Client | None = None

app = FastAPI(title="CosmoLog AI Agent")
app.mount("/static", StaticFiles(directory="static"), name="static")

conversation_history: list[types.Content] = []

_last_fetch_result: dict[str, Any] | None = None


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    cid = uuid.uuid4().hex[:8]
    set_correlation_id(cid)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    return response


class ChatRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    message: str

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value


def _object_schema(
    properties: dict[str, types.Schema],
    required: list[str] | None = None,
) -> types.Schema:
    return types.Schema(
        type=types.Type.OBJECT,
        properties=properties,
        required=required,
    )


FUNCTION_DECLARATIONS: list[types.FunctionDeclaration] = [
    types.FunctionDeclaration(
        name="fetch_space_data",
        description="Fetch live NASA space data: APOD, NASA images, and near-Earth objects.",
        parameters=_object_schema(
            {
                "date": types.Schema(
                    type=types.Type.STRING,
                    description="Date for APOD lookup (YYYY-MM-DD). Defaults to today.",
                ),
                "image_query": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "Search query for NASA images."
                        " If omitted, a random visually compelling query is used."
                    ),
                ),
                "image_count": types.Schema(
                    type=types.Type.INTEGER,
                    description="Number of images to return. Defaults to 3.",
                ),
                "neo_days": types.Schema(
                    type=types.Type.INTEGER,
                    description="Number of days ahead to check for NEOs. Defaults to 7.",
                ),
                "neo_count": types.Schema(
                    type=types.Type.INTEGER,
                    description="Maximum number of NEOs to return. Defaults to 10.",
                ),
            }
        ),
    ),
    types.FunctionDeclaration(
        name="manage_space_journal",
        description=(
            "Manage the local space journal with create, read, update, and delete operations."
        ),
        parameters=_object_schema(
            {
                "operation": types.Schema(
                    type=types.Type.STRING,
                    enum=["create", "read", "update", "delete"],
                    description="One of create, read, update, or delete.",
                ),
                "entry_id": types.Schema(
                    type=types.Type.STRING,
                    description="Required for update and delete operations.",
                ),
                "payload": types.Schema(
                    type=types.Type.OBJECT,
                    description="Required for create and update. Entry data dictionary.",
                    properties={
                        "type": types.Schema(
                            type=types.Type.STRING,
                            description=(
                                "Entry type, required for create"
                                " (e.g. 'observation', 'apod', 'rover_photo')."
                            ),
                        ),
                        "date": types.Schema(
                            type=types.Type.STRING,
                            description="Entry date in YYYY-MM-DD format, required for create.",
                        ),
                        "title": types.Schema(
                            type=types.Type.STRING,
                            description="Title of the journal entry.",
                        ),
                        "tags": types.Schema(
                            type=types.Type.ARRAY,
                            items=types.Schema(type=types.Type.STRING),
                            description="Tags for categorizing the entry.",
                        ),
                        "notes": types.Schema(
                            type=types.Type.STRING,
                            description="Free-text notes for the entry.",
                        ),
                        "source_url": types.Schema(
                            type=types.Type.STRING,
                            description="URL of the source data (e.g. APOD image URL).",
                        ),
                    },
                    required=["type", "date"],
                ),
                "tag_filter": types.Schema(
                    type=types.Type.STRING,
                    description="Optional tag to filter entries during read.",
                ),
            },
            required=["operation"],
        ),
    ),
    types.FunctionDeclaration(
        name="show_space_dashboard",
        description="Display the CosmoLog dashboard with NASA data and journal entries.",
        parameters=_object_schema(
            {
                "space_data": types.Schema(
                    type=types.Type.OBJECT,
                    description="Data returned from fetch_space_data.",
                ),
                "journal_entries": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.OBJECT),
                    description="Entries returned from manage_space_journal read operation.",
                ),
                "tag_filter": types.Schema(
                    type=types.Type.STRING,
                    description="Active tag filter for journal entries.",
                ),
            }
        ),
    ),
]

GEMINI_TOOL = types.Tool(function_declarations=FUNCTION_DECLARATIONS)


def _get_gemini_client() -> genai.Client:
    global _gemini_client

    if _gemini_client is not None:
        return _gemini_client

    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    if not project:
        raise RuntimeError("Missing GOOGLE_CLOUD_PROJECT, required for Vertex AI Gemini access.")

    _gemini_client = genai.Client(vertexai=True, project=project, location=location)
    logger.info("gemini_client_init project=%s location=%s", project, location)
    return _gemini_client


def _coerce_tool_args(name: str, args: dict[str, Any]) -> dict[str, Any]:
    coerced = dict(args)
    if name == "fetch_space_data":
        for key in ("image_count", "neo_days", "neo_count"):
            value = coerced.get(key)
            if isinstance(value, float) and value.is_integer():
                coerced[key] = int(value)
    return coerced


def _serialize_result(result: Any) -> Any:
    if isinstance(result, BaseModel):
        return result.model_dump()
    return result


def _function_response_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    return {"result": result}


def _extract_response_parts(response: Any) -> list[Any]:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return []

    content = getattr(candidates[0], "content", None)
    return list(getattr(content, "parts", None) or [])


def _part_text(part: Any) -> str | None:
    text = getattr(part, "text", None)
    return text if text else None


def _part_function_call(part: Any) -> Any | None:
    function_call = getattr(part, "function_call", None)
    return function_call if function_call else None


def _is_journal_read_request(message: str) -> bool:
    normalized = " ".join(message.lower().strip().split()).rstrip(".?!")
    if "journal" not in normalized:
        return False

    mutating_or_fetching_terms = (
        "add",
        "apod",
        "asteroid",
        "create",
        "delete",
        "fetch",
        "nasa",
        "neo",
        "remove",
        "rover",
        "save",
        "update",
    )
    if any(term in normalized for term in mutating_or_fetching_terms):
        return False

    return any(
        phrase in normalized
        for phrase in (
            "display",
            "read",
            "show",
            "what is in",
            "what's in",
        )
    )


def _dispatch_tool(name: str, args: dict[str, Any]) -> tuple[Any, str | None]:
    global _last_fetch_result
    tool = TOOL_REGISTRY.get(name)
    if tool is None:
        logger.warning("unknown_tool name=%s", name)
        return {"status": "error", "message": f"Unknown tool: {name}"}, None

    coerced_args = _coerce_tool_args(name, args)

    if name == "show_space_dashboard" and _last_fetch_result is not None:
        logger.info("cache_inject replacing space_data with cached fetch result")
        coerced_args["space_data"] = _last_fetch_result

    logger.info("tool_dispatch name=%s args=%s", name, _truncate(coerced_args))
    t0 = time.perf_counter()
    try:
        result = tool(**coerced_args)

        if name == "fetch_space_data":
            _last_fetch_result = _serialize_result(result)

        duration_ms = (time.perf_counter() - t0) * 1000
        if name == "show_space_dashboard":
            html = result.html()
            logger.info(
                "tool_success name=%s duration_ms=%.1f html_len=%d",
                name,
                duration_ms,
                len(html),
            )
            return "Dashboard rendered successfully", html
        logger.info(
            "tool_success name=%s duration_ms=%.1f result_type=%s",
            name,
            duration_ms,
            type(result).__name__,
        )
        logger.debug("tool_result_detail name=%s result=%s", name, _truncate(result))
        return _serialize_result(result), None
    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.error("tool_error name=%s duration_ms=%.1f", name, duration_ms, exc_info=True)
        return {"status": "error", "message": str(exc)}, None


async def _journal_read_shortcut() -> AsyncGenerator[dict[str, Any], None]:
    yield {
        "type": "thinking",
        "data": {"text": "I'll read your space journal and render the dashboard."},
    }

    read_args = {"operation": "read"}
    yield {"type": "tool_call", "data": {"name": "manage_space_journal", "args": read_args}}
    journal_result, _ = _dispatch_tool("manage_space_journal", read_args)
    yield {
        "type": "tool_result",
        "data": {"name": "manage_space_journal", "result": journal_result},
    }

    journal_entries = []
    if isinstance(journal_result, dict):
        entries = journal_result.get("entries")
        if isinstance(entries, list):
            journal_entries = entries

    dashboard_args = {"journal_entries": journal_entries}
    yield {
        "type": "tool_call",
        "data": {"name": "show_space_dashboard", "args": dashboard_args},
    }
    dashboard_result, dashboard_html = _dispatch_tool("show_space_dashboard", dashboard_args)
    yield {
        "type": "tool_result",
        "data": {"name": "show_space_dashboard", "result": dashboard_result},
    }

    if dashboard_html is not None:
        yield {"type": "dashboard", "data": {"html": dashboard_html}}

    if isinstance(journal_result, dict) and journal_result.get("status") == "error":
        message = journal_result.get("message", "unknown error")
        text = f"I couldn't read your space journal: {message}."
    elif journal_entries:
        entry_word = "entry" if len(journal_entries) == 1 else "entries"
        pronoun = "it" if len(journal_entries) == 1 else "them"
        text = (
            f"Your space journal has {len(journal_entries)} {entry_word}. "
            f"I rendered {pronoun} on the dashboard."
        )
    else:
        text = (
            "There are no entries in your space journal yet. "
            "I rendered the dashboard with the current journal state."
        )

    yield {"type": "text", "data": {"text": text}}


async def agent_loop(
    message: str,
    history: list[types.Content],
) -> AsyncGenerator[dict[str, Any], None]:
    logger.info("agent_loop_start message_len=%d history_size=%d", len(message), len(history))
    yield {"type": "start", "data": {}}

    history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

    iteration = 0
    try:
        if _is_journal_read_request(message):
            logger.info("journal_read_shortcut message_len=%d", len(message))
            async for event in _journal_read_shortcut():
                yield event
            return

        client = _get_gemini_client()

        for iteration in range(1, MAX_ITERATIONS + 1):
            logger.info(
                "gemini_call iteration=%d model=%s history_len=%d",
                iteration,
                MODEL,
                len(history),
            )
            response = await client.aio.models.generate_content(
                model=MODEL,
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[GEMINI_TOOL],
                ),
            )
            parts = _extract_response_parts(response)
            text_parts = [text for part in parts if (text := _part_text(part))]
            function_calls = [
                function_call
                for part in parts
                if (function_call := _part_function_call(part)) is not None
            ]

            logger.info(
                "gemini_response iteration=%d text_parts=%d function_calls=%d",
                iteration,
                len(text_parts),
                len(function_calls),
            )
            logger.debug(
                "gemini_response_text iteration=%d text=%s",
                iteration,
                _truncate("\n".join(text_parts)),
            )
            for fc in function_calls:
                logger.debug(
                    "gemini_function_call name=%s args=%s",
                    fc.name,
                    _truncate(dict(fc.args or {})),
                )

            if not function_calls:
                text = "\n".join(text_parts) if text_parts else ""
                if not text and iteration > 1:
                    text = (
                        "Done — I've completed the requested actions."
                        " Check the dashboard for updated results."
                    )
                if text:
                    yield {"type": "text", "data": {"text": text}}
                return

            if text_parts:
                yield {"type": "thinking", "data": {"text": "\n".join(text_parts)}}

            history.append(types.Content(role="model", parts=parts))

            response_parts: list[types.Part] = []
            for function_call in function_calls:
                name = function_call.name
                args = dict(function_call.args or {})

                yield {"type": "tool_call", "data": {"name": name, "args": args}}

                result, dashboard_html = _dispatch_tool(name, args)
                yield {"type": "tool_result", "data": {"name": name, "result": result}}

                if dashboard_html is not None:
                    yield {"type": "dashboard", "data": {"html": dashboard_html}}

                response_parts.append(
                    types.Part.from_function_response(
                        name=name,
                        response=_function_response_payload(result),
                    )
                )

            history.append(types.Content(role="user", parts=response_parts))

        logger.warning("agent_loop_max_iterations max=%d", MAX_ITERATIONS)
        yield {
            "type": "text",
            "data": {
                "text": "I reached the maximum reasoning limit before completing the request."
            },
        }
    except Exception as exc:
        logger.exception("agent_loop_error")
        yield {"type": "error", "data": {"message": str(exc)}}
    finally:
        logger.info("agent_loop_done iterations=%d", iteration)
        yield {"type": "done", "data": {}}


async def _sse_event_stream(
    message: str,
) -> AsyncGenerator[dict[str, str], None]:
    import asyncio as _asyncio

    log_queue: _asyncio.Queue[dict[str, Any]] = _asyncio.Queue(maxsize=200)
    cid = get_correlation_id()
    log_handler = SSELogHandler(log_queue, target_cid=cid)
    log_handler.addFilter(CorrelationFilter())
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)

    def _drain_logs() -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        while not log_queue.empty():
            try:
                entry = log_queue.get_nowait()
                entries.append({"event": "log", "data": json.dumps(entry)})
            except _asyncio.QueueEmpty:
                break
        return entries

    try:
        async for event in agent_loop(message, conversation_history):
            for log_event in _drain_logs():
                yield log_event
            event_type = event["type"]
            data = event.get("data", {})
            yield {"event": event_type, "data": json.dumps(data)}
        for log_event in _drain_logs():
            yield log_event
    except Exception as exc:
        logger.exception("sse_stream_error")
        yield {"event": "error", "data": json.dumps({"message": str(exc)})}
        yield {"event": "done", "data": json.dumps({})}
    finally:
        root_logger.removeHandler(log_handler)


@app.get("/")
async def root() -> FileResponse:
    return FileResponse("static/index.html")


@app.post("/chat")
async def chat(request: ChatRequest) -> EventSourceResponse:
    logger.info("chat_request message_len=%d", len(request.message))
    return EventSourceResponse(_sse_event_stream(request.message))


@app.delete("/api/journal/{entry_id}")
async def delete_journal_entry(entry_id: str) -> dict[str, str]:
    try:
        manage_space_journal(operation="delete", entry_id=entry_id)
        return {"status": "ok"}
    except Exception as exc:
        logger.error("delete_journal_entry error entry_id=%s", entry_id, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/reset")
async def reset() -> dict[str, str]:
    global _last_fetch_result
    conversation_history.clear()
    _last_fetch_result = None
    logger.info("conversation_reset")
    return {"status": "ok"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
