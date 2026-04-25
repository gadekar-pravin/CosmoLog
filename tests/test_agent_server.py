from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest

import agent


@pytest.fixture(autouse=True)
def clear_conversation_history() -> None:
    agent.conversation_history.clear()


def _parse_sse(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    normalized = body.replace("\r\n", "\n").strip()
    if not normalized:
        return events

    for block in normalized.split("\n\n"):
        event_type = ""
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event: "):
                event_type = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data_lines.append(line.removeprefix("data: "))

        if event_type:
            data = json.loads("\n".join(data_lines)) if data_lines else {}
            events.append({"event": event_type, "data": data})

    return events


async def _fake_agent_loop(
    message: str,
    history: list[Any],
) -> AsyncGenerator[dict[str, Any], None]:
    yield {"type": "start", "data": {}}
    yield {"type": "text", "data": {"text": f"Echo: {message}"}}
    yield {"type": "done", "data": {}}


@pytest.mark.asyncio
async def test_health_endpoint():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=agent.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_reset_endpoint():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=agent.app),
        base_url="http://test",
    ) as client:
        response = await client.post("/reset")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_reset_clears_history():
    agent.conversation_history.append("existing turn")  # type: ignore[arg-type]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=agent.app),
        base_url="http://test",
    ) as client:
        response = await client.post("/reset")

    assert response.status_code == 200
    assert agent.conversation_history == []


@pytest.mark.asyncio
async def test_root_serves_html():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=agent.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "CosmoLog" in response.text
    assert "Mission Chat" in response.text
    assert "Live Dashboard" in response.text
    assert "Fetch today's APOD and show it on the dashboard" in response.text


@pytest.mark.asyncio
async def test_chat_returns_sse_content_type(monkeypatch):
    monkeypatch.setattr(agent, "agent_loop", _fake_agent_loop)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=agent.app),
        base_url="http://test",
    ) as client:
        response = await client.post("/chat", json={"message": "hi"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")


@pytest.mark.asyncio
async def test_chat_serializes_agent_events_as_sse(monkeypatch):
    monkeypatch.setattr(agent, "agent_loop", _fake_agent_loop)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=agent.app),
        base_url="http://test",
    ) as client:
        response = await client.post("/chat", json={"message": "hi"})

    assert _parse_sse(response.text) == [
        {"event": "start", "data": {}},
        {"event": "text", "data": {"text": "Echo: hi"}},
        {"event": "done", "data": {}},
    ]


@pytest.mark.asyncio
async def test_chat_uses_global_conversation_history(monkeypatch):
    seen_lengths: list[int] = []

    async def fake_agent_loop(
        message: str,
        history: list[Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        assert history is agent.conversation_history
        seen_lengths.append(len(history))
        history.append({"role": "user", "message": message})  # type: ignore[arg-type]
        yield {"type": "done", "data": {}}

    monkeypatch.setattr(agent, "agent_loop", fake_agent_loop)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=agent.app),
        base_url="http://test",
    ) as client:
        await client.post("/chat", json={"message": "first"})
        await client.post("/chat", json={"message": "second"})

    assert seen_lengths == [0, 1]
    assert len(agent.conversation_history) == 2


@pytest.mark.asyncio
async def test_chat_generator_exception_yields_error_done(monkeypatch):
    async def broken_agent_loop(
        message: str,
        history: list[Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        yield {"type": "start", "data": {}}
        raise RuntimeError("stream exploded")

    monkeypatch.setattr(agent, "agent_loop", broken_agent_loop)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=agent.app),
        base_url="http://test",
    ) as client:
        response = await client.post("/chat", json={"message": "hi"})

    assert _parse_sse(response.text) == [
        {"event": "start", "data": {}},
        {"event": "error", "data": {"message": "stream exploded"}},
        {"event": "done", "data": {}},
    ]


@pytest.mark.asyncio
async def test_chat_rejects_blank_message():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=agent.app),
        base_url="http://test",
    ) as client:
        response = await client.post("/chat", json={"message": "   "})

    assert response.status_code == 422
