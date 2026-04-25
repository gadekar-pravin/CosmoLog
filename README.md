# CosmoLog

NASA Space Mission Journal Dashboard — an MCP application built with FastMCP and Prefab UI.

CosmoLog fetches live NASA data (Astronomy Picture of the Day, Mars rover photos, near-Earth objects), stores selections in a local journal, and renders an interactive dashboard — all exposed as MCP tools for use with AI assistants.

## Features

- **Astronomy Picture of the Day** — image and video (iframe) support
- **Mars rover photo grid** — Curiosity rover, configurable sol and photo count
- **Near-Earth object tracking** — hazard status badges, distance and velocity data
- **Local journal** — full CRUD with tag filtering, persisted to JSON
- **Interactive dashboard** — Prefab UI with stats, cards, tables, and toast notifications
- **API caching** — 5-minute in-memory TTL cache for NASA rate-limit protection

## Project Structure

```
CosmoLog/
├── mcp_server.py        # FastMCP server, tool definitions, entry point
├── nasa_client.py       # httpx-based NASA API client (APOD, Mars Rover, NeoWs)
├── models.py            # Pydantic v2 data models
├── journal.py           # Journal CRUD against space_journal.json
├── dashboard.py         # Prefab UI dashboard builder
├── pyproject.toml       # Project config, dependencies, ruff settings
├── tests/
│   ├── conftest.py      # Shared fixtures (sample API responses, tmp_journal)
│   ├── test_models.py
│   ├── test_journal.py
│   ├── test_nasa_client.py
│   ├── test_dashboard.py
│   └── test_mcp_server.py
└── docs/
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
uv run python mcp_server.py
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `NASA_API_KEY` | `DEMO_KEY` | NASA API key. `DEMO_KEY` is rate-limited to 30 requests/hour. Get a free key at https://api.nasa.gov |

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
uv sync                  # Install dependencies
uv run pytest            # Run tests
uv run ruff check .      # Lint
uv run ruff format .     # Format
```

Test stack: pytest, pytest-asyncio, respx (httpx mocking). Tests never hit real APIs.

## Tech Stack

- [FastMCP](https://github.com/jlowin/fastmcp) — MCP server framework
- [Prefab UI](https://github.com/prefab-cloud/prefab-ui) — Dashboard component library
- [httpx](https://www.python-httpx.org/) — Async-capable HTTP client
- [Pydantic v2](https://docs.pydantic.dev/) — Data validation and models
- [python-dotenv](https://github.com/theskumar/python-dotenv) — Environment variable loading
- [Ruff](https://docs.astral.sh/ruff/) — Linting and formatting
