"""The grid specification cookie and the Advanced settings form."""

import pytest

import gridspec
from conftest import input_value

BAD_COOKIES = [
    "abc", "42,42", "1,2,3,4", "42,42,7,", ",,", "42,42,seven",
    "nan,nan,nan", "inf,42,7", "-inf,42,7", "0,0,0", "-5,42,7", "1e9,42,7", "19.9,42,7", "42,42,2.9",
]


# ---------------------------------------------------------------- the parser itself

def test_standard_and_raaco_grids_are_accepted():
    assert gridspec.parse_cookie("42.0,42.0,7.0") == (42.0, 42.0, 7.0)
    assert gridspec.parse_cookie("39.5,54.5,7.0") == (39.5, 54.5, 7.0)


@pytest.mark.parametrize("raw", BAD_COOKIES + ["", None])
def test_unusable_cookies_parse_to_none(raw):
    assert gridspec.parse_cookie(raw) is None


def test_range_limits_are_inclusive():
    assert gridspec.validate(["20", "150", "3"]) == (20.0, 150.0, 3.0)
    assert gridspec.validate(["150", "20", "20"]) == (150.0, 20.0, 20.0)


@pytest.mark.parametrize("values, label", [
    (["abc", "42", "7"], "Grid size X"),
    (["42", "", "7"], "Grid size Y"),
    (["42", "42", None], "Height unit"),
    (["nan", "42", "7"], "Grid size X"),
    (["42", "inf", "7"], "Grid size Y"),
    (["42", "42", "0"], "Height unit"),
    (["19.99", "42", "7"], "Grid size X"),
    (["42", "150.01", "7"], "Grid size Y"),
])
def test_validate_names_the_offending_field(values, label):
    with pytest.raises(gridspec.GridSpecError, match=label):
        gridspec.validate(values)


# ---------------------------------------------------------------- the web behaviour

@pytest.mark.parametrize("raw", BAD_COOKIES)
def test_damaged_cookie_does_not_break_the_home_page(client, raw):
    """Any damaged gridspec cookie used to turn the whole site into a 500"""
    client.set_cookie("gridspec", raw)

    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    shown = [float(input_value(html, i)) for i in ("gridSizeX", "gridSizeY", "gridSizeZ")]
    assert shown == [42.0, 42.0, 7.0]                                # fell back to the standard grid
    assert "gridspec=" in response.headers.get("Set-Cookie", "")     # and repaired the cookie


def test_valid_cookie_is_honoured(client):
    client.set_cookie("gridspec", "39.5,54.5,7.0")

    html = client.get("/").get_data(as_text=True)

    assert input_value(html, "gridSizeX") == "39.5"
    assert input_value(html, "gridSizeY") == "54.5"


def test_saving_advanced_settings_sets_a_durable_cookie(client):
    response = client.post("/", data=dict(advanced_settings="Save", gridSizeX="39.5", gridSizeY="54.5", gridSizeZ="7"))

    assert response.status_code == 200
    cookie = response.headers["Set-Cookie"]
    assert cookie.startswith("gridspec=")
    assert "Max-Age=31536000" in cookie
    assert "SameSite=Lax" in cookie
    assert "HttpOnly" in cookie


@pytest.mark.parametrize("form, message", [
    (dict(gridSizeX="abc", gridSizeY="42", gridSizeZ="7"), "Grid size X must be a number"),
    (dict(gridSizeX="42", gridSizeY="42"), "Height unit must be a number"),   # field missing entirely
    (dict(gridSizeX="nan", gridSizeY="42", gridSizeZ="7"), "Grid size X must be between"),
    (dict(gridSizeX="0", gridSizeY="42", gridSizeZ="7"), "Grid size X must be between"),
    (dict(gridSizeX="42", gridSizeY="1e9", gridSizeZ="7"), "Grid size Y must be between"),
    (dict(gridSizeX="42", gridSizeY="42", gridSizeZ="-1"), "Height unit must be between"),
])
def test_invalid_advanced_settings_are_rejected_with_a_reason(client, form, message):
    response = client.post("/", data=dict(advanced_settings="Save", **form))

    assert response.status_code == 422
    assert message in response.get_data(as_text=True)
    assert "gridspec=" not in response.headers.get("Set-Cookie", "")  # nothing was saved
