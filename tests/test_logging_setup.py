import logging
import re
from pathlib import Path

from hotelai import logging_setup
from hotelai.config import settings


def test_configure_logging_writes_timestamped_entries_to_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "log_dir", tmp_path)
    monkeypatch.setattr(logging_setup, "_configured", False)
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    level_before = root.level

    logging_setup.configure_logging()
    try:
        logging.getLogger("test_logging_setup").warning("evento di prova")
    finally:
        for handler in list(root.handlers):
            if handler not in handlers_before:
                root.removeHandler(handler)
                handler.close()
        root.setLevel(level_before)

    content = settings.log_path.read_text(encoding="utf-8")
    assert "evento di prova" in content
    assert "WARNING" in content
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", content)


def test_configure_logging_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "log_dir", tmp_path)
    monkeypatch.setattr(logging_setup, "_configured", False)
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    level_before = root.level

    logging_setup.configure_logging()
    logging_setup.configure_logging()
    added = [handler for handler in root.handlers if handler not in handlers_before]
    try:
        assert len(added) == 1
    finally:
        for handler in added:
            root.removeHandler(handler)
            handler.close()
        root.setLevel(level_before)


def test_uncaught_exception_is_logged(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "log_dir", tmp_path)
    monkeypatch.setattr(logging_setup, "_configured", False)
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    level_before = root.level

    logging_setup.configure_logging()
    try:
        try:
            raise ValueError("boom di prova")
        except ValueError:
            import sys

            logging_setup._log_uncaught_exception(*sys.exc_info())
    finally:
        for handler in list(root.handlers):
            if handler not in handlers_before:
                root.removeHandler(handler)
                handler.close()
        root.setLevel(level_before)

    content = settings.log_path.read_text(encoding="utf-8")
    assert "boom di prova" in content
    assert "CRITICAL" in content
