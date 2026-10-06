"""The job limiter: a few builds at once, a few waiting, everything else turned away.

Without it, six large simultaneous builds made even the home page take 196 s.
"""

import threading
import time

import pytest
from flask import make_response

import gfg_main
import job_limiter
from conftest import post_form
from job_limiter import BUSY_MESSAGE, JobLimiter, ServerBusy


def hold(limiter):
    """Take a slot from this thread; returns the function that gives it back"""
    slot = limiter.slot()
    slot.__enter__()
    return lambda: slot.__exit__(None, None, None)


def wait_until(condition, timeout=3.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out waiting for the condition"
        time.sleep(0.005)


# ---------------------------------------------------------------- the limiter itself

def test_allows_up_to_max_running_at_once_and_turns_the_next_away():
    limiter = JobLimiter(max_running=2, max_waiting=0, wait_timeout=1)
    first, second = hold(limiter), hold(limiter)

    with pytest.raises(ServerBusy, match=BUSY_MESSAGE):
        with limiter.slot():
            pass

    first()
    with limiter.slot():  # room again
        assert limiter.running == 2
    second()
    assert limiter.running == 0


def test_a_waiting_request_gets_its_turn_when_a_slot_is_released():
    limiter = JobLimiter(max_running=1, max_waiting=1, wait_timeout=5)
    release = hold(limiter)
    finished = []

    def waiter():
        with limiter.slot():
            finished.append(True)

    thread = threading.Thread(target=waiter)
    thread.start()
    wait_until(lambda: limiter.waiting == 1)
    assert finished == []  # still waiting its turn

    release()
    thread.join(timeout=3)

    assert finished == [True]
    assert (limiter.running, limiter.waiting) == (0, 0)


def _take_a_turn(limiter):
    with limiter.slot():
        pass


def test_a_full_queue_turns_requests_away_immediately():
    limiter = JobLimiter(max_running=1, max_waiting=1, wait_timeout=5)
    release = hold(limiter)
    queued = threading.Thread(target=_take_a_turn, args=(limiter,))
    queued.start()
    wait_until(lambda: limiter.waiting == 1)  # the one allowed place in the queue is taken

    started = time.monotonic()
    with pytest.raises(ServerBusy):
        with limiter.slot():
            pass

    assert time.monotonic() - started < 1  # did not sit in the queue
    release()
    queued.join(timeout=3)


def test_a_request_that_waits_too_long_is_turned_away():
    limiter = JobLimiter(max_running=1, max_waiting=1, wait_timeout=0.15)
    release = hold(limiter)

    started = time.monotonic()
    with pytest.raises(ServerBusy):
        with limiter.slot():
            pass
    elapsed = time.monotonic() - started

    assert 0.1 <= elapsed < 2
    assert limiter.waiting == 0  # it left the queue
    release()


def test_the_slot_is_given_back_when_the_build_fails():
    limiter = JobLimiter(max_running=1, max_waiting=0, wait_timeout=1)

    with pytest.raises(RuntimeError):
        with limiter.slot():
            raise RuntimeError("the build blew up")

    assert limiter.running == 0
    with limiter.slot():  # not leaked
        pass


def test_never_runs_more_than_max_running_even_under_contention():
    limiter = JobLimiter(max_running=3, max_waiting=100, wait_timeout=30)
    lock = threading.Lock()
    state = dict(now=0, peak=0, done=0)

    def build():
        with limiter.slot():
            with lock:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            time.sleep(0.01)
            with lock:
                state["now"] -= 1
                state["done"] += 1

    threads = [threading.Thread(target=build) for _ in range(30)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert state["done"] == 30
    assert state["peak"] == 3
    assert (limiter.running, limiter.waiting) == (0, 0)


# ---------------------------------------------------------------- configuration

def test_settings_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("GFG_MAX_JOBS", "5")
    monkeypatch.setenv("GFG_MAX_QUEUE", "7")
    monkeypatch.setenv("GFG_QUEUE_TIMEOUT", "2.5")

    limiter = JobLimiter.from_env()

    assert (limiter.max_running, limiter.max_waiting, limiter.wait_timeout) == (5, 7, 2.5)


@pytest.mark.parametrize("junk", ["", "abc", "0", "-3"])
def test_unusable_environment_values_fall_back_to_the_defaults(monkeypatch, junk):
    for name in ("GFG_MAX_JOBS", "GFG_MAX_QUEUE", "GFG_QUEUE_TIMEOUT", "GFG_THREADS"):
        monkeypatch.setenv(name, junk)

    limiter = JobLimiter.from_env()

    assert (limiter.max_running, limiter.max_waiting, limiter.wait_timeout) == (2, 4, 120.0)
    assert job_limiter.server_threads(limiter) == 10


def test_the_server_always_gets_a_thread_to_spare():
    """Waiting builds occupy server threads; one must stay free for cheap requests"""
    limiter = JobLimiter(max_running=2, max_waiting=4)

    assert job_limiter.server_threads(limiter) == 10           # default: threads needed + 4
    assert limiter.threads_needed == 6


def test_a_too_small_thread_count_is_raised(monkeypatch):
    monkeypatch.setenv("GFG_THREADS", "3")

    assert job_limiter.server_threads(JobLimiter(max_running=2, max_waiting=4)) == 7  # 6 + 1


# ---------------------------------------------------------------- in the application

def test_a_busy_server_turns_builds_away_but_still_serves_cheap_requests(client, monkeypatch):
    limiter = JobLimiter(max_running=1, max_waiting=0, wait_timeout=1)
    monkeypatch.setattr(gfg_main, "limiter", limiter)
    release = hold(limiter)
    try:
        preview = post_form(client, "baseplate", preview="true")
        download = post_form(client, "baseplate")
        dimensions = post_form(client, "baseplate", dimensions="true")
        home = client.get("/")
    finally:
        release()

    assert preview.status_code == 503
    assert preview.get_json() == {"errors": [BUSY_MESSAGE]}
    assert preview.headers["Retry-After"] == "5"

    assert download.status_code == 503
    assert BUSY_MESSAGE in download.get_data(as_text=True)

    # The point of the exercise: cheap requests are not stuck behind the builds
    assert dimensions.status_code == 200
    assert home.status_code == 200

    # and once there is capacity again, builds work
    assert post_form(client, "baseplate").status_code == 200


def test_a_build_holds_a_slot_while_it_runs_and_releases_it_afterwards(client, generators, monkeypatch):
    limiter = JobLimiter(max_running=2, max_waiting=0, wait_timeout=1)
    monkeypatch.setattr(gfg_main, "limiter", limiter)
    seen = []

    def process(form, constants):
        seen.append(limiter.running)
        return make_response("model")

    monkeypatch.setattr(generators["baseplate"], "process", process)
    response = post_form(client, "baseplate")

    assert response.status_code == 200
    assert seen == [1]
    assert limiter.running == 0


def test_dimensions_requests_never_take_a_slot(client, monkeypatch):
    limiter = JobLimiter(max_running=1, max_waiting=0, wait_timeout=1)
    monkeypatch.setattr(gfg_main, "limiter", limiter)
    release = hold(limiter)
    try:
        assert post_form(client, "classicbin", dimensions="true").status_code == 200
    finally:
        release()
