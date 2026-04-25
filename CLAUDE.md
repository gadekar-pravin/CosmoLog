# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

CosmoLog is a NASA Space Mission Journal Dashboard — an MCP application with 3 tools (`fetch_space_data`, `manage_space_journal`, `show_space_dashboard`) built with FastMCP and Prefab UI.

## Architecture

```
mcp_server.py    — FastMCP server, tool definitions, entry point (`cosmolog` script)
nasa_client.py   — httpx-based NASA API client (APOD, Mars Rover, NeoWs) with TTL cache
journal.py       — Journal CRUD against space_journal.json (gitignored)
models.py        — Pydantic v2 models: SpaceData, APODData, RoverPhoto, NearEarthObject, JournalEntry
dashboard.py     — Prefab UI dashboard builder (imported lazily from show_space_dashboard)
```

- Transport: `mcp.run(transport="http")`
- Entry point script: `cosmolog` (defined in `[project.scripts]`)
- Journal and dashboard modules are lazily imported inside tool functions

## Agent Architecture

The planned Gemini agent web app layers a conversational UI over the existing MCP
tools without changing the MCP server contract.

```
agent.py          — FastAPI app, Gemini client, tool dispatch, SSE agent loop
agent_prompt.py   — Gemini system prompt (`SYSTEM_PROMPT`)
static/index.html — browser chat UI and live dashboard iframe
```

- MCP tools are imported in-process from `mcp_server.py`, not called over MCP transport
- `TOOL_REGISTRY` maps Gemini function names to `fetch_space_data`, `manage_space_journal`, and `show_space_dashboard`
- `agent_loop()` is an async generator that yields SSE event dictionaries while Gemini reasons, calls tools, and produces text
- SSE event types: `start`, `thinking`, `tool_call`, `tool_result`, `dashboard`, `text`, `error`, `done`
- `show_space_dashboard` returns a `PrefabApp`; agent dispatch must call `.html()` and stream the HTML as a `dashboard` event
- Dashboard HTML is sent to the browser iframe, while Gemini receives only a short summary to avoid bloating conversation context

## Prefab UI Reference

The Prefab framework source is at `../prefab/`. When unsure about a component API, check the actual source:
- Components: `../prefab/src/prefab_ui/components/`
- Actions: `../prefab/src/prefab_ui/actions/`
- Rx values: `../prefab/src/prefab_ui/rx/__init__.py`

## Key Prefab Patterns

These are easy to get wrong — follow exactly:
- `on_success=SetState("key", RESULT)` — there is NO `result_key` parameter on `CallTool`
- `RESULT` is `Rx("$result")`, `ERROR` is `Rx("$error")` from `prefab_ui.rx`
- `CallTool` accepts `on_success` and `on_error` as keyword arguments, not positional
- Template expressions use `{{ }}` syntax for reactive state
- `ShowToast(message, variant=...)` — variant is a keyword arg
- Use `Embed` for video APODs (iframe), not `Image` or `Video`
- Use manual `Table`/`TableRow`/`TableCell` for NEO table — `DataTable` cannot render `Badge` in cells
- `SendMessage(text)` sends a chat message to the LLM — used for edit and refresh buttons

## Commands

```bash
uv sync                        # install deps
uv run pytest                  # run tests
uv run python mcp_server.py    # start MCP server
uv run python agent.py         # start agent web app
uv run ruff check .            # lint
uv run ruff format .           # format
```

Always use `uv`, never `pip`.

## Testing

- 5 test files in `tests/`: `test_models`, `test_journal`, `test_nasa_client`, `test_dashboard`, `test_mcp_server`
- Shared fixtures in `tests/conftest.py` (sample API responses, `tmp_journal`, `sample_journal_entry`)
- `respx` mocks httpx requests in NASA client tests — never hit real APIs
- `tmp_path` + `monkeypatch` for journal tests (monkeypatch `journal.JOURNAL_PATH`)
- `pytest-asyncio` for MCP tool registration tests (`await mcp.list_tools()`)
- Dashboard tests verify PrefabApp structure without running the server

## Code Style

- Ruff handles formatting and linting (config in pyproject.toml)
- Python 3.12+ — use `X | Y` union syntax, not `Union[X, Y]`
- Pydantic v2 `BaseModel` for all data models

## Git

- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`

## NASA API

- `DEMO_KEY` is rate-limited to 30 req/hr — the `NASAClient` uses a 5-minute in-memory cache
- The client is module-level in `mcp_server.py` (not per-call) so the cache persists
- `.env` file loaded via `python-dotenv` for `NASA_API_KEY`

## Docs

- `docs/` contains functional spec, technical spec, and per-phase implementation plans (phases 1–5)
