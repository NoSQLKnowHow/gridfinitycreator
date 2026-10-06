"""Requests whose client has gone away are not worked on.

The preview is requested again on every change to the form, and the page cancels the
request it replaces (static/latest_request.js). That only helps the browser: unless the
server notices as well, the abandoned request still waits for a build slot and then builds
a model nobody will receive. Under load, a user's newest request could even be turned away
(503) because the queue was full of their own abandoned ones.

Three layers cooperate, each tested here: the limiter drops waiting requests, the model
builder stops running ones, and the server is configured so that it can tell at all
(waitress reports a hang-up to a running request only if told to look ahead).
"""

import dataclasses
import os
import socket
import threading
import time

import pytest
import waitress

import gfg_main
import job_limiter
import model_builder
import fake_builders
from conftest import REPO, post_form
from job_limiter import ClientGone, JobLimiter


class Client:
    """A client that can hang up: callable, like waitress.client_disconnected"""

    def __init__(self):
        self.gone = False

    def __call__(self):
        return self.gone


def hold(limiter):
    slot = limiter.slot()
    slot.__enter__()
    return lambda: slot.__exit__(None, None, None)


def wait_until(condition, timeout=3.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out waiting for the condition"
        time.sleep(0.005)


def alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


# ---------------------------------------------------------------- the limiter

def test_a_waiting_request_whose_client_has_gone_leaves_the_queue():
    limiter = JobLimiter(max_running=1, max_waiting=2, wait_timeout=30)
    release = hold(limiter)
    client, outcome = Client(), []

    def waiter():
        try:
            with limiter.slot(client):
                outcome.append("built")
        except ClientGone:
            outcome.append("gone")

    thread = threading.Thread(target=waiter)
    thread.start()
    wait_until(lambda: limiter.waiting == 1)

    client.gone = True
    thread.join(timeout=3)

    assert outcome == ["gone"]
    assert limiter.waiting == 0
    assert limiter.running == 1  # only the one that was really building
    release()
    assert limiter.running == 0


def test_a_request_abandoned_before_its_turn_never_runs():
    limiter = JobLimiter(max_running=2, max_waiting=0, wait_timeout=1)
    ran = []

    with pytest.raises(ClientGone):
        with limiter.slot(lambda: True):
            ran.append(True)

    assert ran == []
    assert limiter.running == 0
    with limiter.slot():  # and nothing was leaked
        assert limiter.running == 1


def test_giving_up_a_turn_hands_it_to_the_next_in_line():
    """The slot's release wakes one waiter. If that one has gone, the turn must pass on,
       not sit unused while the next request waits out its whole timeout."""
    limiter = JobLimiter(max_running=1, max_waiting=2, wait_timeout=30)
    release = hold(limiter)
    gone, outcome = Client(), {}

    def first_in_line():
        try:
            with limiter.slot(gone):
                outcome["first"] = "built"
        except ClientGone:
            outcome["first"] = "gone"

    def second_in_line():
        with limiter.slot():
            outcome["second"] = "built"

    first = threading.Thread(target=first_in_line)
    first.start()
    wait_until(lambda: limiter.waiting == 1)   # waiters are woken in the order they arrived
    second = threading.Thread(target=second_in_line)
    second.start()
    wait_until(lambda: limiter.waiting == 2)

    gone.gone = True
    release()
    second.join(timeout=3)

    assert outcome == {"first": "gone", "second": "built"}


def test_requests_that_pass_no_check_wait_exactly_as_before():
    limiter = JobLimiter(max_running=1, max_waiting=1, wait_timeout=0.3)
    release = hold(limiter)

    with pytest.raises(job_limiter.ServerBusy):
        with limiter.slot():
            pass
    release()


# ---------------------------------------------------------------- the model builder

def test_a_running_build_is_stopped_when_its_client_goes(tmp_path):
    pid_file, client = tmp_path / "pid", Client()

    def hang_up_once_the_build_has_started():
        wait_until(pid_file.exists, timeout=20)
        time.sleep(0.1)
        client.gone = True

    threading.Thread(target=hang_up_once_the_build_has_started, daemon=True).start()
    started = time.monotonic()
    with pytest.raises(ClientGone):
        model_builder.run_in_process(fake_builders.hangs, (str(pid_file),), timeout=30, client_gone=client)

    assert time.monotonic() - started < 10               # not the 30 s it would otherwise have run
    assert not alive(int(pid_file.read_text()))          # and the process is really gone


@dataclasses.dataclass
class Params:
    size: int = 1


def test_build_uses_the_check_set_for_this_request(tmp_path, monkeypatch):
    output = tmp_path / "model.stl"
    output.write_bytes(b"solid x")
    seen = []

    def fake_run(target, args=(), timeout=None, client_gone=None):
        seen.append(client_gone)
        return ("ok", None)

    monkeypatch.setattr(model_builder, "run_in_process", fake_run)
    client = Client()

    with model_builder.stop_when_gone(client):
        model_builder.build("x", Params(), Params(), str(output))
    model_builder.build("x", Params(), Params(), str(output))   # outside the block: no check

    assert seen == [client, None]


def test_an_abandoned_build_leaves_no_partial_file_behind(tmp_path, monkeypatch):
    output = tmp_path / "model.stl"
    output.write_bytes(b"half a model")

    def fake_run(target, args=(), timeout=None, client_gone=None):
        raise ClientGone()

    monkeypatch.setattr(model_builder, "run_in_process", fake_run)

    with pytest.raises(ClientGone):
        model_builder.build("x", Params(), Params(), str(output))

    assert not output.exists()


# ---------------------------------------------------------------- in the application

def test_a_queued_request_is_dropped_when_its_client_hangs_up(client, generators, monkeypatch):
    limiter = JobLimiter(max_running=1, max_waiting=2, wait_timeout=30)
    monkeypatch.setattr(gfg_main, "limiter", limiter)
    built = []
    monkeypatch.setattr(generators["baseplate"], "process", lambda form, constants: built.append(True))
    release = hold(limiter)
    gone, result = Client(), {}

    def request():
        result["response"] = post_form(client, "baseplate", preview="true",
                                       environ={"waitress.client_disconnected": gone})

    thread = threading.Thread(target=request)
    thread.start()
    wait_until(lambda: limiter.waiting == 1)
    gone.gone = True
    thread.join(timeout=5)
    release()

    assert result["response"].status_code == 499   # nobody is listening; "client closed request"
    assert built == []                             # no model was built for it
    assert (limiter.running, limiter.waiting) == (0, 0)


def test_a_build_runs_with_the_clients_check_in_place(client, generators, monkeypatch):
    seen = []

    def process(form, constants):
        seen.append(model_builder.client_gone_check.get())
        from flask import make_response
        return make_response("model")

    monkeypatch.setattr(generators["baseplate"], "process", process)
    gone = Client()

    post_form(client, "baseplate", environ={"waitress.client_disconnected": gone})
    post_form(client, "baseplate")  # a server that does not provide the check (Flask's own)

    assert seen == [gone, None]
    assert model_builder.client_gone_check.get() is None  # nothing leaks out of the request


# ---------------------------------------------------------------- the server itself

def request_that_hangs_up(server_options, watch_seconds):
    """Serve a request that watches for its client leaving, hang up, and say whether it noticed"""
    noticed, started = threading.Event(), threading.Event()

    def app(environ, start_response):
        gone = environ["waitress.client_disconnected"]
        started.set()
        deadline = time.monotonic() + watch_seconds
        while time.monotonic() < deadline:
            if gone():
                noticed.set()
                break
            time.sleep(0.02)
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]

    server = waitress.create_server(app, host="127.0.0.1", port=0, **server_options)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        connection = socket.create_connection(("127.0.0.1", server.effective_port))
        connection.sendall(b"POST / HTTP/1.1\r\nHost: test\r\nContent-Length: 0\r\n\r\n")
        assert started.wait(5)
        connection.close()  # what an aborted fetch() does
        return noticed.wait(watch_seconds)
    finally:
        server.close()
        thread.join(10)


def test_the_server_options_let_a_running_request_see_its_client_leave():
    options = job_limiter.server_options(JobLimiter())

    assert request_that_hangs_up(options, watch_seconds=4) is True


def test_without_looking_ahead_waitress_never_tells_a_running_request():
    """The control for the test above: this is why server_options() sets the option"""
    options = dict(job_limiter.server_options(JobLimiter()), channel_request_lookahead=0)

    assert request_that_hangs_up(options, watch_seconds=1.5) is False


def test_the_options_keep_the_thread_count_the_limiter_needs():
    limiter = JobLimiter(max_running=2, max_waiting=4)

    assert job_limiter.server_options(limiter)["threads"] == job_limiter.server_threads(limiter)


def test_the_production_server_is_started_with_those_options():
    with open(os.path.join(REPO, "gfg_main.py"), encoding="utf-8") as handle:
        source = handle.read()

    assert "waitress.serve(app, host=host, port=port, **job_limiter.server_options(limiter))" in source
