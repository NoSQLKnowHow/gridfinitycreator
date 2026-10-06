"""Models are built in a separate process.

CadQuery's native calls hold Python's global interpreter lock, so building in the web
server's own threads froze every other request (a 10 s build stalled an unrelated
thread for an unbroken 7 s). A child process cannot do that, and can also be killed
when it overruns or crash without taking the server with it.
"""

import logging
import os
import time

import pytest

import fake_builders
import grid_constants
import model_builder
from conftest import post_form
from generators.common.errors import SettingsError


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


# ---------------------------------------------------------------- process handling

def test_returns_what_the_child_sends_back():
    result = model_builder.run_in_process(fake_builders.answers, ("ok", {"size": 3}), timeout=30)

    assert result == ("ok", {"size": 3})


def test_the_work_happens_in_another_process():
    status, pid = model_builder.run_in_process(fake_builders.reports_its_pid, timeout=30)

    assert status == "ok"
    assert pid != os.getpid()


def test_a_child_that_overruns_is_killed(tmp_path):
    pid_file = tmp_path / "pid"

    started = time.monotonic()
    with pytest.raises(model_builder.BuildTimeout, match="longer than 2 seconds"):
        model_builder.run_in_process(fake_builders.hangs, (str(pid_file),), timeout=2)

    assert time.monotonic() - started < 15
    assert not alive(int(pid_file.read_text()))  # stopped, not left running


def test_a_crashed_child_is_reported_promptly_not_after_the_full_timeout():
    started = time.monotonic()
    with pytest.raises(model_builder.BuildFailed) as raised:
        model_builder.run_in_process(fake_builders.crashes, timeout=120)

    assert time.monotonic() - started < 30
    assert "exited with code 3" in raised.value.details
    assert not isinstance(raised.value, model_builder.BuildTimeout)


def test_an_unhandled_exception_in_the_child_is_reported():
    with pytest.raises(model_builder.BuildFailed):
        model_builder.run_in_process(fake_builders.raises, timeout=120)


# ---------------------------------------------------------------- real builds

def build(name, tmp_path, timeout=None, **settings_overrides):
    import generator_loader
    module = generator_loader.get(name)
    settings = module.settings.Settings()
    for key, value in settings_overrides.items():
        setattr(settings, key, value)
    filename = str(tmp_path / "model.stl")
    model_builder.build(name, settings, grid_constants.Grid(), filename, timeout=timeout)
    return filename


def test_a_real_build_writes_the_model(generators, tmp_path):
    filename = build("baseplate", tmp_path)

    assert os.path.getsize(filename) > 1000


def test_settings_the_generator_refuses_come_back_as_settings_errors(generators, tmp_path):
    with pytest.raises(SettingsError, match="largest allowed is 6 × 6"):
        build("holeybin", tmp_path, numHolesX=100, numHolesY=100, holeDepth=1000.0)

    assert list(tmp_path.iterdir()) == []


def test_a_build_that_takes_too_long_is_stopped_and_leaves_no_file(generators, tmp_path):
    with pytest.raises(model_builder.BuildTimeout):
        build("classicbin", tmp_path, timeout=0.5,
              sizeUnitsX=6, sizeUnitsY=6, sizeUnitsZ=12, compartmentsX=8, compartmentsY=8)  # ~10 s of work

    assert list(tmp_path.iterdir()) == []


def test_an_unknown_generator_is_a_build_failure_with_details(generators, tmp_path):
    settings = generators["baseplate"].settings.Settings()

    with pytest.raises(model_builder.BuildFailed) as raised:
        model_builder.build("no_such_generator", settings, grid_constants.Grid(), str(tmp_path / "x.stl"))

    assert "KeyError" in raised.value.details


def test_a_missing_output_file_is_an_error_not_a_silent_success(generators, tmp_path):
    """CadQuery's exporter returns normally when it cannot write its file"""
    settings = generators["baseplate"].settings.Settings()
    nowhere = str(tmp_path / "no" / "such" / "directory" / "model.stl")

    with pytest.raises(model_builder.BuildFailed, match="did not produce a file"):
        model_builder.build("baseplate", settings, grid_constants.Grid(), nowhere)


def test_the_timeout_comes_from_the_environment(monkeypatch):
    assert model_builder.build_timeout() == model_builder.DEFAULT_BUILD_TIMEOUT

    monkeypatch.setenv("GFG_BUILD_TIMEOUT", "42")
    assert model_builder.build_timeout() == 42

    monkeypatch.setenv("GFG_BUILD_TIMEOUT", "junk")
    assert model_builder.build_timeout() == model_builder.DEFAULT_BUILD_TIMEOUT


# ---------------------------------------------------------------- what the user sees

def test_a_build_that_overruns_is_explained_to_the_user(client, tmp_output, monkeypatch):
    monkeypatch.setenv("GFG_BUILD_TIMEOUT", "0.2")

    response = post_form(client, "classicbin")  # a normal bin takes about a second

    assert response.status_code == 422
    assert "took longer than 0.2 seconds to build" in response.get_data(as_text=True)
    assert list(tmp_output.iterdir()) == []


def test_a_crashing_build_is_a_friendly_error_and_is_logged(client, monkeypatch, caplog):
    import gfg_main

    def crash(*args, **kwargs):
        raise model_builder.BuildFailed("The model builder stopped unexpectedly.", "exited with code -11 (SIGSEGV)")

    monkeypatch.setattr(model_builder, "build", crash)
    with caplog.at_level(logging.ERROR):
        response = post_form(client, "baseplate")
    html = response.get_data(as_text=True)

    assert response.status_code == 500
    assert gfg_main.UNEXPECTED_ERROR_MESSAGE in html
    assert "SIGSEGV" not in html           # technical detail stays out of the page...
    assert "SIGSEGV" in caplog.text        # ...and goes to the log
