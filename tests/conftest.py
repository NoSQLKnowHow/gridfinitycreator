"""Shared test fixtures.

The tests drive the real application: real generators, real CadQuery geometry and
the real Flask request pipeline (including CSRF tokens) through Flask's test client.
"""

import os
import re
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Generators are discovered relative to the working directory, and the project
# modules are imported by plain name, so run from the repository root
os.chdir(REPO)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import gfg_main  # noqa: E402

# Form values that produce a valid default model for each generator. Checkboxes
# are "on" when present and off when omitted, exactly like a browser submits them.
DEFAULT_PAYLOADS = {
    "baseplate": dict(
        sizeUnitsX=2, sizeUnitsY=2, baseStyle="standard", baseThickness="2.4",
        magnetHoleDiameter="6.5", exportFormat="stl"),
    "classicbin": dict(
        sizeUnitsX=2, sizeUnitsY=2, sizeUnitsZ=6, compartmentsX=3, compartmentsY=3,
        magnetHoleDiameter="6.5", exportFormat="stl", removedWalls="",
        addStackingLip="y", addMagnetHoles="y", addGrabCurve="y", addLabelRidge="y"),
    "holeybin": dict(
        numHolesX=3, numHolesY=3, sizeUnitsX=1, sizeUnitsY=1, holeDepth="5.0",
        holeShape="CIRCLE", holeSize="4.0", keepoutDiameter="12.0",
        magnetHoleDiameter="6.5", exportFormat="stl",
        addStackingLip="y", addMagnetHoles="y"),
    "lightbin": dict(
        sizeUnitsX=2, sizeUnitsY=2, sizeUnitsZ=6, compartmentsX=1, compartmentsY=1,
        exportFormat="stl", removedWalls="", addStackingLip="y", addLabelRidge="y"),
    "solidbin": dict(
        sizeUnitsX=2, sizeUnitsY=2, sizeUnitsZ=6, magnetHoleDiameter="6.5",
        exportFormat="stl", addStackingLip="y", addMagnetHoles="y"),
}

CSRF_PATTERN = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')


@pytest.fixture(scope="session")
def generators():
    """The loaded generator modules, keyed by directory name"""
    gfg_main.generators = gfg_main.load_generators()
    return {g.__name__: g for g in gfg_main.generators}


@pytest.fixture()
def tmp_output(tmp_path, monkeypatch):
    """Send generated files to a throwaway directory"""
    monkeypatch.setenv("GFG_TMP_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def client(generators, tmp_output):
    """A test client that behaves like production: unhandled errors become HTTP 500
       responses instead of propagating into the test"""
    app = gfg_main.app
    app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
    return app.test_client()


def csrf_token(client):
    """Load the home page (which starts the session) and return its CSRF token"""
    html = client.get("/").get_data(as_text=True)
    return CSRF_PATTERN.search(html).group(1)


def post_form(client, form_id, token=None, **overrides):
    """Submit one generator form the way the browser does. A keyword set to None
       removes that field (an unchecked checkbox); anything else overrides the default."""
    payload = dict(DEFAULT_PAYLOADS[form_id])
    payload.update(overrides)
    payload = {k: v for k, v in payload.items() if v is not None}
    payload["csrf_token"] = token if token is not None else csrf_token(client)
    payload[form_id] = "Generate"  # the name of the submit button
    return client.post("/", data=payload)


def form_html(client, form_id):
    """The rendered HTML of one generator's settings form, as served on the home page"""
    html = client.get("/").get_data(as_text=True)
    start = html.index(f'id="{form_id}_form"')
    return html[start:html.index("</form>", start)]


def is_checked(form_markup, field_name):
    """Whether the checkbox <input id=field_name> in this form markup is rendered checked"""
    tag = re.search(rf'<input[^>]*\bid="{field_name}"[^>]*>', form_markup).group(0)
    return re.search(r"\bchecked\b", tag) is not None


def solid_count(shape):
    """Number of separate solids in a CadQuery result"""
    return len((shape.val() if hasattr(shape, "val") else shape).Solids())
