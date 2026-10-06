"""The browser-side code.

The validation module has its own unit tests in tests/js (run with Node), included here
so that a single `pytest` covers everything. They are skipped if Node is not installed.
"""

import os
import re
import shutil
import subprocess

import pytest

from conftest import REPO

NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
def test_javascript_unit_tests_pass():
    result = subprocess.run([NODE, "--test"], cwd=os.path.join(REPO, "tests", "js"),
                            capture_output=True, text=True, timeout=120)

    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-1000:]
    assert "# pass 0" not in result.stdout  # it really ran tests


def test_helper_scripts_load_before_the_scripts_that_use_them(client):
    html = client.get("/").get_data(as_text=True)

    assert html.index("/static/safe_config.js") < html.index("/static/library.js")
    assert html.index("/static/latest_request.js") < html.index("/static/viewer.js")


def test_the_library_never_builds_inline_event_handlers():
    """Escaping text for HTML does not make it safe inside onclick="f('...')": the browser
       decodes the entities before running the code. Buttons carry their ids in data
       attributes instead (and a single listener reads them)."""
    with open(os.path.join(REPO, "static", "library.js"), encoding="utf-8") as handle:
        source = handle.read()

    # Comments may well talk about onclick="..." (this fix's own does), only code counts
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    code = "\n".join(line for line in code.splitlines() if not line.lstrip().startswith("//"))

    assert not re.search(r"\bon[a-z]+\s*=\s*[\"']", code)
    assert "data-library-action" in code
