from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import types

import agent


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


def test_journal_payload_schema_has_required_fields():
    """Verify payload property in manage_space_journal has type and date as required."""
    journal_decl = next(d for d in agent.FUNCTION_DECLARATIONS if d.name == "manage_space_journal")
    payload_schema = journal_decl.parameters.properties["payload"]

    assert "type" in payload_schema.properties
    assert "date" in payload_schema.properties
    assert "type" in payload_schema.required
    assert "date" in payload_schema.required
