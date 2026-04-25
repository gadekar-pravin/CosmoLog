# CosmoLog AI Agent — Implementation Plan

This document breaks the CosmoLog AI Agent web application into 4 independently implementable and testable phases. Each phase builds on the previous and can be committed separately.

**Spec reference:** `docs/agent-functional-specification.md`

**Baseline:** The CosmoLog MCP server is complete (5 phases, 5 test files, ~49 tests). All existing files remain unchanged.

---

# Phase 1: Agent Foundation

## Goal

Install new dependencies, create the system prompt module, update environment configuration, and extend project documentation. This phase has zero behavioral code — it establishes the foundation for the agent loop.

## What This Phase Delivers

- 4 new dependencies in `pyproject.toml` (`google-genai`, `fastapi`, `uvicorn`, `sse-starlette`)
- `agent_prompt.py` — system prompt string constant for the Gemini agent
- Updated `.env.example` with `GEMINI_API_KEY` and `GEMINI_MODEL`
- `tests/test_agent_prompt.py` — ~4 tests verifying prompt content
- Updated `CLAUDE.md` with agent architecture notes

## Prerequisites

- All 5 MCP server phases complete
- `uv sync` passes with existing dependencies

## Acceptance Criteria

- [ ] `uv add google-genai fastapi uvicorn sse-starlette` succeeds
- [ ] `uv sync` installs all new dependencies without errors
- [ ] `agent_prompt.py` defines a `SYSTEM_PROMPT` string constant
- [ ] `SYSTEM_PROMPT` mentions all three tool names: `fetch_space_data`, `manage_space_journal`, `show_space_dashboard`
- [ ] `SYSTEM_PROMPT` instructs the recommended tool-calling order: fetch data, then journal, then dashboard
- [ ] `SYSTEM_PROMPT` instructs the agent to show reasoning before tool calls
- [ ] `.env.example` includes `GEMINI_API_KEY` and `GEMINI_MODEL` entries
- [ ] `tests/test_agent_prompt.py` has ~4 tests, all passing
- [ ] `CLAUDE.md` updated with agent architecture section
- [ ] `uv run pytest tests/test_agent_prompt.py -v` passes
- [ ] `uv run ruff check agent_prompt.py tests/test_agent_prompt.py` is clean

---

## Step 1: Install Dependencies

```bash
cd CosmoLog
uv add google-genai fastapi uvicorn sse-starlette
```

| Package          | Purpose                              |
| ---------------- | ------------------------------------ |
| `google-genai`   | Google Gemini API client (function calling) |
| `fastapi`        | Web framework for `/chat`, `/reset`, `/health` routes |
| `uvicorn`        | ASGI server to run the FastAPI app   |
| `sse-starlette`  | `EventSourceResponse` for SSE streaming in FastAPI |

---

## Step 2: Create `agent_prompt.py`

A single module exporting one constant: `SYSTEM_PROMPT`.

**Reference:** Functional spec section 5.3.

The system prompt must instruct Gemini to:

1. Act as a NASA space exploration assistant named CosmoLog.
2. Use the three available tools to fulfill user requests about space data, journal management, and dashboard rendering.
3. Follow the recommended tool-calling order: fetch data first, then save/manage journal entries, then render the dashboard.
4. Show its reasoning process (thinking steps) before making tool calls.
5. Provide informative, educational responses about NASA data.
6. Always call `show_space_dashboard` at the end of a workflow that involves data fetching or journal changes, passing the most recent data.
7. Handle errors gracefully and explain them to the user.

### Design Notes

- The prompt is a plain string constant, not a template — no runtime interpolation needed.
- Keep the prompt concise but specific. Gemini's function-calling behavior is largely driven by the `FunctionDeclaration` schemas, not the system prompt. The prompt guides *when* and *why* to call tools, not *how*.
- Include explicit instruction to pass `space_data` and `journal_entries` to `show_space_dashboard` so the dashboard renders with current data.

---

## Step 3: Update `.env.example`

Add the Gemini configuration variables below the existing `NASA_API_KEY` entry:

```
# Google Gemini API key — required for the AI agent
# Get a key at https://aistudio.google.com/apikey
GEMINI_API_KEY=your-gemini-api-key-here

# Gemini model name (optional, defaults to gemini-2.5-flash)
GEMINI_MODEL=gemini-2.5-flash
```

**Reference:** Functional spec section 10.1.

---

## Step 4: Create `tests/test_agent_prompt.py`

```python
from agent_prompt import SYSTEM_PROMPT


def test_system_prompt_is_string():
    """SYSTEM_PROMPT must be a non-empty string."""
    assert isinstance(SYSTEM_PROMPT, str)
    assert len(SYSTEM_PROMPT) > 100


def test_system_prompt_mentions_all_tools():
    """SYSTEM_PROMPT must reference all three MCP tools by name."""
    assert "fetch_space_data" in SYSTEM_PROMPT
    assert "manage_space_journal" in SYSTEM_PROMPT
    assert "show_space_dashboard" in SYSTEM_PROMPT


def test_system_prompt_mentions_tool_order():
    """SYSTEM_PROMPT should instruct the recommended tool-calling order."""
    # The fetch instruction should appear before journal, journal before dashboard
    fetch_pos = SYSTEM_PROMPT.index("fetch_space_data")
    journal_pos = SYSTEM_PROMPT.index("manage_space_journal")
    dashboard_pos = SYSTEM_PROMPT.index("show_space_dashboard")
    assert fetch_pos < journal_pos < dashboard_pos


def test_system_prompt_mentions_reasoning():
    """SYSTEM_PROMPT should instruct the agent to show reasoning."""
    prompt_lower = SYSTEM_PROMPT.lower()
    assert "reason" in prompt_lower or "think" in prompt_lower
```

### Test Summary

| # | Test Name | What It Verifies |
|---|---|---|
| 1 | `test_system_prompt_is_string` | `SYSTEM_PROMPT` is a non-empty string of reasonable length |
| 2 | `test_system_prompt_mentions_all_tools` | All three tool names appear in the prompt |
| 3 | `test_system_prompt_mentions_tool_order` | Tool names appear in the recommended order |
| 4 | `test_system_prompt_mentions_reasoning` | Prompt instructs reasoning/thinking behavior |

---

## Step 5: Update `CLAUDE.md`

Add an "Agent Architecture" section after the existing "Architecture" section. Include:

- The new file responsibilities (`agent.py`, `agent_prompt.py`, `static/index.html`)
- The agent's relationship to the MCP tools (in-process import, not MCP transport)
- The `TOOL_REGISTRY` dispatch pattern
- The async generator pattern for `agent_loop()`
- The SSE event types
- The `PrefabApp.html()` special handling for dashboard rendering
- Updated commands section with `uv run python agent.py` to start the agent server

---

## Verification

```bash
cd CosmoLog
uv sync
uv run pytest tests/test_agent_prompt.py -v     # 4 tests pass
uv run ruff check agent_prompt.py tests/test_agent_prompt.py
uv run ruff format --check agent_prompt.py tests/test_agent_prompt.py
```

---

## Commit

```
feat: add agent system prompt and dependencies
```

---

# Phase 2: Agent Loop + Tool Dispatch

## Goal

Build the core agent logic: the `TOOL_REGISTRY`, Gemini `FunctionDeclaration` objects, the `agent_loop()` async generator, and the `_dispatch_tool()` function with special `PrefabApp` handling. This phase produces a testable agent loop that yields SSE event dicts but does not yet expose HTTP routes.

## What This Phase Delivers

- `agent.py` (partial) — `TOOL_REGISTRY`, `FunctionDeclaration` objects, `agent_loop()` async generator, `_dispatch_tool()`, Gemini client initialization
- `tests/test_agent.py` — ~11 tests covering the agent loop (mocking the Gemini client)

## Prerequisites

- Phase 1 complete (`agent_prompt.py`, dependencies installed)
- A valid `GEMINI_API_KEY` is not required — tests mock the Gemini client

## Acceptance Criteria

- [ ] `TOOL_REGISTRY` maps all 3 tool names to their Python functions imported from `mcp_server.py`
- [ ] 3 `FunctionDeclaration` objects match the tool parameter schemas from spec section 5.2
- [ ] `agent_loop(message, history)` is an async generator that yields `dict` events
- [ ] Event dicts have a `"type"` key matching the SSE event types: `start`, `thinking`, `tool_call`, `tool_result`, `dashboard`, `text`, `error`, `done`
- [ ] `_dispatch_tool()` calls the correct function from `TOOL_REGISTRY`
- [ ] `_dispatch_tool()` handles `show_space_dashboard` specially: calls `.html()` on the `PrefabApp`, yields a `dashboard` event with the HTML, returns a summary string to Gemini
- [ ] `agent_loop()` respects `MAX_ITERATIONS` (default 10) and yields an error event if exceeded
- [ ] `agent_loop()` catches Gemini API errors and yields an `error` event instead of raising
- [ ] `agent_loop()` handles unknown tool names from Gemini gracefully
- [ ] `tests/test_agent.py` has ~11 tests, all passing
- [ ] `uv run pytest tests/test_agent.py -v` passes
- [ ] `uv run ruff check agent.py tests/test_agent.py` is clean

---

## Step 1: Define `TOOL_REGISTRY`

Import the three tool functions from `mcp_server.py` and map them by name:

```python
from mcp_server import fetch_space_data, manage_space_journal, show_space_dashboard

TOOL_REGISTRY = {
    "fetch_space_data": fetch_space_data,
    "manage_space_journal": manage_space_journal,
    "show_space_dashboard": show_space_dashboard,
}
```

**Reference:** Functional spec section 5.4.

### Design Notes

- In-process import, not MCP transport — the tool functions are plain Python callables.
- This follows the established pattern from EAG3-03 (`gift_whisperer/app.py`).

---

## Step 2: Define `FunctionDeclaration` Objects

Create Gemini `FunctionDeclaration` objects for all three tools. Parameter names, types, and descriptions must match the MCP tool signatures exactly.

**Reference:** Functional spec section 5.2.

Use `google.genai.types.FunctionDeclaration` with `properties` and `required` fields matching each tool's parameter table:

| Tool | Parameters | Required |
|---|---|---|
| `fetch_space_data` | `date` (str), `rover` (str), `sol` (int), `photo_count` (int), `neo_days` (int) | None |
| `manage_space_journal` | `operation` (str), `entry_id` (str), `payload` (obj), `tag_filter` (str) | `operation` |
| `show_space_dashboard` | `space_data` (obj), `journal_entries` (array), `tag_filter` (str) | None |

### Design Notes

- Gemini's function-calling uses these declarations to decide when and how to call tools. Accuracy here is critical — a mismatched type or missing description will cause Gemini to construct wrong arguments.
- Use `google.genai.types.Schema` for parameter schemas. The `type` values are Gemini's type enum (STRING, INTEGER, OBJECT, ARRAY), not Python types.
- The `payload` parameter for `manage_space_journal` and `space_data` for `show_space_dashboard` are OBJECT types with no strict inner schema — Gemini constructs these from conversation context.

---

## Step 3: Initialize Gemini Client

```python
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
```

**Reference:** Functional spec section 10.1.

### Design Notes

- The client is module-level so it persists across requests (similar to `_nasa_client` in `mcp_server.py`).
- `GEMINI_API_KEY` is required at runtime but not for tests (tests mock the client).

---

## Step 4: Implement `_dispatch_tool()`

This function takes a tool name and arguments, dispatches to the correct function, and handles the `PrefabApp` special case.

**Reference:** Functional spec section 5.4.

```
_dispatch_tool(name, args) -> (result_for_gemini, optional_dashboard_html)
```

Key behaviors:

1. Look up `name` in `TOOL_REGISTRY`. If not found, return an error dict.
2. Call the function with `**args`.
3. **Special case for `show_space_dashboard`:** The function returns a `PrefabApp`. Call `.html()` to get the HTML string. Return a summary string (e.g., `"Dashboard rendered successfully"`) as the Gemini result, and the HTML separately for the `dashboard` SSE event.
4. For other tools, `model_dump()` or return the dict result directly.
5. Catch exceptions from tool functions and return an error dict so Gemini can explain the failure.

### Design Notes

- The return type is a tuple `(result_for_gemini: dict | str, dashboard_html: str | None)`. This keeps the function pure — it does not yield SSE events itself.
- Type coercion: Gemini sometimes sends `float` for `int` parameters (e.g., `photo_count: 3.0`). Coerce numeric arguments to `int` where the tool signature expects it.
- The summary string returned for dashboard prevents bloating the conversation context with 20-50KB of HTML markup.

---

## Step 5: Implement `agent_loop()` Async Generator

The core agent loop. This is an async generator that yields SSE event dicts.

**Reference:** Functional spec sections 5.1 and 6.2.

```python
async def agent_loop(
    message: str,
    history: list[dict],
) -> AsyncGenerator[dict, None]:
    ...
```

### Loop Logic

1. Yield `{"type": "start", "data": {}}`.
2. Append the user message to `history`.
3. Send `history` to Gemini (with `SYSTEM_PROMPT` and `FunctionDeclaration` tools).
4. Parse the response:
   - If the response contains **text** (thinking/reasoning), yield `{"type": "thinking", "data": {"text": ...}}`.
   - If the response contains **function calls**:
     a. For each function call, yield `{"type": "tool_call", "data": {"name": ..., "args": ...}}`.
     b. Call `_dispatch_tool()` for each.
     c. Yield `{"type": "tool_result", "data": {"name": ..., "result": ...}}`.
     d. If a `dashboard` HTML was returned, yield `{"type": "dashboard", "data": {"html": ...}}`.
     e. Feed all tool results back to Gemini and repeat from step 4.
   - If the response contains **text only** (no function calls), yield `{"type": "text", "data": {"text": ...}}` and exit the loop.
5. Guard: if iterations exceed `MAX_ITERATIONS` (default 10), yield `{"type": "text", "data": {"text": "..."}}` explaining the limit was reached.
6. Yield `{"type": "done", "data": {}}`.

### Error Handling

- Wrap the Gemini API call in try/except. On error, yield `{"type": "error", "data": {"message": ...}}` and then `{"type": "done", "data": {}}`.
- Tool exceptions are caught inside `_dispatch_tool()` and returned as error dicts to Gemini, which decides how to explain the failure.

### Design Notes

- **Async generator pattern:** The loop yields event dicts (plain Python dicts), not SSE-formatted strings. This decouples the business logic from the HTTP transport layer. Phase 3 wraps this generator in `EventSourceResponse`.
- **History mutation:** The function appends to the `history` list in-place. The caller (the FastAPI route in Phase 3) owns the list and persists it across requests.
- **Parallel tool calls:** Gemini may return multiple function calls in a single response. Dispatch them sequentially (per spec section 5.1) and collect all results before sending them back to Gemini together.

---

## Step 6: Create `tests/test_agent.py`

All tests mock the Gemini client. No real API calls.

**Test strategy:** Use `unittest.mock.AsyncMock` (or `MagicMock` with appropriate return values) to simulate Gemini responses. The key mocking target is `gemini_client.aio.models.generate_content` (or whatever the async generation method is — verify from the `google-genai` SDK).

### Test Table

| # | Test Name | What It Verifies |
|---|---|---|
| 1 | `test_tool_registry_has_three_tools` | `TOOL_REGISTRY` contains exactly 3 entries |
| 2 | `test_tool_registry_keys` | Keys are `fetch_space_data`, `manage_space_journal`, `show_space_dashboard` |
| 3 | `test_tool_registry_values_callable` | All values in `TOOL_REGISTRY` are callable |
| 4 | `test_function_declarations_count` | Exactly 3 `FunctionDeclaration` objects defined |
| 5 | `test_function_declaration_names` | Declaration names match `TOOL_REGISTRY` keys |
| 6 | `test_dispatch_tool_fetch` | `_dispatch_tool("fetch_space_data", {...})` calls the correct function and returns a dict |
| 7 | `test_dispatch_tool_dashboard_returns_html` | `_dispatch_tool("show_space_dashboard", {...})` returns dashboard HTML separately from the Gemini result |
| 8 | `test_dispatch_tool_unknown_name` | `_dispatch_tool("nonexistent", {})` returns an error dict |
| 9 | `test_agent_loop_text_only` | Mock Gemini to return text (no function calls) — loop yields `start`, `text`, `done` events |
| 10 | `test_agent_loop_with_tool_call` | Mock Gemini to return a function call then text — loop yields the full event sequence |
| 11 | `test_agent_loop_gemini_error` | Mock Gemini to raise an exception — loop yields `start`, `error`, `done` events |

### Test Notes

- Tests 6-8 test `_dispatch_tool()` directly. Use `monkeypatch` or `unittest.mock.patch` to mock the underlying tool functions so no NASA API calls or file I/O occur.
- Tests 9-11 test `agent_loop()` end-to-end with a mocked Gemini client. Collect all yielded events into a list using `async for` and verify the sequence.
- For the dashboard test (7): mock `show_space_dashboard` to return a mock `PrefabApp` object with a `.html()` method that returns a test HTML string.

---

## Verification

```bash
cd CosmoLog
uv run pytest tests/test_agent.py -v          # ~11 tests pass
uv run pytest -v                               # all tests pass (~53+ total)
uv run ruff check agent.py tests/test_agent.py
uv run ruff format --check agent.py tests/test_agent.py
```

Expected test count breakdown:
- Existing MCP server tests: ~49
- `test_agent_prompt.py`: 4 tests (Phase 1)
- `test_agent.py`: ~11 tests (this phase)
- **Total: ~64 tests**

---

## Commit

```
feat: add agent loop with tool dispatch and Gemini integration
```

---

# Phase 3: FastAPI Server + SSE Streaming

## Goal

Complete `agent.py` by adding the FastAPI application, 4 HTTP routes, `EventSourceResponse` wrapping of the agent loop generator, conversation state management, and the uvicorn entrypoint. After this phase the agent server is fully runnable.

## What This Phase Delivers

- `agent.py` (complete) — FastAPI app with 4 routes (`GET /`, `POST /chat`, `POST /reset`, `GET /health`), conversation state, uvicorn entrypoint
- `tests/test_agent_server.py` — ~5 tests using `httpx.AsyncClient` to test the HTTP layer

## Prerequisites

- Phase 2 complete (`agent.py` has the agent loop and tool dispatch)
- `static/` directory exists (can be empty or contain a placeholder `index.html` — Phase 4 builds the real frontend)

## Acceptance Criteria

- [ ] `GET /` serves `static/index.html`
- [ ] `POST /chat` accepts `{"message": "..."}` and returns an SSE stream (`text/event-stream`)
- [ ] SSE events match the types defined in spec section 6.2: `start`, `thinking`, `tool_call`, `tool_result`, `dashboard`, `text`, `error`, `done`
- [ ] `POST /reset` clears conversation history and returns `{"status": "ok"}`
- [ ] `GET /health` returns `{"status": "healthy"}`
- [ ] Conversation history persists across `/chat` requests within a session
- [ ] `uv run python agent.py` starts the server on `HOST:PORT` (defaults to `0.0.0.0:8000`)
- [ ] `tests/test_agent_server.py` has ~5 tests, all passing
- [ ] `uv run pytest tests/test_agent_server.py -v` passes
- [ ] `uv run ruff check agent.py tests/test_agent_server.py` is clean

---

## Step 1: Create FastAPI App and Static Mount

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI(title="CosmoLog AI Agent")
app.mount("/static", StaticFiles(directory="static"), name="static")
```

**Reference:** Functional spec section 6.1.

### Design Notes

- `GET /` is a dedicated route returning `FileResponse("static/index.html")`, not relying on the static mount for the root path.
- The static mount at `/static` allows the HTML to reference CSS/JS files if needed in the future, though Phase 4's `index.html` is self-contained.

---

## Step 2: Implement Conversation State

```python
conversation_history: list[dict] = []
```

**Reference:** Functional spec section 6.3.

### Design Notes

- Single-user, in-memory — a plain Python list. No session management.
- The list is mutated in-place by `agent_loop()` (it appends user/assistant/tool messages).
- Lost on server restart. Cleared by `POST /reset`.
- This is intentionally simple for a demo application.

---

## Step 3: Implement `POST /chat`

This route:

1. Accepts a JSON body: `{"message": "..."}`.
2. Calls `agent_loop(message, conversation_history)`.
3. Wraps the async generator in an `EventSourceResponse` from `sse-starlette`.
4. Returns the SSE stream.

**Reference:** Functional spec sections 6.1 and 6.2.

### SSE Formatting

The `agent_loop()` generator yields plain dicts like `{"type": "text", "data": {"text": "..."}}`. The route must convert these to SSE format:

```
event: text
data: {"text": "Hello!"}

```

Use `EventSourceResponse` with a wrapper async generator that:
- Sets the `event` field from `dict["type"]`
- JSON-serializes `dict["data"]` as the `data` field

### Design Notes

- **POST-based SSE:** The standard `EventSource` browser API only supports GET. The frontend (Phase 4) uses `fetch()` with a `ReadableStream` reader to consume the POST-based SSE stream. This is the standard modern pattern for chat applications.
- The route should catch any unexpected exceptions from the generator and yield a final `error` + `done` event to prevent the SSE stream from hanging.

---

## Step 4: Implement `POST /reset`

```python
@app.post("/reset")
async def reset():
    conversation_history.clear()
    return {"status": "ok"}
```

**Reference:** Functional spec section 6.1.

---

## Step 5: Implement `GET /health`

```python
@app.get("/health")
async def health():
    return {"status": "healthy"}
```

**Reference:** Functional spec section 6.1.

---

## Step 6: Add Uvicorn Entrypoint

```python
if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
```

**Reference:** Functional spec section 10.1 (HOST/PORT env vars).

---

## Step 7: Create Placeholder `static/index.html`

A minimal HTML file so `GET /` works before Phase 4 builds the real frontend:

```html
<!DOCTYPE html>
<html><body><h1>CosmoLog AI Agent</h1><p>Frontend coming in Phase 4.</p></body></html>
```

---

## Step 8: Create `tests/test_agent_server.py`

Use `httpx.AsyncClient` with FastAPI's `TestClient` pattern (`ASGITransport`).

**Test strategy:** Mock the `agent_loop` generator to return a fixed sequence of events. This tests the HTTP layer independently of the Gemini integration.

### Test Table

| # | Test Name | What It Verifies |
|---|---|---|
| 1 | `test_health_endpoint` | `GET /health` returns 200 with `{"status": "healthy"}` |
| 2 | `test_reset_endpoint` | `POST /reset` returns 200 with `{"status": "ok"}` |
| 3 | `test_chat_returns_sse_content_type` | `POST /chat` with `{"message": "hi"}` returns `text/event-stream` content type |
| 4 | `test_chat_sse_has_done_event` | SSE stream from `/chat` includes a `done` event |
| 5 | `test_root_serves_html` | `GET /` returns 200 with HTML content |

### Test Notes

- Use `pytest-asyncio` for async test functions.
- Mock `agent_loop` at the module level in `agent.py` so the tests don't need a Gemini API key.
- For tests 3-4: parse the SSE stream from the response body. The response is `text/event-stream` — split on `\n\n` and parse `event:` / `data:` lines.
- Test 5 requires the placeholder `static/index.html` from Step 7.

---

## Verification

```bash
cd CosmoLog
uv run pytest tests/test_agent_server.py -v    # ~5 tests pass
uv run pytest -v                                # all tests pass (~69+ total)
uv run ruff check agent.py tests/test_agent_server.py
uv run ruff format --check agent.py tests/test_agent_server.py
```

### Manual Server Test

```bash
uv run python agent.py
# Server starts on http://0.0.0.0:8000
# GET http://localhost:8000/health -> {"status": "healthy"}
# POST http://localhost:8000/reset -> {"status": "ok"}
# GET http://localhost:8000/ -> placeholder HTML
# Ctrl+C to stop
```

Expected test count breakdown:
- Existing MCP server tests: ~49
- `test_agent_prompt.py`: 4 tests
- `test_agent.py`: ~11 tests
- `test_agent_server.py`: ~5 tests (this phase)
- **Total: ~69 tests**

---

## Commit

```
feat: add FastAPI server with SSE streaming and chat endpoint
```

---

# Phase 4: Frontend UI

## Goal

Build the complete single-page frontend (`static/index.html`) with a split-pane layout, dark space theme, glass morphism, SSE event handling, chat panel with collapsible thinking/tool steps, dashboard iframe, suggested prompts, responsive layout, and animations.

## What This Phase Delivers

- `static/index.html` — complete self-contained frontend (HTML + CSS + JS in one file)

## Prerequisites

- Phase 3 complete (`agent.py` fully runnable with all routes)
- A valid `GEMINI_API_KEY` in `.env` for manual testing

## Acceptance Criteria

- [ ] `static/index.html` is a single self-contained file (no external JS/CSS dependencies besides Google Fonts)
- [ ] Split-pane layout: chat panel (~40% width) on the left, dashboard panel (~60% width) on the right
- [ ] Responsive: side-by-side above 1024px, stacked below
- [ ] Dark space theme with background `#0a0a1a`, glass morphism on cards/panels
- [ ] Inter and JetBrains Mono fonts loaded from Google Fonts
- [ ] Chat panel displays user messages (right-aligned) and agent messages (left-aligned)
- [ ] Thinking steps displayed as collapsible sections with muted italic text
- [ ] Tool calls displayed as collapsible cards showing name and arguments
- [ ] Tool results nested inside tool call cards, collapsed by default
- [ ] Dashboard panel shows a space-themed placeholder initially
- [ ] Dashboard panel updates via iframe `srcdoc` when a `dashboard` SSE event arrives
- [ ] 4 suggested prompt buttons displayed when chat is empty, hidden after first message
- [ ] Input bar with text field, send button, Enter key support
- [ ] Input disabled while agent is processing
- [ ] Reset Chat button in the header clears chat and resets dashboard to placeholder
- [ ] SSE consumption via `fetch()` + `ReadableStream` (not `EventSource`)
- [ ] Message appear animation (fade-in + slide-up)
- [ ] Typing indicator (three animated dots) while waiting for agent response
- [ ] Subtle CSS starfield or particle effect on the background
- [ ] Error events displayed as error-styled message bubbles
- [ ] Manual verification passes (no automated tests for frontend)

---

## Step 1: HTML Structure

**Reference:** Functional spec section 7.1.

The page structure:

```
<header>  — Logo, title ("CosmoLog AI Agent"), Reset Chat button
<main>    — Split pane container
  <aside> — Chat panel (messages, input bar, suggested prompts)
  <section> — Dashboard panel (placeholder or iframe)
</main>
```

### Key Elements

- **Chat messages container:** Scrollable div that auto-scrolls to the bottom on new messages.
- **Suggested prompts:** 4 buttons above the input bar, visible only when chat is empty.
- **Input bar:** Fixed at the bottom of the chat panel. Text input + send button.
- **Dashboard iframe:** Hidden initially. Shown when the first `dashboard` event arrives. Uses `srcdoc` attribute.
- **Dashboard placeholder:** Visible initially. Space-themed with a prompt message and subtle animation.

---

## Step 2: CSS Design System

**Reference:** Functional spec section 7.4.

### Color Tokens

| Token | Value | CSS Variable |
|---|---|---|
| Background | `#0a0a1a` | `--bg` |
| Surface | `#0f0f2e` | `--surface` |
| Surface hover | `#1a1a3e` | `--surface-hover` |
| Cosmic blue | `#4f8cff` | `--cosmic-blue` |
| Nebula purple | `#a855f7` | `--nebula-purple` |
| Star white | `#e2e8f0` | `--star-white` |
| Muted | `#64748b` | `--muted` |
| Success | `#22c55e` | `--success` |
| Danger | `#ef4444` | `--danger` |
| Border | `rgba(79, 140, 255, 0.15)` | `--border` |

### Glass Morphism

Applied to chat panel, dashboard panel, message bubbles, and tool call cards:

```css
background: rgba(15, 15, 46, 0.8);
backdrop-filter: blur(12px);
border: 1px solid rgba(79, 140, 255, 0.15);
border-radius: 12px;
```

### Typography

- Body text: `Inter`, loaded from Google Fonts
- Code/JSON: `JetBrains Mono`, loaded from Google Fonts

### Animations

- **Message appear:** `@keyframes fadeSlideUp` — opacity 0 to 1, translateY(10px) to 0
- **Thinking pulse:** `@keyframes pulse` — opacity oscillation on the thinking indicator
- **Typing indicator:** `@keyframes bounce` — three dots with staggered animation-delay
- **Dashboard transition:** CSS transition on opacity when dashboard content updates
- **Stars background:** CSS-only starfield using multiple `box-shadow` values on pseudo-elements, or `radial-gradient` layers

### Responsive Breakpoint

```css
@media (max-width: 1024px) {
    main { flex-direction: column; }
    aside { width: 100%; }
    section { width: 100%; }
}
```

---

## Step 3: JavaScript — SSE Handling

**Reference:** Functional spec sections 6.2 and 7.2.

### POST-Based SSE Consumption

The standard `EventSource` API only supports GET. Since `/chat` is POST, use `fetch()` with a `ReadableStream` reader:

```javascript
const response = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: userMessage }),
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
// Read chunks, split on \n\n, parse event: and data: lines
```

### Event Routing

| SSE Event Type | JavaScript Action |
|---|---|
| `start` | Show typing indicator |
| `thinking` | Add collapsible thinking section to chat |
| `tool_call` | Add collapsible tool call card to chat |
| `tool_result` | Append result to the most recent tool call card |
| `dashboard` | Set `iframe.srcdoc` to the HTML, hide placeholder |
| `text` | Add agent message bubble to chat |
| `error` | Add error-styled message bubble |
| `done` | Hide typing indicator, re-enable input |

### State Management

- `isProcessing` flag: disables input while agent is responding
- `hasMessages` flag: controls suggested prompts visibility
- Chat auto-scroll: after each new message element, scroll the container to the bottom

---

## Step 4: Suggested Prompts

**Reference:** Functional spec section 7.5.

Four buttons with the exact text:

1. "Fetch today's APOD and show it on the dashboard"
2. "Fetch NASA data, save the APOD to my journal, and show the dashboard"
3. "Show me what's in my space journal"
4. "Fetch Mars rover photos and near-Earth objects, save them all, and display everything"

On click: fill the input field and trigger send. Hide all prompt buttons after the first message.

---

## Step 5: Reset Chat

The "Reset Chat" button in the header:

1. Calls `POST /reset` to clear server-side history.
2. Clears all chat messages from the DOM.
3. Resets the dashboard iframe to the placeholder state.
4. Shows suggested prompts again.

---

## Verification

### Manual Testing Checklist

```bash
# Start the server
uv run python agent.py

# Open http://localhost:8000 in a browser
```

- [ ] Page loads with dark space theme and glass morphism effects
- [ ] Four suggested prompt buttons are visible
- [ ] Stars/particle background effect is visible
- [ ] Clicking a suggested prompt sends the message and hides the prompts
- [ ] User message appears right-aligned
- [ ] Typing indicator shows while waiting for response
- [ ] Thinking steps appear as collapsible items
- [ ] Tool call cards appear and are expandable
- [ ] Dashboard renders in the right panel iframe
- [ ] Agent's final text response appears left-aligned
- [ ] Input is disabled during processing, re-enabled after
- [ ] Enter key submits a message
- [ ] Reset Chat clears everything and shows prompts again
- [ ] On narrow viewport (<1024px), layout stacks vertically
- [ ] Error events (if triggered) show with red accent styling

### Lint Check

```bash
# No Python tests for frontend — lint the Python files only
uv run ruff check agent.py
uv run ruff format --check agent.py
```

### Full Test Suite

```bash
uv run pytest -v    # all ~69 tests still pass (no new Python tests this phase)
```

---

## Commit

```
feat: build agent frontend with chat UI and dashboard panel
```

---

# Summary

## Phase Overview

| Phase | Files Created/Modified | Tests Added | Running Total |
|---|---|---|---|
| 1: Agent Foundation | `agent_prompt.py`, `.env.example`, `CLAUDE.md`, `pyproject.toml` | 4 | ~53 |
| 2: Agent Loop + Tool Dispatch | `agent.py` (partial) | ~11 | ~64 |
| 3: FastAPI Server + SSE Streaming | `agent.py` (complete), `static/index.html` (placeholder) | ~5 | ~69 |
| 4: Frontend UI | `static/index.html` (complete) | 0 (manual) | ~69 |

## New Files After All 4 Phases

```
CosmoLog/
  # New files
  agent.py               # FastAPI server + Gemini agent loop + SSE streaming
  agent_prompt.py        # System prompt constant
  static/
    index.html           # Single-page frontend (chat + dashboard UI)

  # Modified files
  pyproject.toml         # 4 new dependencies added
  .env.example           # GEMINI_API_KEY, GEMINI_MODEL added
  CLAUDE.md              # Agent architecture section added

  # New test files
  tests/
    test_agent_prompt.py # Phase 1: 4 tests
    test_agent.py        # Phase 2: ~11 tests
    test_agent_server.py # Phase 3: ~5 tests
```

## Key Design Decisions

1. **Async generator pattern** — `agent_loop()` yields event dicts, decoupling business logic from HTTP transport for testability.
2. **Single `agent.py` file** — per spec, but split across Phase 2 (loop logic) and Phase 3 (server routes) for incremental delivery.
3. **POST-based SSE** — frontend uses `fetch()` + `ReadableStream` instead of `EventSource` (which only supports GET).
4. **Dashboard special handling** — `.html()` on `PrefabApp`, HTML sent via SSE `dashboard` event, summary string returned to Gemini to avoid context bloat.
5. **In-process tool import** — tools imported directly from `mcp_server.py`, not called over MCP transport, for simplicity and reliability.

## Spec Coverage

| Spec Section | Covered In |
|---|---|
| 5.1 Agent Loop | Phase 2 |
| 5.2 Tool Declarations | Phase 2 |
| 5.3 System Prompt | Phase 1 |
| 5.4 Tool Dispatch | Phase 2 |
| 5.5 Dashboard Pipeline | Phase 2 |
| 6.1 FastAPI Routes | Phase 3 |
| 6.2 SSE Event Types | Phase 2 (yields), Phase 3 (transport) |
| 6.3 Conversation State | Phase 3 |
| 7.1–7.5 Frontend UI | Phase 4 |
| 8.1 Multi-Turn Reasoning | Phase 2 |
| 8.2 Thinking Visibility | Phase 2 |
| 8.3 Error Handling | Phase 2, Phase 3 |
| 8.4 Dashboard Trigger Rules | Phase 1 (prompt), Phase 2 (dispatch) |
| 8.5 Tool Argument Construction | Phase 2 |
| 10.1 Environment Variables | Phase 1, Phase 3 |
| 11.1–11.2 Project Structure | Phase 1 (CLAUDE.md) |
| 13.1–13.6 Acceptance Criteria | All phases |
