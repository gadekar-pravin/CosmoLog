# CosmoLog

NASA Space Mission Journal Dashboard — an MCP application built with FastMCP and Prefab UI, with a Gemini-powered agent web app featuring a mission console chat interface and SSE streaming.

CosmoLog fetches live NASA data (Astronomy Picture of the Day, Mars rover photos, near-Earth objects), stores selections in a local journal, and renders an interactive dashboard — all exposed as MCP tools for use with AI assistants. The agent web app layers a conversational Gemini interface over these tools with real-time streaming and a themed mission console UI.

## Demo

[![CosmoLog Demo](https://img.youtube.com/vi/XKHB9NBlpFE/maxresdefault.jpg)](https://youtu.be/XKHB9NBlpFE)

▶️ [Watch the demo on YouTube](https://youtu.be/XKHB9NBlpFE)

## Features

- **Astronomy Picture of the Day** — image and video (iframe) support
- **Mars rover photo grid** — Curiosity rover, configurable sol and photo count
- **Near-Earth object tracking** — hazard status badges, distance and velocity data, configurable count cap
- **Local journal** — full CRUD with tag filtering, persisted to JSON
- **Interactive dashboard** — Prefab UI with stats, cards, tables, and toast notifications
- **API caching** — 5-minute in-memory TTL cache for NASA rate-limit protection
- **Gemini AI agent** — conversational interface powered by Vertex AI, with tool-calling and reasoning
- **Mission console UI** — SSE streaming chat interface with live dashboard panel
- **Structured logging** — centralized logging with correlation IDs for request tracing

## Project Structure

```
CosmoLog/
├── mcp_server.py        # FastMCP server, tool definitions, entry point
├── nasa_client.py       # httpx-based NASA API client (APOD, Mars Rover, NeoWs)
├── models.py            # Pydantic v2 data models
├── journal.py           # Journal CRUD against space_journal.json
├── dashboard.py         # Prefab UI dashboard builder
├── agent.py             # FastAPI app, Gemini client, SSE streaming agent loop
├── agent_prompt.py      # Gemini system prompt
├── logging_config.py    # Centralized logging with correlation IDs
├── static/
│   └── index.html       # Mission console browser UI (chat + dashboard iframe)
├── pyproject.toml       # Project config, dependencies, ruff settings
├── tests/
│   ├── conftest.py      # Shared fixtures (sample API responses, tmp_journal)
│   ├── test_models.py
│   ├── test_journal.py
│   ├── test_nasa_client.py
│   ├── test_dashboard.py
│   ├── test_mcp_server.py
│   ├── test_agent.py
│   ├── test_agent_server.py
│   ├── test_agent_prompt.py
│   └── test_logging_config.py
└── docs/
    ├── agent-functional-specification.md
    ├── agent-implementation-plan.md
    └── mcp/
        ├── functional-specification.md
        ├── technical-specification.md
        └── phase-1-models.md ... phase-5-mcp-server.md
```

## Quick Start

```bash
git clone <repo-url>
cd CosmoLog
```

Set up your environment and start the server:

```bash
cp .env.example .env   # optionally replace DEMO_KEY with your own key
uv sync
```

**MCP server** (for use with AI assistants via MCP protocol):

```bash
uv run python mcp_server.py
```

**Agent web app** (mission console UI with Gemini):

```bash
# Requires Google Cloud auth: gcloud auth application-default login
uv run python agent.py
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `NASA_API_KEY` | `DEMO_KEY` | NASA API key. `DEMO_KEY` is rate-limited to 30 requests/hour. Get a free key at https://api.nasa.gov |
| `GOOGLE_CLOUD_PROJECT` | — | Google Cloud project ID, required for Vertex AI Gemini access |
| `GOOGLE_CLOUD_LOCATION` | `global` | GCP region for Vertex AI endpoint |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Gemini model name |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

## MCP Tools

### `fetch_space_data`

Fetch live NASA data: APOD, Mars rover photos, and near-Earth objects.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `date` | `str \| None` | today | APOD date (YYYY-MM-DD) |
| `rover` | `str` | `"curiosity"` | Mars rover name |
| `sol` | `int \| None` | latest | Martian sol for rover photos |
| `photo_count` | `int` | `3` | Number of rover photos to return |
| `neo_days` | `int` | `7` | Days ahead to check for NEOs |
| `neo_count` | `int` | `10` | Maximum number of NEOs to return |

### `manage_space_journal`

CRUD operations on the local space journal.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `operation` | `str` | — | One of `create`, `read`, `update`, `delete` |
| `entry_id` | `str \| None` | `None` | Required for `update` and `delete` |
| `payload` | `dict \| None` | `None` | Entry data for `create` and `update` |
| `tag_filter` | `str \| None` | `None` | Filter entries by tag during `read` |

### `show_space_dashboard`

Render the CosmoLog Prefab UI dashboard.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `space_data` | `dict \| None` | `None` | Data from `fetch_space_data` |
| `journal_entries` | `list[dict] \| None` | `None` | Entries from `manage_space_journal` read |
| `tag_filter` | `str \| None` | `None` | Active tag filter |

## Development

Requires **Python 3.12+** and **uv**.

```bash
uv sync                        # Install dependencies
uv run pytest                  # Run tests
uv run python mcp_server.py    # Start MCP server
uv run python agent.py         # Start agent web app
uv run ruff check .            # Lint
uv run ruff format .           # Format
```

Test stack: pytest, pytest-asyncio, respx (httpx mocking). Tests never hit real APIs.

## Tech Stack

- [FastMCP](https://github.com/jlowin/fastmcp) — MCP server framework
- [Prefab UI](https://github.com/prefab-cloud/prefab-ui) — Dashboard component library
- [httpx](https://www.python-httpx.org/) — Async-capable HTTP client
- [Pydantic v2](https://docs.pydantic.dev/) — Data validation and models
- [python-dotenv](https://github.com/theskumar/python-dotenv) — Environment variable loading
- [google-genai](https://github.com/googleapis/python-genai) — Gemini SDK (Vertex AI)
- [FastAPI](https://fastapi.tiangolo.com/) — Agent web server
- [uvicorn](https://www.uvicorn.org/) — ASGI server
- [sse-starlette](https://github.com/sysid/sse-starlette) — Server-Sent Events for streaming
- [Ruff](https://docs.astral.sh/ruff/) — Linting and formatting
