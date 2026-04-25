---
name: verify
description: Run linting and tests to verify the codebase is correct. Use after making changes or before committing.
---

Run the following commands in sequence. Stop at the first failure and report what went wrong.

1. **Lint check**: `uv run ruff check .`
2. **Format check**: `uv run ruff format --check .`
3. **Tests**: `uv run pytest -x`

Report results clearly: what passed, what failed, and any fixes needed.
