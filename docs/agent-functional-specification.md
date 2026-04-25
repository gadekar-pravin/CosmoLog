# Functional Specification: CosmoLog AI Agent Web Application

## 1. Document Overview

### 1.1 Project Name

**CosmoLog AI Agent**

### 1.2 Purpose

This document specifies the functional requirements for an AI agent web application that wraps the existing CosmoLog MCP server. The agent uses **Google Gemini** as its LLM backend to orchestrate the three CosmoLog MCP tools through a conversational chat interface with live dashboard rendering.

### 1.3 Relationship to Existing MCP Server

The CosmoLog MCP server (specified in `docs/mcp/functional-specification.md`) provides three tools:

1. `fetch_space_data` — Fetch live NASA data (APOD, Mars rover photos, near-Earth objects).
2. `manage_space_journal` — CRUD operations on a local `space_journal.json` file.
3. `show_space_dashboard` — Render a Prefab UI dashboard.

The agent web application imports and calls these tools directly, adding a conversational AI layer and a browser-based UI on top of the existing tool implementations.

### 1.4 Assignment Context

This is the agent web application component for EAG3-04. It demonstrates an AI agent that can use MCP tools through multi-turn reasoning, with results streamed to the browser in real time.

---

## 2. Product Summary

The CosmoLog AI Agent is a web application that presents a split-pane interface in the browser:

- **Left panel (~40% width):** A conversational chat interface where the user interacts with a Gemini-powered AI agent. The agent can fetch NASA data, manage journal entries, and trigger dashboard rendering by calling the CosmoLog MCP tools.
- **Right panel (~60% width):** A live dashboard panel that displays the Prefab-rendered CosmoLog dashboard inside an iframe whenever the agent calls `show_space_dashboard`.

The user types natural language prompts. The agent reasons about which tools to call, executes them, and streams its thinking, tool calls, tool results, and final responses back to the browser via Server-Sent Events (SSE). When the agent renders a dashboard, the Prefab HTML is injected into the right panel in real time.

---

## 3. Target Users

### 3.1 Primary User

A student or developer demonstrating an AI agent that orchestrates MCP tools through a conversational interface.

### 3.2 Secondary User

An evaluator or instructor reviewing whether the agent correctly uses all three MCP tools, handles multi-turn tool calling, and renders a live dashboard.

### 3.3 Demo Audience

Anyone watching a live demo who benefits from seeing the agent's reasoning process (thinking steps, tool calls, results) alongside the rendered dashboard output.

---

## 4. Architecture Overview

### 4.1 System Diagram

```
Browser (HTML/CSS/JS)
  |
  |  POST /chat (SSE stream)
  |  POST /reset
  |  GET /
  v
FastAPI (agent.py)
  |
  |-- Gemini API (google-genai)
  |     - Multi-turn conversation
  |     - Function calling (tool_use)
  |
  |-- MCP Tools (in-process import)
        - fetch_space_data()     --> nasa_client.py --> NASA APIs
        - manage_space_journal() --> journal.py     --> space_journal.json
        - show_space_dashboard() --> dashboard.py   --> PrefabApp --> .html()
```

### 4.2 MCP Integration: In-Process Import

The agent imports the MCP tool functions directly from `mcp_server.py` rather than connecting to the MCP server over HTTP.

**Rationale:**

- Simplest and most reliable approach for a single-user demo application.
- Avoids the complexity of running a separate MCP server process and managing an HTTP client.
- Follows the established pattern from EAG3-03 (`gift_whisperer/app.py`).
- Tool functions are plain Python functions — they can be called directly without the MCP transport layer.

**Implementation:** A `TOOL_REGISTRY` dictionary maps tool names (strings) to their Python function references, enabling the agent loop to dispatch tool calls by name.

### 4.3 Technology Stack

| Component        | Technology                  | Purpose                                   |
| ---------------- | --------------------------- | ----------------------------------------- |
| LLM Backend      | Google Gemini (`google-genai`) | Multi-turn conversation with function calling |
| Web Framework    | FastAPI                     | HTTP server, SSE streaming, static files  |
| ASGI Server      | Uvicorn                     | Runs the FastAPI application              |
| Streaming        | Server-Sent Events (SSE)    | Real-time response streaming to browser   |
| Frontend         | Vanilla HTML/CSS/JS         | Single-page chat + dashboard UI           |
| Dashboard        | Prefab UI (PrefabApp)       | Renders the CosmoLog dashboard as HTML    |
| NASA Data        | NASA APIs (via `nasa_client.py`) | APOD, Mars Rover, NeoWs                 |
| Journal Storage  | Local JSON file             | `space_journal.json`                      |

---

## 5. Functional Requirements

### 5.1 Agent Loop

The agent implements a multi-turn tool-calling loop:

1. **Receive** user message from the browser.
2. **Send** the conversation history (including the new message) to Gemini.
3. **Parse** the Gemini response:
   - If the response contains **function calls**, dispatch each tool call (see 5.4), collect the results, feed them back to Gemini, and repeat from step 3.
   - If the response contains **text only** (no function calls), stream the text to the browser and end the loop.
4. **Guard** against infinite loops with a maximum iteration limit (default: 10).

The loop must handle the case where Gemini returns multiple function calls in a single response (parallel tool calling). Each tool call is dispatched sequentially, and all results are sent back to Gemini together.

### 5.2 Tool Declarations

The agent must declare the three CosmoLog tools to Gemini as `FunctionDeclaration` objects. The declarations must match the exact parameter names, types, and descriptions from the MCP tool signatures.

#### fetch_space_data

| Parameter    | Type    | Required | Description                                        |
| ------------ | ------- | -------: | -------------------------------------------------- |
| `date`       | string  |       No | Date for APOD lookup (YYYY-MM-DD). Defaults to today. |
| `rover`      | string  |       No | Mars rover name. Defaults to `curiosity`.          |
| `sol`        | integer |       No | Martian sol for rover photos. Defaults to latest.  |
| `photo_count`| integer |       No | Number of rover photos to return. Defaults to 3.   |
| `neo_days`   | integer |       No | Days ahead to check for NEOs. Defaults to 7.       |

#### manage_space_journal

| Parameter    | Type   |    Required | Description                                     |
| ------------ | ------ | ----------: | ----------------------------------------------- |
| `operation`  | string |         Yes | One of `create`, `read`, `update`, or `delete`. |
| `entry_id`   | string | Conditional | Required for `update` and `delete`.             |
| `payload`    | object | Conditional | Required for `create` and `update`.             |
| `tag_filter` | string |          No | Optional tag filter for `read`.                 |

#### show_space_dashboard

| Parameter         | Type   | Required | Description                                           |
| ----------------- | ------ | -------: | ----------------------------------------------------- |
| `space_data`      | object |       No | Data returned from `fetch_space_data`.                |
| `journal_entries` | array  |       No | Entries returned from `manage_space_journal` read.    |
| `tag_filter`      | string |       No | Active tag filter for journal entries.                |

### 5.3 System Prompt

The agent must be initialized with a system prompt that instructs Gemini to:

1. Act as a NASA space exploration assistant named CosmoLog.
2. Use the three available tools to fulfill user requests about space data, journal management, and dashboard rendering.
3. Follow a recommended tool-calling order: fetch data first, then save/manage journal entries, then render the dashboard.
4. Show its reasoning process (thinking steps) before making tool calls.
5. Provide informative, educational responses about NASA data.
6. Always call `show_space_dashboard` at the end of a workflow that involves data fetching or journal changes, passing the most recent data.
7. Handle errors gracefully and explain them to the user.

The system prompt must be defined in a separate module (`agent_prompt.py`) as a string constant for maintainability.

### 5.4 Tool Dispatch

Tool dispatch uses a `TOOL_REGISTRY` dictionary:

```python
TOOL_REGISTRY = {
    "fetch_space_data": fetch_space_data,
    "manage_space_journal": manage_space_journal,
    "show_space_dashboard": show_space_dashboard,
}
```

When the agent loop receives a function call from Gemini:

1. Look up the function name in `TOOL_REGISTRY`.
2. Extract the arguments from the function call.
3. Call the function with the arguments.
4. Serialize the result to a dictionary.

**Special handling for `show_space_dashboard`:**

The `show_space_dashboard` tool returns a `PrefabApp` object, not a plain dictionary. The agent must:

1. Call the tool function to get the `PrefabApp` object.
2. Call `.html()` on the `PrefabApp` to render it as a self-contained HTML string.
3. Send the HTML string to the browser as an SSE `dashboard` event (see 6.2).
4. Return a summary string (not the full HTML) to Gemini as the tool result, so the conversation context is not bloated with HTML markup.

### 5.5 Dashboard Rendering Pipeline

```
show_space_dashboard(space_data, journal_entries, tag_filter)
  --> PrefabApp object
  --> PrefabApp.html()
  --> HTML string
  --> SSE "dashboard" event --> Browser
  --> iframe srcdoc attribute updated
  --> Dashboard visible in right panel
```

The rendered HTML from `PrefabApp.html()` includes all component markup and loads the Prefab renderer (JS/CSS) from CDN. It is injected into an iframe via the `srcdoc` attribute, isolating the dashboard styles from the agent UI styles.

---

## 6. Web Application Requirements

### 6.1 FastAPI Routes

| Method | Path     | Purpose                                      | Response Type          |
| ------ | -------- | -------------------------------------------- | ---------------------- |
| `GET`  | `/`      | Serve the single-page frontend (`index.html`) | HTML (static file)     |
| `POST` | `/chat`  | Accept a user message, run the agent loop, stream results | SSE stream             |
| `POST` | `/reset` | Clear the conversation history                | JSON `{"status": "ok"}` |
| `GET`  | `/health`| Health check endpoint                         | JSON `{"status": "healthy"}` |

#### POST /chat

**Request body:**

```json
{
  "message": "Fetch today's APOD and show it on the dashboard"
}
```

**Response:** An SSE stream (Content-Type: `text/event-stream`) with events described in section 6.2.

#### POST /reset

Clears the in-memory conversation history and returns a confirmation. The next `/chat` request starts a fresh conversation.

### 6.2 SSE Event Types

The agent streams events to the browser as Server-Sent Events. Each event has a `type` field and a `data` field.

| Event Type    | Data Payload                                     | Purpose                                      |
| ------------- | ------------------------------------------------ | -------------------------------------------- |
| `start`       | `{}`                                             | Signals the start of a response stream       |
| `thinking`    | `{"text": "..."}`                                | Agent's reasoning/thinking step              |
| `tool_call`   | `{"name": "...", "args": {...}}`                 | Notification that a tool is being called      |
| `tool_result` | `{"name": "...", "result": {...}}`               | Result returned from a tool call             |
| `dashboard`   | `{"html": "..."}`                                | Rendered Prefab dashboard HTML for iframe     |
| `text`        | `{"text": "..."}`                                | Final text response from the agent           |
| `error`       | `{"message": "..."}`                             | Error message                                |
| `done`        | `{}`                                             | Signals the end of the response stream       |

The frontend must handle each event type appropriately:

- `thinking` and `tool_call` events are displayed as collapsible/expandable steps in the chat.
- `text` events are displayed as the agent's reply message bubble.
- `dashboard` events update the right panel iframe.
- `error` events display an error notification in the chat.

### 6.3 Conversation State

- Conversation history is maintained **in-memory** on the server (a Python list of message dictionaries).
- The application is **single-user** — there is no session management or multi-user support.
- The conversation history is lost when the server restarts.
- The `/reset` endpoint clears the history for a fresh conversation.

---

## 7. Frontend UI Requirements

### 7.1 Layout

The frontend is a single HTML page (`static/index.html`) with a split-pane layout:

```
+------------------------------------------------------+
|  [CosmoLog Logo]   CosmoLog AI Agent    [Reset Chat]  |
+--------------------+---------------------------------+
|                    |                                   |
|   Chat Panel       |   Dashboard Panel                |
|   (~40% width)     |   (~60% width)                   |
|                    |                                   |
|   [Messages]       |   [Prefab Dashboard iframe]      |
|   [Thinking]       |                                   |
|   [Tool Calls]     |                                   |
|                    |                                   |
+--------------------+---------------------------------+
|  [Suggested Prompts]                                   |
|  [Input bar with send button]                         |
+------------------------------------------------------+
```

The layout must be responsive:

- On screens wider than 1024px: side-by-side split pane.
- On narrower screens: stacked layout with chat on top, dashboard below.

### 7.2 Chat Panel

The chat panel displays the conversation between the user and the agent.

**Message types:**

| Element           | Display Style                                       |
| ----------------- | --------------------------------------------------- |
| User message      | Right-aligned bubble with user avatar/icon           |
| Agent text        | Left-aligned bubble with CosmoLog avatar/icon        |
| Thinking step     | Collapsible section with a "thinking" icon, muted text, italic style |
| Tool call         | Collapsible card showing tool name and arguments     |
| Tool result       | Nested inside the tool call card, collapsed by default |
| Error             | Left-aligned bubble with error styling (red accent)  |

**Input bar:**

- Text input field with placeholder text (e.g., "Ask about space...").
- Send button (paper plane icon).
- Enter key submits the message.
- Input is disabled while the agent is processing a response.

**Suggested prompts:**

- Displayed above the input bar when the conversation is empty.
- Clicking a suggested prompt fills and submits the input.
- Hidden after the first message is sent.

### 7.3 Dashboard Panel

The dashboard panel has three states:

1. **Placeholder (initial):** A space-themed placeholder with a message like "Ask the agent to fetch data and show the dashboard" and a subtle animation.
2. **Loading:** A loading indicator shown while `show_space_dashboard` is executing.
3. **Dashboard (active):** An iframe with `srcdoc` set to the Prefab HTML received from the `dashboard` SSE event.

The iframe must:

- Fill the available width and height of the dashboard panel.
- Have no visible border.
- Allow scrolling within the iframe for long dashboard content.

### 7.4 Visual Design

The UI uses a dark space theme with the following design system:

#### Colors

| Token             | Value                         | Usage                             |
| ----------------- | ----------------------------- | --------------------------------- |
| Background        | `#0a0a1a`                     | Page background                   |
| Surface           | `#0f0f2e`                     | Card/panel backgrounds            |
| Surface hover     | `#1a1a3e`                     | Hover states                      |
| Cosmic blue       | `#4f8cff`                     | Primary accent, links, buttons    |
| Nebula purple     | `#a855f7`                     | Secondary accent, gradients       |
| Star white        | `#e2e8f0`                     | Primary text                      |
| Muted             | `#64748b`                     | Secondary text, timestamps        |
| Success           | `#22c55e`                     | Success states, safe badges       |
| Danger            | `#ef4444`                     | Error states, hazardous badges    |
| Border            | `rgba(79, 140, 255, 0.15)`    | Subtle borders on cards/panels    |

#### Typography

| Font              | Usage                          |
| ----------------- | ------------------------------ |
| Inter             | Body text, UI elements         |
| JetBrains Mono    | Code blocks, tool arguments, JSON data |

Both fonts loaded from Google Fonts.

#### Glass Morphism

Cards and panels use a glass morphism effect:

- `background: rgba(15, 15, 46, 0.8)`
- `backdrop-filter: blur(12px)`
- `border: 1px solid rgba(79, 140, 255, 0.15)`
- `border-radius: 12px`

#### Animations

- **Message appear:** Fade-in + slide-up when new messages are added to the chat.
- **Thinking pulse:** A subtle pulsing animation on thinking step indicators.
- **Dashboard panel:** Smooth fade transition when dashboard content updates.
- **Stars background:** A subtle CSS starfield or particle effect on the background (performant, CSS-only preferred).
- **Typing indicator:** Three animated dots shown while waiting for agent response.

### 7.5 Suggested Demo Prompts

Four pre-built prompt buttons displayed when the chat is empty:

1. **"Fetch today's APOD and show it on the dashboard"** — Minimal demo of fetch + dashboard.
2. **"Fetch NASA data, save the APOD to my journal, and show the dashboard"** — Full three-tool flow.
3. **"Show me what's in my space journal"** — Journal read + dashboard.
4. **"Fetch Mars rover photos and near-Earth objects, save them all, and display everything"** — Comprehensive demo.

---

## 8. Agent Behavior Specifications

### 8.1 Multi-Turn Reasoning

The agent must demonstrate visible multi-turn reasoning:

1. When a user request requires multiple tools, the agent should call them in a logical order and explain its reasoning.
2. Each tool call should be preceded by a thinking step that the user can see.
3. The agent must pass data between tool calls — e.g., using the result of `fetch_space_data` as input to `manage_space_journal` for creating entries, and then passing both to `show_space_dashboard`.

### 8.2 Thinking Visibility

The agent's internal reasoning (thinking/planning steps) must be streamed to the browser as `thinking` SSE events. This allows the user (and evaluator) to see how the agent decides which tools to call and in what order.

### 8.3 Error Handling

| Error Scenario              | Agent Behavior                                                  |
| --------------------------- | --------------------------------------------------------------- |
| Gemini API error            | Stream an `error` SSE event with a user-friendly message. Do not crash. |
| Gemini rate limit           | Stream an `error` event asking the user to wait and retry.      |
| Tool function raises        | Catch the exception, send a `tool_result` with the error, let Gemini decide how to respond. |
| Tool returns error status   | Pass the error result to Gemini so it can explain the failure to the user. |
| Max iterations exceeded     | Stop the loop, stream a `text` event explaining that the agent reached its reasoning limit. |
| Invalid tool name from Gemini | Log a warning, return an error result to Gemini indicating the tool does not exist. |

### 8.4 Dashboard Trigger Rules

The agent should call `show_space_dashboard`:

1. At the end of any workflow that fetches data or modifies journal entries.
2. When the user explicitly asks to "show the dashboard" or "display the data."
3. With the most recent available data — combining fresh `fetch_space_data` results and current journal entries.

The system prompt instructs this behavior, but Gemini ultimately decides when to call tools. The agent must not force tool calls outside of the LLM's decision.

### 8.5 Tool Argument Construction

Gemini constructs tool arguments based on the conversation context. The agent must:

1. Pass Gemini's arguments to the tool functions, coercing types to match Python signatures where needed (e.g., float → int for `photo_count`).
2. Handle cases where Gemini omits optional parameters (Python defaults apply).

---

## 9. End-to-End User Flows

### 9.1 Primary Demo Flow

**User prompt:**

```text
Fetch today's NASA data, save the APOD to my journal with the tag "demo," and show everything on the dashboard.
```

**Expected agent behavior:**

1. Stream a `thinking` event: "I'll fetch NASA data first, then save the APOD, read the journal, and display the dashboard."
2. Call `fetch_space_data` with default parameters.
3. Stream `tool_call` and `tool_result` events for the fetch.
4. Call `manage_space_journal` with `operation: "create"` and a payload constructed from the APOD data.
5. Stream `tool_call` and `tool_result` events for the create.
6. Call `manage_space_journal` with `operation: "read"` to get all journal entries.
7. Stream `tool_call` and `tool_result` events for the read.
8. Call `show_space_dashboard` with the fetched space data and journal entries.
9. Stream `tool_call` event, then `dashboard` event with the rendered HTML.
10. Stream a `text` event summarizing what was done.
11. Stream a `done` event.

**Expected UI state:**

- Chat panel shows the full conversation with expandable thinking/tool steps.
- Dashboard panel shows the live Prefab dashboard with APOD hero, rover photos, NEO table, and journal entries.

### 9.2 CRUD Demo Flow

**User prompt (following the primary flow):**

```text
Update the notes on the APOD entry to "Favorite image of the week," delete one rover photo from the journal, then refresh the dashboard.
```

**Expected agent behavior:**

1. Call `manage_space_journal` with `operation: "read"` to find the entries.
2. Call `manage_space_journal` with `operation: "update"` on the APOD entry.
3. Call `manage_space_journal` with `operation: "delete"` on a rover photo entry.
4. Call `manage_space_journal` with `operation: "read"` to get updated entries.
5. Call `show_space_dashboard` with updated data.
6. Stream summary text.

### 9.3 Conversation Continuity

The agent maintains conversation history across multiple prompts within a session. A follow-up prompt like "Now fetch data for yesterday's APOD" should work without the user re-explaining context.

The agent should remember previously fetched data and journal entries from earlier in the conversation and use them when appropriate (e.g., when rendering a dashboard without a fresh fetch).

---

## 10. Configuration

### 10.1 Environment Variables

| Variable        | Required | Default         | Description                              |
| --------------- | -------: | --------------- | ---------------------------------------- |
| `GEMINI_API_KEY`| Yes      | —               | Google Gemini API key                    |
| `GEMINI_MODEL`  | No       | `gemini-2.5-flash` | Gemini model name                       |
| `NASA_API_KEY`  | No       | `DEMO_KEY`      | NASA API key (shared with MCP server)    |
| `HOST`          | No       | `0.0.0.0`       | FastAPI server host                      |
| `PORT`          | No       | `8000`          | FastAPI server port                      |

### 10.2 Environment File

All variables are loaded from a `.env` file in the project root using `python-dotenv`, consistent with the existing MCP server configuration.

---

## 11. Project Structure

```
CosmoLog/
  # Existing files (unchanged)
  mcp_server.py          # MCP server with tool definitions
  models.py              # Pydantic data models
  nasa_client.py         # NASA API client with TTL cache
  journal.py             # Journal CRUD operations
  dashboard.py           # Prefab dashboard builder

  # New files
  agent.py               # FastAPI server + Gemini agent loop + SSE streaming
  agent_prompt.py         # System prompt constant

  static/
    index.html           # Single-page frontend (chat + dashboard UI)

  # Existing (unchanged)
  docs/
  tests/
  space_journal.json     # Local journal data (gitignored)
  pyproject.toml
  .env
```

### 11.1 New File Responsibilities

| File              | Responsibility                                                       |
| ----------------- | -------------------------------------------------------------------- |
| `agent.py`        | FastAPI app, `/chat` SSE endpoint, `/reset` endpoint, Gemini client initialization, agent loop, tool dispatch, dashboard HTML extraction |
| `agent_prompt.py` | System prompt string constant for the Gemini agent                   |
| `static/index.html` | Complete single-page frontend: HTML structure, CSS styles (space theme), JavaScript (SSE handling, chat UI, dashboard iframe management) |

### 11.2 New Dependencies

| Package          | Purpose                        |
| ---------------- | ------------------------------ |
| `google-genai`   | Google Gemini API client       |
| `fastapi`        | Web framework                  |
| `uvicorn`        | ASGI server                    |
| `sse-starlette`  | SSE response support for FastAPI |

These are added to `pyproject.toml` via `uv add`.

---

## 12. Non-Functional Requirements

### 12.1 Performance

- The agent loop should complete a typical three-tool workflow (fetch, save, dashboard) within 15 seconds under normal conditions.
- SSE events should be streamed as they become available, not batched.
- The Prefab dashboard HTML should render in the iframe within 1 second of receipt.

### 12.2 Reliability

- The agent must not crash on Gemini API errors, tool failures, or malformed responses.
- All errors must be reported to the user via the SSE stream, not silently swallowed.
- The NASA API client's TTL cache (from the existing MCP server) helps ensure demo stability by avoiding redundant API calls.

### 12.3 Demo Stability

- The application must work reliably during a live demo with a valid `GEMINI_API_KEY` and `NASA_API_KEY`.
- Cached NASA responses reduce the risk of API rate-limit failures during repeated demo runs.
- The in-memory conversation state ensures fast response times (no database required).

### 12.4 Security

- API keys must not be exposed to the browser or included in SSE events.
- The frontend must not make direct calls to NASA APIs or Gemini — all API access goes through the FastAPI backend.
- The dashboard iframe uses `srcdoc` (not `src` with a URL), so no additional endpoints are exposed.
- User input is passed to Gemini as conversation content, not interpolated into code or commands.

---

## 13. Acceptance Criteria

### 13.1 Agent Loop

The application is accepted if:

- The agent receives a user message and sends it to Gemini.
- Gemini responds with function calls, and the agent dispatches them correctly.
- The agent feeds tool results back to Gemini and continues until a text-only response is produced.
- The full loop is streamed to the browser as SSE events.

### 13.2 MCP Tool Usage

The application is accepted if:

- The agent successfully calls all three MCP tools (`fetch_space_data`, `manage_space_journal`, `show_space_dashboard`) during a demo workflow.
- Tool arguments match the function signatures defined in `mcp_server.py`.
- Tool results are correctly serialized and passed back to Gemini.

### 13.3 Dashboard Rendering

The application is accepted if:

- `show_space_dashboard` returns a `PrefabApp` object.
- The `PrefabApp.html()` method produces a self-contained HTML string.
- The HTML is sent to the browser as an SSE `dashboard` event.
- The browser displays the dashboard in an iframe in the right panel.
- The dashboard shows APOD, rover photos, NEO table, and journal entries.

### 13.4 Streaming

The application is accepted if:

- Thinking steps, tool calls, tool results, and text responses are streamed incrementally.
- The user sees progressive updates in the chat panel as the agent works.
- The dashboard appears in the right panel as soon as it is rendered.

### 13.5 UI Quality

The application is accepted if:

- The UI uses a dark space theme with the specified color palette.
- Glass morphism effects are visible on cards and panels.
- The layout is split-pane on desktop and stacks on mobile.
- Suggested prompts are displayed and functional.
- Chat messages are styled with clear user/agent distinction.
- Thinking and tool call steps are collapsible.

### 13.6 Error Resilience

The application is accepted if:

- A Gemini API error does not crash the server.
- A tool failure is reported to the user and the agent continues gracefully.
- The max iteration guard prevents infinite loops.

---

## 14. Recommended Demo Script

### Step 1: Start the Agent Server

```bash
uv run python agent.py
```

Open `http://localhost:8000` in a browser.

### Step 2: Observe the Initial UI

- The chat panel is empty with four suggested prompt buttons visible.
- The dashboard panel shows a space-themed placeholder.

### Step 3: Run the Primary Demo

Click the suggested prompt:

```text
Fetch NASA data, save the APOD to my journal, and show the dashboard
```

**Observe:**

- Thinking steps appear in the chat as collapsible items.
- Tool calls appear with their arguments (fetch, create, read, dashboard).
- The dashboard panel transitions from placeholder to loading to the live Prefab dashboard.
- The agent's summary text appears at the end.

### Step 4: Demonstrate CRUD

Type:

```text
Update the notes on the APOD entry to "Favorite image of the week," delete one rover photo, and refresh the dashboard.
```

**Observe:**

- The agent calls update, delete, read, and dashboard tools.
- The dashboard refreshes with the updated journal state.

### Step 5: Demonstrate Continuity

Type:

```text
What data did we fetch earlier?
```

**Observe:**

- The agent recalls the earlier conversation context and summarizes the data without re-fetching.

### Step 6: Reset and Start Fresh

Click the "Reset Chat" button and verify the conversation is cleared and suggested prompts reappear.

---

## 15. Risks and Mitigations

| Risk                                    | Impact                                       | Mitigation                                                         |
| --------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------ |
| Gemini API rate limit                   | Agent cannot respond                         | Use `gemini-2.5-flash` (generous rate limits). Show a retry message. |
| Gemini returns invalid tool name        | Tool dispatch fails                          | Return an error result to Gemini; it will self-correct.            |
| Gemini returns malformed arguments      | Tool call raises an exception                | Catch exceptions and send error result back to Gemini.             |
| Large dashboard HTML in SSE             | Slow transmission, browser lag               | PrefabApp HTML is typically 20-50KB, well within SSE limits.       |
| Conversation history grows too large    | Gemini context window exceeded               | Limit history to last N turns or implement a sliding window.       |
| NASA API rate limit (DEMO_KEY)          | `fetch_space_data` returns errors            | Use a personal API key. Existing TTL cache reduces repeat calls.   |
| Browser does not support SSE            | Chat does not update                         | Modern browsers support SSE consumption via `fetch()` with streamed responses. No polyfill needed. |
| Concurrent users on single-user server  | Conversation state conflicts                 | Document as single-user. Not a concern for demo purposes.          |

---