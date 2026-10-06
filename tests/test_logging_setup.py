"""The server must start even when it cannot write its log file.

A directory that exists is not necessarily writable. A container that runs as an ordinary user, with
a volume Docker created as root, has /logs but cannot make a file in it; os.makedirs(exist_ok=True)
is perfectly happy there, and the RotatingFileHandler that came next raised PermissionError and took
the whole server down at start-up.
"""

import logging.handlers
import os

import pytest

import gfg_main


def test_a_writable_directory_is_used(tmp_path):
    handler, used = gfg_main.open_log_file(str(tmp_path / "logs"))

    try:
        assert used == str(tmp_path / "logs")
        assert handler.baseFilename == str(tmp_path / "logs" / "access.log")
    finally:
        handler.close()


def test_a_directory_that_cannot_be_created_falls_back(tmp_path):
    blocker = tmp_path / "a_file"
    blocker.write_text("not a directory")
    fallback = tmp_path / "fallback"

    handler, used = gfg_main.open_log_file(str(blocker / "logs"), fallback_dir=str(fallback))

    try:
        assert used == str(fallback)
    finally:
        handler.close()


def test_a_directory_that_exists_but_cannot_be_written_falls_back(tmp_path, monkeypatch):
    """The container case: /logs is there, owned by root, and the server is not root.
       (The test suite may itself run as root, which ignores permissions, so the refusal is simulated.)"""
    unwritable, fallback = tmp_path / "logs", tmp_path / "fallback"
    unwritable.mkdir()
    real = logging.handlers.RotatingFileHandler

    def refuse_the_first(path, *args, **kwargs):
        if os.path.dirname(path) == str(unwritable):
            raise PermissionError(13, "Permission denied", path)
        return real(path, *args, **kwargs)

    monkeypatch.setattr(logging.handlers, "RotatingFileHandler", refuse_the_first)

    handler, used = gfg_main.open_log_file(str(unwritable), fallback_dir=str(fallback))

    try:
        assert used == str(fallback)
    finally:
        handler.close()


def test_with_nowhere_to_write_there_is_no_file_logging_but_no_crash(tmp_path, monkeypatch):
    def refuse_everything(path, *args, **kwargs):
        raise PermissionError(13, "Permission denied", path)

    monkeypatch.setattr(logging.handlers, "RotatingFileHandler", refuse_everything)

    assert gfg_main.open_log_file(str(tmp_path / "a"), fallback_dir=str(tmp_path / "b")) == (None, None)


def test_the_default_fallback_is_in_the_temporary_directory(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    blocker = tmp_path / "a_file"
    blocker.write_text("x")

    handler, used = gfg_main.open_log_file(str(blocker / "logs"))

    try:
        assert used == str(tmp_path / "gridfinitycreator-logs")
    finally:
        handler.close()


def test_the_server_start_up_uses_it():
    with open(os.path.join(os.path.dirname(gfg_main.__file__), "gfg_main.py"), encoding="utf-8") as handle:
        source = handle.read()

    assert "open_log_file(" in source.split('if __name__ == "__main__":')[1]
