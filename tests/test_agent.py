from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import types

import agent


@pytest.fixture(autouse=True)
def _clear_fetch_cache():
    agent._last_fetch_result = None
    yield
    agent._last_fetch_result = None


def _response(*parts: types.Part) -> Any:
    return SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(parts=list(parts)),
            )
        ]
    )


def _text_part(text: str) -> types.Part:
    return types.Part.from_text(text=text)


def _function_part(name: str, args: dict[str, Any] | None = None) -> types.Part:
    return types.Part(function_call=types.FunctionCall(name=name, args=args or {}))


async def _collect_events(message: str = "hello") -> list[dict[str, Any]]:
    history: list[types.Content] = []
    return [event async for event in agent.agent_loop(message, history)]


class FakeModels:
    def __init__(self, responses: list[Any] | None = None, error: Exception | None = None):
        self.responses = responses or []
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]


def _fake_client(models: FakeModels) -> Any:
    return SimpleNamespace(aio=SimpleNamespace(models=models))


def test_tool_registry_has_three_tools():
    assert len(agent.TOOL_REGISTRY) == 3


def test_tool_registry_keys():
    assert set(agent.TOOL_REGISTRY) == {
        "fetch_space_data",
        "manage_space_journal",
        "show_space_dashboard",
    }


def test_tool_registry_values_callable():
    assert all(callable(tool) for tool in agent.TOOL_REGISTRY.values())


def test_function_declarations_count():
    assert len(agent.FUNCTION_DECLARATIONS) == 3


def test_function_declaration_names():
    declaration_names = {declaration.name for declaration in agent.FUNCTION_DECLARATIONS}

    assert declaration_names == set(agent.TOOL_REGISTRY)


def test_dispatch_tool_fetch(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_fetch_space_data(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "success", "apod": {"title": "Test Nebula"}}

    monkeypatch.setitem(agent.TOOL_REGISTRY, "fetch_space_data", fake_fetch_space_data)

    result, dashboard_html = agent._dispatch_tool("fetch_space_data", {"photo_count": 2})

    assert captured == {"photo_count": 2}
    assert result == {"status": "success", "apod": {"title": "Test Nebula"}}
    assert dashboard_html is None


def test_dispatch_tool_dashboard_returns_html(monkeypatch):
    class FakeDashboard:
        def html(self) -> str:
            return "<html>dashboard</html>"

    def fake_show_space_dashboard(**kwargs: Any) -> FakeDashboard:
        assert kwargs == {"space_data": {"apod": {"title": "Test"}}}
        return FakeDashboard()

    monkeypatch.setitem(agent.TOOL_REGISTRY, "show_space_dashboard", fake_show_space_dashboard)

    result, dashboard_html = agent._dispatch_tool(
        "show_space_dashboard",
        {"space_data": {"apod": {"title": "Test"}}},
    )

    assert result == "Dashboard rendered successfully"
    assert dashboard_html == "<html>dashboard</html>"


def test_dispatch_tool_unknown_name():
    result, dashboard_html = agent._dispatch_tool("nonexistent", {})

    assert result["status"] == "error"
    assert "Unknown tool" in result["message"]
    assert dashboard_html is None


def test_dispatch_tool_exception_to_error(monkeypatch):
    def broken_tool(**kwargs: Any) -> dict[str, Any]:
        raise ValueError("tool exploded")

    monkeypatch.setitem(agent.TOOL_REGISTRY, "fetch_space_data", broken_tool)

    result, dashboard_html = agent._dispatch_tool("fetch_space_data", {})

    assert result == {"status": "error", "message": "tool exploded"}
    assert dashboard_html is None


def test_dispatch_tool_float_to_int_coercion(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_fetch_space_data(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "success"}

    monkeypatch.setitem(agent.TOOL_REGISTRY, "fetch_space_data", fake_fetch_space_data)

    result, _ = agent._dispatch_tool(
        "fetch_space_data",
        {"sol": 100.0, "photo_count": 3.0, "neo_days": 7.0, "neo_count": 10.0},
    )

    assert result == {"status": "success"}
    assert captured == {"sol": 100, "photo_count": 3, "neo_days": 7, "neo_count": 10}
    assert all(isinstance(value, int) for value in captured.values())


@pytest.mark.asyncio
async def test_agent_loop_text_only(monkeypatch):
    models = FakeModels([_response(_text_part("Here is a space fact."))])
    monkeypatch.setattr(agent, "_get_gemini_client", lambda: _fake_client(models))

    events = await _collect_events()

    assert [event["type"] for event in events] == ["start", "text", "done"]
    assert events[1]["data"] == {"text": "Here is a space fact."}
    assert models.calls[0]["model"] == agent.MODEL
    assert models.calls[0]["config"].tools == [agent.GEMINI_TOOL]


@pytest.mark.asyncio
async def test_agent_loop_with_tool_call(monkeypatch):
    models = FakeModels(
        [
            _response(
                _text_part("I'll fetch the latest NASA data."),
                _function_part("fetch_space_data", {"photo_count": 1}),
            ),
            _response(_text_part("Fetched the data.")),
        ]
    )
    monkeypatch.setattr(agent, "_get_gemini_client", lambda: _fake_client(models))
    monkeypatch.setitem(
        agent.TOOL_REGISTRY,
        "fetch_space_data",
        lambda **kwargs: {"status": "success", "received": kwargs},
    )

    events = await _collect_events("fetch data")

    assert [event["type"] for event in events] == [
        "start",
        "thinking",
        "tool_call",
        "tool_result",
        "text",
        "done",
    ]
    assert events[1]["data"] == {"text": "I'll fetch the latest NASA data."}
    assert events[2]["data"] == {"name": "fetch_space_data", "args": {"photo_count": 1}}
    assert events[3]["data"]["result"] == {
        "status": "success",
        "received": {"photo_count": 1},
    }
    assert events[4]["data"] == {"text": "Fetched the data."}
    assert len(models.calls) == 2


@pytest.mark.asyncio
async def test_agent_loop_gemini_error(monkeypatch):
    models = FakeModels(error=RuntimeError("Gemini unavailable"))
    monkeypatch.setattr(agent, "_get_gemini_client", lambda: _fake_client(models))

    events = await _collect_events()

    assert [event["type"] for event in events] == ["start", "error", "done"]
    assert events[1]["data"] == {"message": "Gemini unavailable"}


@pytest.mark.asyncio
async def test_agent_loop_config_error(monkeypatch):
    def raise_config_error() -> Any:
        raise RuntimeError("Missing GOOGLE_CLOUD_PROJECT")

    monkeypatch.setattr(agent, "_get_gemini_client", raise_config_error)

    events = await _collect_events()

    assert [event["type"] for event in events] == ["start", "error", "done"]
    assert events[1]["data"] == {"message": "Missing GOOGLE_CLOUD_PROJECT"}


@pytest.mark.asyncio
async def test_agent_loop_multiple_tool_calls(monkeypatch):
    models = FakeModels(
        [
            _response(
                _text_part("I'll fetch data and read the journal."),
                _function_part("fetch_space_data", {"neo_days": 2}),
                _function_part("manage_space_journal", {"operation": "read"}),
            ),
            _response(_text_part("Both tool calls completed.")),
        ]
    )
    monkeypatch.setattr(agent, "_get_gemini_client", lambda: _fake_client(models))
    monkeypatch.setitem(
        agent.TOOL_REGISTRY,
        "fetch_space_data",
        lambda **kwargs: {"space": kwargs},
    )
    monkeypatch.setitem(
        agent.TOOL_REGISTRY,
        "manage_space_journal",
        lambda **kwargs: {"journal": kwargs},
    )

    events = await _collect_events("fetch and read")

    assert [event["type"] for event in events] == [
        "start",
        "thinking",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "text",
        "done",
    ]
    assert events[2]["data"]["name"] == "fetch_space_data"
    assert events[4]["data"]["name"] == "manage_space_journal"
    function_response_turn = models.calls[1]["contents"][-1]
    assert len(function_response_turn.parts) == 2


@pytest.mark.asyncio
async def test_agent_loop_journal_read_shortcut_empty_journal(monkeypatch):
    def fail_get_client() -> Any:
        raise AssertionError("Gemini should not be called for journal-only reads")

    def fail_fetch(**kwargs: Any) -> dict[str, Any]:
        raise AssertionError("fetch_space_data should not be called")

    class FakeDashboard:
        def html(self) -> str:
            return "<html>journal dashboard</html>"

    dashboard_args: dict[str, Any] = {}

    def fake_dashboard(**kwargs: Any) -> FakeDashboard:
        dashboard_args.update(kwargs)
        return FakeDashboard()

    monkeypatch.setattr(agent, "_get_gemini_client", fail_get_client)
    monkeypatch.setitem(agent.TOOL_REGISTRY, "fetch_space_data", fail_fetch)
    monkeypatch.setitem(
        agent.TOOL_REGISTRY,
        "manage_space_journal",
        lambda **kwargs: {"status": "success", "entries": []},
    )
    monkeypatch.setitem(agent.TOOL_REGISTRY, "show_space_dashboard", fake_dashboard)

    events = await _collect_events("Show me what's in my space journal")

    assert [event["type"] for event in events] == [
        "start",
        "thinking",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "dashboard",
        "text",
        "done",
    ]
    assert events[2]["data"] == {
        "name": "manage_space_journal",
        "args": {"operation": "read"},
    }
    assert events[4]["data"] == {
        "name": "show_space_dashboard",
        "args": {"journal_entries": []},
    }
    assert dashboard_args == {"journal_entries": []}
    assert events[6]["data"] == {"html": "<html>journal dashboard</html>"}
    assert "no entries" in events[7]["data"]["text"].lower()


@pytest.mark.asyncio
async def test_agent_loop_journal_read_shortcut_passes_entries(monkeypatch):
    journal_entries = [
        {
            "id": "observation-2026-04-26-abc123",
            "type": "observation",
            "date": "2026-04-26",
            "title": "Lunar sketch",
        }
    ]
    dashboard_args: dict[str, Any] = {}

    class FakeDashboard:
        def html(self) -> str:
            return "<html>dashboard</html>"

    def fake_dashboard(**kwargs: Any) -> FakeDashboard:
        dashboard_args.update(kwargs)
        return FakeDashboard()

    monkeypatch.setattr(
        agent,
        "_get_gemini_client",
        lambda: (_ for _ in ()).throw(AssertionError("Gemini should not be called")),
    )
    monkeypatch.setitem(
        agent.TOOL_REGISTRY,
        "fetch_space_data",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("fetch_space_data should not be called")
        ),
    )
    monkeypatch.setitem(
        agent.TOOL_REGISTRY,
        "manage_space_journal",
        lambda **kwargs: {"status": "success", "entries": journal_entries},
    )
    monkeypatch.setitem(agent.TOOL_REGISTRY, "show_space_dashboard", fake_dashboard)

    events = await _collect_events("Show me what's in my space journal")

    assert dashboard_args == {"journal_entries": journal_entries}
    assert events[-2]["data"]["text"] == (
        "Your space journal has 1 entry. I rendered it on the dashboard."
    )


@pytest.mark.asyncio
async def test_agent_loop_max_iterations(monkeypatch):
    models = FakeModels([_response(_function_part("fetch_space_data", {}))])
    monkeypatch.setattr(agent, "_get_gemini_client", lambda: _fake_client(models))
    monkeypatch.setattr(agent, "MAX_ITERATIONS", 2)
    monkeypatch.setitem(agent.TOOL_REGISTRY, "fetch_space_data", lambda **kwargs: {"ok": True})

    events = await _collect_events("keep going")

    assert [event["type"] for event in events] == [
        "start",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "text",
        "done",
    ]
    assert len(models.calls) == 2
    assert "maximum reasoning limit" in events[-2]["data"]["text"]


def test_dispatch_tool_caches_fetch_result(monkeypatch):
    agent._last_fetch_result = None

    def fake_fetch(**kwargs: Any) -> dict[str, Any]:
        return {"apod": {"title": "Test"}, "neos": list(range(10))}

    monkeypatch.setitem(agent.TOOL_REGISTRY, "fetch_space_data", fake_fetch)

    agent._dispatch_tool("fetch_space_data", {})

    assert agent._last_fetch_result == {"apod": {"title": "Test"}, "neos": list(range(10))}


def test_dispatch_tool_injects_cached_data(monkeypatch):
    agent._last_fetch_result = {"apod": {"title": "Cached"}, "neos": [1, 2, 3]}
    received_args: dict[str, Any] = {}

    class FakeDashboard:
        def html(self) -> str:
            return "<html></html>"

    def fake_dashboard(**kwargs: Any) -> FakeDashboard:
        received_args.update(kwargs)
        return FakeDashboard()

    monkeypatch.setitem(agent.TOOL_REGISTRY, "show_space_dashboard", fake_dashboard)

    agent._dispatch_tool(
        "show_space_dashboard",
        {"space_data": {"apod": {"title": "Gemini truncated"}}, "journal_entries": []},
    )

    assert received_args["space_data"] == {"apod": {"title": "Cached"}, "neos": [1, 2, 3]}
    assert received_args["journal_entries"] == []


def test_dispatch_tool_no_injection_without_cache(monkeypatch):
    agent._last_fetch_result = None
    received_args: dict[str, Any] = {}

    class FakeDashboard:
        def html(self) -> str:
            return "<html></html>"

    def fake_dashboard(**kwargs: Any) -> FakeDashboard:
        received_args.update(kwargs)
        return FakeDashboard()

    monkeypatch.setitem(agent.TOOL_REGISTRY, "show_space_dashboard", fake_dashboard)

    gemini_data = {"apod": {"title": "Gemini version"}}
    agent._dispatch_tool("show_space_dashboard", {"space_data": gemini_data})

    assert received_args["space_data"] == gemini_data


def test_dispatch_tool_error_does_not_cache(monkeypatch):
    agent._last_fetch_result = None

    def broken_fetch(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("API down")

    monkeypatch.setitem(agent.TOOL_REGISTRY, "fetch_space_data", broken_fetch)

    agent._dispatch_tool("fetch_space_data", {})

    assert agent._last_fetch_result is None


def test_journal_payload_schema_has_required_fields():
    """Verify payload property in manage_space_journal has type and date as required."""
    journal_decl = next(d for d in agent.FUNCTION_DECLARATIONS if d.name == "manage_space_journal")
    payload_schema = journal_decl.parameters.properties["payload"]

    assert "type" in payload_schema.properties
    assert "date" in payload_schema.properties
    assert "type" in payload_schema.required
    assert "date" in payload_schema.required
