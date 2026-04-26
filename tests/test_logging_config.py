from __future__ import annotations

import asyncio
import logging

import logging_config
from logging_config import (
    CorrelationFilter,
    SSELogHandler,
    _truncate,
    configure_logging,
    get_correlation_id,
    set_correlation_id,
)


class TestSSELogHandler:
    _cid_filter = CorrelationFilter()

    def _handler_with_queue(
        self, target_cid: str, maxsize: int = 100
    ) -> tuple[SSELogHandler, asyncio.Queue]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        handler = SSELogHandler(queue, target_cid=target_cid)
        return handler, queue

    def _emit(self, handler: SSELogHandler, record: logging.LogRecord) -> None:
        """Apply CorrelationFilter (as root logger would) then emit."""
        self._cid_filter.filter(record)
        handler.emit(record)

    def test_captures_matching_cid(self):
        token = logging_config.correlation_id.set("abc123")
        try:
            handler, queue = self._handler_with_queue("abc123")
            record = _make_record(msg="tool_dispatch name=fetch")
            self._emit(handler, record)
            assert not queue.empty()
            entry = queue.get_nowait()
            assert entry["level"] == "INFO"
            assert entry["message"] == "tool_dispatch name=fetch"
            assert "module" in entry
            assert "timestamp" in entry
        finally:
            logging_config.correlation_id.reset(token)

    def test_ignores_different_cid(self):
        token = logging_config.correlation_id.set("xyz789")
        try:
            handler, queue = self._handler_with_queue("abc123")
            record = _make_record()
            self._emit(handler, record)
            assert queue.empty()
        finally:
            logging_config.correlation_id.reset(token)

    def test_ignores_debug_level(self):
        token = logging_config.correlation_id.set("abc123")
        try:
            handler, queue = self._handler_with_queue("abc123")
            record = _make_record(level=logging.DEBUG)
            self._emit(handler, record)
            assert queue.empty()
        finally:
            logging_config.correlation_id.reset(token)

    def test_full_queue_does_not_raise(self):
        token = logging_config.correlation_id.set("abc123")
        try:
            handler, queue = self._handler_with_queue("abc123", maxsize=1)
            for _ in range(5):
                record = _make_record()
                self._emit(handler, record)
            assert queue.qsize() == 1
        finally:
            logging_config.correlation_id.reset(token)


def _make_record(
    name: str = "test", level: int = logging.INFO, msg: str = "hello"
) -> logging.LogRecord:
    return logging.LogRecord(
        name=name,
        level=level,
        pathname="",
        lineno=0,
        msg=msg,
        args=None,
        exc_info=None,
    )


def _reset_logging_config(monkeypatch):
    """Reset module-level state so configure_logging() runs fresh."""
    monkeypatch.setattr(logging_config, "_configured", False)
    # Remove any handlers added by previous configure_logging() calls
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)


class TestConfigureLogging:
    def test_sets_up_root_handler_and_filter(self, monkeypatch):
        _reset_logging_config(monkeypatch)
        configure_logging()

        root = logging.getLogger()
        assert len(root.handlers) >= 1

        handler = root.handlers[-1]
        filter_types = [type(f) for f in handler.filters]
        assert CorrelationFilter in filter_types

    def test_idempotent(self, monkeypatch):
        _reset_logging_config(monkeypatch)
        configure_logging()
        handler_count = len(logging.getLogger().handlers)

        configure_logging()
        assert len(logging.getLogger().handlers) == handler_count


class TestCorrelationFilter:
    def test_injects_correlation_id(self):
        filt = CorrelationFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=None,
            exc_info=None,
        )
        result = filt.filter(record)
        assert result is True
        assert hasattr(record, "correlation_id")

    def test_default_correlation_id(self, monkeypatch):
        monkeypatch.setattr(logging_config, "correlation_id", logging_config.correlation_id)
        # Reset to default by using a fresh context
        token = logging_config.correlation_id.set("no-request")
        try:
            filt = CorrelationFilter()
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="hello",
                args=None,
                exc_info=None,
            )
            filt.filter(record)
            assert record.correlation_id == "no-request"  # type: ignore[attr-defined]
        finally:
            logging_config.correlation_id.reset(token)


class TestCorrelationIdGetSet:
    def test_roundtrip(self):
        original = get_correlation_id()
        set_correlation_id("test-abc123")
        assert get_correlation_id() == "test-abc123"
        # Restore
        set_correlation_id(original)


class TestTruncate:
    def test_short_string_unchanged(self):
        assert _truncate("hello") == "hello"

    def test_long_string_truncated(self):
        long = "x" * 600
        result = _truncate(long, max_len=500)
        assert len(result) == 503  # 500 + "..."
        assert result.endswith("...")

    def test_dict_converted_to_string(self):
        result = _truncate({"key": "value"})
        assert "key" in result
        assert "value" in result

    def test_none(self):
        assert _truncate(None) == "None"

    def test_custom_max_len(self):
        result = _truncate("abcdefgh", max_len=5)
        assert result == "abcde..."
