# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

CosmoLog is a NASA Space Mission Journal Dashboard — an MCP application with 3 tools (`fetch_space_data`, `manage_space_journal`, `show_space_dashboard`) built with FastMCP and Prefab UI.

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

## Commands

```bash
uv sync                        # install deps
uv run pytest                  # run tests
uv run python mcp_server.py    # start MCP server
uv run ruff check .            # lint
uv run ruff format .           # format
```

Always use `uv`, never `pip`.

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
