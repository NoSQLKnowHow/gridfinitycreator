"""Stand-ins for the build worker, used to test model_builder's process handling.

They live in their own light module because the child process has to import them by
name, and they must not pull in CadQuery. Each takes the pipe `sender` first.
"""

import os
import time


def answers(sender, status, payload):
    sender.send((status, payload))
    sender.close()


def reports_its_pid(sender):
    sender.send(("ok", os.getpid()))
    sender.close()


def hangs(sender, pid_file):
    """Records its pid, then never answers"""
    with open(pid_file, "w") as handle:
        handle.write(str(os.getpid()))
    time.sleep(3600)


def crashes(sender):
    """Dies without answering, the way a native crash would"""
    os._exit(3)


def raises(sender):
    raise RuntimeError("boom")
