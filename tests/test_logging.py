from __future__ import annotations

import json

from lib.python.logging import get_logger


def test_get_logger_emits_json_with_extra_fields(capsys):
    log = get_logger("tests.logging.case1")
    log.info("ingest complete", extra={"inserted": 5, "runtime_s": 1.23})

    captured = capsys.readouterr()
    entry = json.loads(captured.out.strip())

    assert entry["level"] == "INFO"
    assert entry["logger"] == "tests.logging.case1"
    assert entry["message"] == "ingest complete"
    assert entry["inserted"] == 5
    assert entry["runtime_s"] == 1.23
    assert "timestamp" in entry


def test_get_logger_does_not_duplicate_handlers():
    log1 = get_logger("tests.logging.case2")
    log2 = get_logger("tests.logging.case2")

    assert log1 is log2
    assert len(log1.handlers) == 1


def test_get_logger_includes_exception_info(capsys):
    log = get_logger("tests.logging.case3")
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("something failed")

    captured = capsys.readouterr()
    entry = json.loads(captured.out.strip())
    assert "ValueError: boom" in entry["exception"]
