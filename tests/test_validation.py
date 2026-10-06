"""Server-side validation: out-of-range input is refused with a reason, never a crash.

The forms used to declare min/max only as HTML attributes, so anything that did
not come from a well-behaved browser (a stale tab, a shared link, a script) went
straight to the geometry code and typically ended in an HTTP 500 - or in a
multi-minute build. Most checks here use the cheap dimensions request, which
runs all validation without building any geometry.
"""

import pytest

from conftest import form_html, post_form

BAD_VALUES = [
    # (generator, field, value, message shown to the user)
    ("classicbin", "sizeUnitsX", "0", "Width: Must be between 1 and 6."),
    ("classicbin", "sizeUnitsX", "7", "Width: Must be between 1 and 6."),
    ("classicbin", "sizeUnitsX", "-3", "Width: Must be between 1 and 6."),
    ("classicbin", "sizeUnitsY", "1000000", "Length: Must be between 1 and 6."),
    ("classicbin", "sizeUnitsZ", "1", "Height: Must be between 2 and 12."),
    ("classicbin", "sizeUnitsZ", "13", "Height: Must be between 2 and 12."),
    ("classicbin", "compartmentsX", "0", "Width direction: Must be between 1 and 24."),
    ("classicbin", "compartmentsY", "25", "Length direction: Must be between 1 and 24."),
    ("classicbin", "magnetHoleDiameter", "500", "Magnet-hole diameter: Must be between 1 and 10."),
    ("classicbin", "magnetHoleDiameter", "0.5", "Magnet-hole diameter: Must be between 1 and 10."),
    ("classicbin", "magnetHoleDiameter", "NaN", "Magnet-hole diameter: Must be between 1 and 10."),
    ("classicbin", "magnetHoleDiameter", "Infinity", "Magnet-hole diameter: Must be between 1 and 10."),
    ("classicbin", "magnetHoleDiameter", "-Infinity", "Magnet-hole diameter: Must be between 1 and 10."),
    ("classicbin", "magnetHoleDiameter", "abc", "Magnet-hole diameter: Not a valid decimal value."),
    ("classicbin", "sizeUnitsX", "", "Width: Not a valid integer value."),
    ("solidbin", "sizeUnitsZ", "0", "Height: Must be between 1 and 12."),
    ("solidbin", "magnetHoleDiameter", "NaN", "Magnet-hole diameter: Must be between 1 and 10."),
    ("lightbin", "compartmentsX", "0", "Width direction: Must be between 1 and 24."),
    ("lightbin", "sizeUnitsY", "9", "Length: Must be between 1 and 6."),
    ("baseplate", "sizeUnitsX", "0", "Width: Must be between 1 and 6."),
    ("baseplate", "baseThickness", "0.5", "Base thickness: Must be between 1 and 10."),
    ("baseplate", "baseThickness", "NaN", "Base thickness: Must be between 1 and 10."),
    ("baseplate", "magnetHoleDiameter", "Infinity", "Magnet-hole diameter: Must be between 1 and 10."),
    ("holeybin", "numHolesX", "0", "# holes in width direction: Must be between 1 and 100."),
    ("holeybin", "numHolesY", "101", "# holes in length direction: Must be between 1 and 100."),
    ("holeybin", "holeDepth", "1000", "Depth: Must be between 1 and 200."),
    ("holeybin", "holeSize", "0", "Size: Must be between 1 and 100."),
    ("holeybin", "keepoutDiameter", "1", "Keepout diameter: Must be between 2 and 100."),
    ("holeybin", "keepoutDiameter", "NaN", "Keepout diameter: Must be between 2 and 100."),
]


@pytest.mark.parametrize("form_id, field, value, message", BAD_VALUES)
def test_out_of_range_input_is_refused_with_one_clear_reason(client, form_id, field, value, message):
    response = post_form(client, form_id, dimensions="true", **{field: value})

    assert response.status_code == 422, response.get_data(as_text=True)[:300]
    assert response.get_json()["errors"] == [message]


def test_refusal_is_shown_on_the_page_for_a_normal_submit(client, tmp_output):
    response = post_form(client, "classicbin", sizeUnitsX="0")

    assert response.status_code == 422
    assert "Width: Must be between 1 and 6." in response.get_data(as_text=True)
    assert list(tmp_output.iterdir()) == []  # and no model was built


def test_every_problem_in_a_form_is_reported_together(client):
    response = post_form(client, "classicbin", dimensions="true", sizeUnitsX="0", compartmentsY="99")

    assert set(response.get_json()["errors"]) == {
        "Width: Must be between 1 and 6.",
        "Length direction: Must be between 1 and 24.",
    }


def test_limits_are_also_published_to_the_browser(client):
    """One definition drives both the server's check and the input's min/max"""
    form = form_html(client, "classicbin")

    import re
    tag = re.search(r'<input[^>]*\bname="sizeUnitsX"[^>]*>', form).group(0)
    assert 'min="1"' in tag and 'max="6"' in tag


@pytest.mark.parametrize("form_id, overrides", [
    ("classicbin", dict(sizeUnitsX=1, sizeUnitsY=1, sizeUnitsZ=2, compartmentsX=1, compartmentsY=1, magnetHoleDiameter="1")),
    ("classicbin", dict(sizeUnitsX=6, sizeUnitsY=6, sizeUnitsZ=12, compartmentsX=6, compartmentsY=6, magnetHoleDiameter="10")),
    ("solidbin", dict(sizeUnitsX=1, sizeUnitsY=1, sizeUnitsZ=1, magnetHoleDiameter="1")),
    ("solidbin", dict(sizeUnitsX=6, sizeUnitsY=6, sizeUnitsZ=12, magnetHoleDiameter="10")),
    ("lightbin", dict(sizeUnitsX=6, sizeUnitsY=6, sizeUnitsZ=12, compartmentsX=6, compartmentsY=6)),
    ("baseplate", dict(sizeUnitsX=1, sizeUnitsY=1, baseThickness="1", magnetHoleDiameter="1")),
    ("baseplate", dict(sizeUnitsX=6, sizeUnitsY=6, baseThickness="10", magnetHoleDiameter="10")),
    ("holeybin", dict(numHolesX=1, numHolesY=1, holeDepth="1", holeSize="1", keepoutDiameter="2")),
])
def test_values_at_the_limits_are_accepted(client, form_id, overrides):
    response = post_form(client, form_id, dimensions="true", **overrides)

    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    assert isinstance(response.get_json(), list)


# ---------------------------------------------------------------- generators on their own

@pytest.mark.parametrize("name, fields", [
    ("classicbin", ["sizeUnitsX", "sizeUnitsY", "compartmentsX", "compartmentsY"]),
    ("lightbin", ["sizeUnitsX", "sizeUnitsY", "sizeUnitsZ", "compartmentsX", "compartmentsY"]),
    ("solidbin", ["sizeUnitsX", "sizeUnitsY", "sizeUnitsZ"]),
    ("baseplate", ["sizeUnitsX", "sizeUnitsY"]),
    ("holeybin", ["numHolesX", "numHolesY"]),
])
@pytest.mark.parametrize("bad", [0, -4])
def test_generators_survive_non_positive_counts(generators, name, fields, bad):
    """Defence in depth: a zero used to divide by zero while the generator was constructed"""
    import grid_constants
    module = generators[name]
    settings = module.settings.Settings()
    for field in fields:
        setattr(settings, field, bad)

    module.generator.Generator(settings, grid_constants.Grid())  # must not raise

    for field in fields:
        if field in ("sizeUnitsX", "sizeUnitsY", "numHolesX", "numHolesY") or name != "holeybin":
            assert getattr(settings, field) >= 1
