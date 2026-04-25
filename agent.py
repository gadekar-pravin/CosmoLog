from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator, Callable
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, field_validator
from sse_starlette.sse import EventSourceResponse

from agent_prompt import SYSTEM_PROMPT
from mcp_server import fetch_space_data, manage_space_journal, show_space_dashboard

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
        description="Fetch live NASA space data: APOD, Mars rover photos, and near-Earth objects.",
        parameters=_object_schema(
            {
                "date": types.Schema(
                    type=types.Type.STRING,
                    description="Date for APOD lookup (YYYY-MM-DD). Defaults to today.",
                ),
                "rover": types.Schema(
                    type=types.Type.STRING,
                    description="Mars rover name. Defaults to curiosity.",
                ),
                "sol": types.Schema(
                    type=types.Type.INTEGER,
                    description="Martian sol for rover photos. Defaults to latest available.",
                ),
                "photo_count": types.Schema(
                    type=types.Type.INTEGER,
                    description="Number of rover photos to return. Defaults to 3.",
                ),
                "neo_days": types.Schema(
                    type=types.Type.INTEGER,
                    description="Number of days ahead to check for NEOs. Defaults to 7.",
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
    return _gemini_client


def _coerce_tool_args(name: str, args: dict[str, Any]) -> dict[str, Any]:
    coerced = dict(args)
    if name == "fetch_space_data":
        for key in ("sol", "photo_count", "neo_days"):
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


def _dispatch_tool(name: str, args: dict[str, Any]) -> tuple[Any, str | None]:
    tool = TOOL_REGISTRY.get(name)
    if tool is None:
        return {"status": "error", "message": f"Unknown tool: {name}"}, None

    coerced_args = _coerce_tool_args(name, args)
    try:
        result = tool(**coerced_args)
        if name == "show_space_dashboard":
            html = result.html()
            return "Dashboard rendered successfully", html
        return _serialize_result(result), None
    except Exception as exc:
        return {"status": "error", "message": str(exc)}, None


async def agent_loop(
    message: str,
    history: list[types.Content],
) -> AsyncGenerator[dict[str, Any], None]:
    yield {"type": "start", "data": {}}

    history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

    try:
        client = _get_gemini_client()

        for _ in range(MAX_ITERATIONS):
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

            if not function_calls:
                if text_parts:
                    yield {"type": "text", "data": {"text": "\n".join(text_parts)}}
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

        yield {
            "type": "text",
            "data": {
                "text": "I reached the maximum reasoning limit before completing the request."
            },
        }
    except Exception as exc:
        yield {"type": "error", "data": {"message": str(exc)}}
    finally:
        yield {"type": "done", "data": {}}


async def _sse_event_stream(
    message: str,
) -> AsyncGenerator[dict[str, str], None]:
    try:
        async for event in agent_loop(message, conversation_history):
            event_type = event["type"]
            data = event.get("data", {})
            yield {"event": event_type, "data": json.dumps(data)}
    except Exception as exc:
        yield {"event": "error", "data": json.dumps({"message": str(exc)})}
        yield {"event": "done", "data": json.dumps({})}


@app.get("/")
async def root() -> FileResponse:
    return FileResponse("static/index.html")


@app.post("/chat")
async def chat(request: ChatRequest) -> EventSourceResponse:
    return EventSourceResponse(_sse_event_stream(request.message))


@app.post("/reset")
async def reset() -> dict[str, str]:
    conversation_history.clear()
    return {"status": "ok"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
