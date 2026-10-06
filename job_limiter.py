"""Bounds how many models are built at once.

Building a model keeps a CPU core busy for seconds to minutes. With no bound, a few
simultaneous requests occupy every server thread, and then even loading the home page
waits behind them (measured: six large builds made the home page take 196 s instead of
0.04 s). The limiter lets a few builds run, lets a few more wait their turn, and turns
everything beyond that away immediately with a "busy" answer - so there are always
server threads left over for cheap requests.

Waiting requests still occupy a server thread, which is why the server must be given
more threads than max_running + max_waiting (see threads_needed).

Settings, all optional environment variables (defaults suit a small private network):
    GFG_MAX_JOBS       models built at the same time                  (default 2)
    GFG_MAX_QUEUE      further requests allowed to wait for a turn    (default 4)
    GFG_QUEUE_TIMEOUT  seconds a waiting request is kept waiting      (default 120)
"""

import os
import threading
import time
from contextlib import contextmanager

BUSY_MESSAGE = "The server is busy building other models. Please try again in a moment."


class ServerBusy(Exception):
    """No capacity to build another model right now."""


def number_from_env(name, default, cast):
    try:
        value = cast(os.environ.get(name, default))
    except ValueError:
        return default
    return value if value > 0 else default


class JobLimiter:
    def __init__(self, max_running=2, max_waiting=4, wait_timeout=120.0):
        self.max_running = max_running
        self.max_waiting = max_waiting
        self.wait_timeout = wait_timeout
        self._running = 0
        self._waiting = 0
        self._condition = threading.Condition()

    @classmethod
    def from_env(cls):
        return cls(
            max_running=number_from_env("GFG_MAX_JOBS", 2, int),
            max_waiting=number_from_env("GFG_MAX_QUEUE", 4, int),
            wait_timeout=number_from_env("GFG_QUEUE_TIMEOUT", 120.0, float),
        )

    @property
    def threads_needed(self):
        """Server threads this limiter can occupy at once (running plus waiting)"""
        return self.max_running + self.max_waiting

    @property
    def running(self):
        return self._running

    @property
    def waiting(self):
        return self._waiting

    @contextmanager
    def slot(self):
        """Hold one build slot for the duration of the with-block.

           Waits for a free slot if there is room in the queue; raises ServerBusy if
           the queue is full or the wait times out."""
        deadline = time.monotonic() + self.wait_timeout

        with self._condition:
            if self._running >= self.max_running:
                if self._waiting >= self.max_waiting:
                    raise ServerBusy(BUSY_MESSAGE)

                self._waiting += 1
                try:
                    while self._running >= self.max_running:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise ServerBusy(BUSY_MESSAGE)
                        self._condition.wait(remaining)
                finally:
                    self._waiting -= 1

            self._running += 1

        try:
            yield
        finally:
            with self._condition:
                self._running -= 1
                self._condition.notify()


def server_threads(limiter):
    """How many threads the web server should run (GFG_THREADS to override).

       Always more than the limiter can occupy, so a thread stays free for the
       home page and the cheap dimensions requests while builds are queued."""
    requested = number_from_env("GFG_THREADS", limiter.threads_needed + 4, int)
    return max(requested, limiter.threads_needed + 1)
