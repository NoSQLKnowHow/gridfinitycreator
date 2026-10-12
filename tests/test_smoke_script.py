"""tools/smoke_test.py is what CI points at the hardened container, so it has to be right: a bug in
it would fail the build for the wrong reason. Run it here against a real server, and against nothing.
"""

import os
import subprocess
import sys
import threading

import pytest
import waitress

import gfg_main
import security_headers
from conftest import REPO

SCRIPT = os.path.join(REPO, "tools", "smoke_test.py")


@pytest.fixture()
def server(generators):
    instance = waitress.create_server(gfg_main.app, host="127.0.0.1", port=0, threads=6)
    thread = threading.Thread(target=instance.run, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{instance.effective_port}"
    instance.close()
    thread.join(10)


def run(*arguments, timeout=240):
    return subprocess.run([sys.executable, SCRIPT, *arguments], capture_output=True, text=True, timeout=timeout)


def test_every_check_passes_against_a_working_server(server):
    result = run(server)

    assert result.returncode == 0, result.stdout + result.stderr
    for check in ("the home page", "a static file", "the dimensions readout", "a preview", "a download (STL)",
                  "a download (3MF)", "a refused request", "the security headers"):
        assert f"ok    {check}" in result.stdout, result.stdout


def test_it_fails_with_a_message_when_nothing_is_listening():
    result = run("http://127.0.0.1:9", "--wait", "1", timeout=60)

    assert result.returncode != 0
    assert "did not answer" in (result.stdout + result.stderr)


def test_it_fails_when_a_check_fails(server, monkeypatch):
    """Point it at a server whose download answers with something that is not a model"""
    monkeypatch.setattr(gfg_main, "generate", lambda gen, f, constants: gfg_main.make_response("not a model", 200))

    result = run(server)

    assert result.returncode != 0
    assert "FAIL" in result.stdout


def test_it_notices_a_server_that_sends_no_security_headers(server, monkeypatch):
    monkeypatch.setattr(security_headers, "HEADERS", {})

    result = run(server)

    assert result.returncode != 0
    assert "FAIL  the security headers" in result.stdout
    assert "ok    the home page" in result.stdout
