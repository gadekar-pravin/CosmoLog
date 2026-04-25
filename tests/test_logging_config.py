from __future__ import annotations

import logging

import logging_config
from logging_config import (
    CorrelationFilter,
    _truncate,
    configure_logging,
    get_correlation_id,
    set_correlation_id,
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
