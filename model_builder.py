"""Builds models in separate processes.

Why not build them in the web server's own threads? CadQuery's native geometry
calls hold Python's global interpreter lock for as long as they run. Measured: during
a 10 second build an unrelated thread was frozen for one unbroken 7 seconds, so the
home page stopped answering while anyone was generating. In a child process the build
cannot touch the web server at all. That also gives:

  * a hard time limit: a child that overruns is killed (threads cannot be stopped),
  * crash isolation: a native crash takes down one build, not the whole server,
  * real parallelism: two builds use two cores,
  * cancellation: a build whose client has gone away is killed, freeing its core.

Children come from the multiprocessing fork server, which loads CadQuery and the
generators once (see build_preload) and forks each child from that warm copy:
about 30 ms to start, instead of about 4 s to import CadQuery afresh.

Settings:
    GFG_BUILD_TIMEOUT   seconds a build may take before it is stopped   (default 300)
"""

import contextlib
import contextvars
import dataclasses
import logging
import multiprocessing
import os
import threading
import time
import traceback

import generator_loader
import grid_constants
from generators.common.errors import SettingsError
from job_limiter import CLIENT_CHECK_INTERVAL, ClientGone, number_from_env

logger = logging.getLogger('GFG')

DEFAULT_BUILD_TIMEOUT = 300  # seconds


class BuildFailed(Exception):
    """A build did not produce a model. The message is safe to show to the user;
       `details` holds technical information (a traceback, an exit code) for the log."""

    def __init__(self, message, details=""):
        super().__init__(message)
        self.details = details


class BuildTimeout(BuildFailed):
    """The build took longer than allowed and was stopped."""


def build_timeout():
    return number_from_env("GFG_BUILD_TIMEOUT", DEFAULT_BUILD_TIMEOUT, float)


# Says whether the client of the request being handled in this thread has disconnected, or None.
# The generators' main.py call build() without knowing about requests, so the web layer
# sets this for the duration of a request instead (see stop_when_gone).
client_gone_check = contextvars.ContextVar("client_gone_check", default=None)


@contextlib.contextmanager
def stop_when_gone(client_gone):
    """While in this block, any build started from this thread is stopped (ClientGone)
       as soon as `client_gone()` says the client has disconnected. None means never."""
    token = client_gone_check.set(client_gone)
    try:
        yield
    finally:
        client_gone_check.reset(token)


_context = None
_context_lock = threading.Lock()


def get_context():
    """The multiprocessing context builds run in: the fork server where available
       (Linux, macOS), otherwise plain spawn (Windows)."""
    global _context
    with _context_lock:
        if _context is None:
            method = "forkserver" if "forkserver" in multiprocessing.get_all_start_methods() else "spawn"
            context = multiprocessing.get_context(method)
            if method == "forkserver":
                context.set_forkserver_preload(["build_preload"])
            _context = context
        return _context


def _stop(process, finished):
    """Make sure the child is gone and reaped. A child that has reported its result
       is given a moment to exit by itself; one that has not is killed."""
    if finished:
        process.join(5)
    if process.is_alive():
        process.terminate()
        process.join(2)
    if process.is_alive():
        process.kill()
        process.join(2)


def run_in_process(target, args=(), timeout=None, client_gone=None):
    """Run target(sender, *args) in a child process and return the (status, payload)
       tuple it sends back through `sender`.

       Raises BuildTimeout if it does not answer within `timeout` seconds (the child is
       killed), ClientGone if `client_gone()` becomes true while it runs (the child is
       killed: nobody is waiting for its answer), and BuildFailed if it dies without
       answering."""
    timeout = build_timeout() if timeout is None else timeout
    context = get_context()

    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=target, args=(sender,) + tuple(args), daemon=True)
    process.start()
    sender.close()  # only the child writes to it; this lets a dead child show up as end-of-file

    answered = False
    try:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BuildTimeout(
                    f"This model took longer than {timeout:g} seconds to build, so it was stopped. "
                    "Try a smaller or simpler design.")
            if client_gone is None:
                ready = receiver.poll(remaining)
            else:
                ready = receiver.poll(min(remaining, CLIENT_CHECK_INTERVAL))
                if not ready and client_gone():
                    raise ClientGone()
            if ready:
                break
        try:
            result = receiver.recv()
        except EOFError:
            process.join(1)
            raise BuildFailed("The model builder stopped unexpectedly.",
                              f"the build process exited with code {process.exitcode}") from None
        answered = True
        return result
    finally:
        _stop(process, finished=answered)
        receiver.close()


def _worker(sender, generator_name, settings, grid, filename):
    """Runs in the child process: build the model and write it to `filename`."""
    try:
        module = generator_loader.get(generator_name)
        model_settings = module.settings.Settings(**settings)
        model_grid = grid_constants.Grid(**grid)
        module.generator.Generator(model_settings, model_grid).generate_stl(filename)
        sender.send(("ok", None))
    except SettingsError as e:
        sender.send(("settings", str(e)))
    except BaseException:
        sender.send(("error", traceback.format_exc()))
    finally:
        sender.close()


def build(generator_name, settings, grid, filename, timeout=None):
    """Build a model with the named generator and write it to `filename`.

       Runs in a separate process; see the module documentation. Raises SettingsError
       if the generator refuses the settings, BuildTimeout if it takes too long,
       ClientGone if the client of this request disconnects meanwhile (see
       stop_when_gone) and BuildFailed if anything else goes wrong."""
    try:
        status, payload = run_in_process(
            _worker,
            (generator_name, dataclasses.asdict(settings), dataclasses.asdict(grid), filename),
            timeout,
            client_gone=client_gone_check.get())

        if status == "settings":
            raise SettingsError(payload)
        if status != "ok":
            raise BuildFailed("The model could not be built.", payload)

        # The exporter does not complain when it cannot write its file
        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            raise BuildFailed("The model builder did not produce a file.")
    except Exception:
        try:
            os.remove(filename)  # never leave a partial file behind
        except OSError:
            pass
        raise


def _ready(sender):
    sender.send(("ok", None))
    sender.close()


def warm_up():
    """Start the fork server now, so that the first real build does not also have to
       wait for CadQuery to load. Safe to call from a background thread."""
    try:
        run_in_process(_ready, timeout=120)
        logger.info("Model builder is ready")
    except Exception:
        logger.exception("Could not warm up the model builder (builds will load CadQuery on demand)")
