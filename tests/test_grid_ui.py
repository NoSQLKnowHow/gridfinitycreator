"""What the page says about the grid in use.

The Advanced settings change the grid, but the page used to carry on as if nothing had
happened: the preset menu always showed "Gridfinity", the help texts always said "42 mm / 7 mm",
and nothing told the user that a non-standard grid was active.
"""

import re

import pytest

import gridspec

RAACO_COOKIE = "39.5,54.5,7.0"


def page(client, cookie=None):
    if cookie is not None:
        client.set_cookie("gridspec", cookie)
    return client.get("/").get_data(as_text=True)


def preset_options(html):
    """(value, selected?) for each option of the preset menu"""
    menu = re.search(r'<select[^>]*id="grid-presets".*?</select>', html, re.DOTALL).group(0)
    return [(re.search(r'value="([^"]*)"', tag).group(1), re.search(r"\bselected\b", tag) is not None)
            for tag in re.findall(r"<option[^>]*>", menu)]


def selected_preset(html):
    selected = [value for value, is_selected in preset_options(html) if is_selected]
    assert len(selected) == 1, f"exactly one option must be selected, got {selected}"
    return selected[0]


# ---------------------------------------------------------------- presets are defined once

def test_the_presets_are_the_two_known_grids():
    assert {name: spec for name, *spec in gridspec.PRESETS} == {"Gridfinity": [42.0, 42.0, 7.0], "Raaco": [39.5, 54.5, 7.0]}


@pytest.mark.parametrize("spec, name", [
    ((42, 42, 7), "Gridfinity"),
    ((42.0, 42.0, 7.0), "Gridfinity"),
    ((39.5, 54.5, 7), "Raaco"),
    ((45, 45, 7), "Custom"),
    ((42, 42, 8), "Custom"),
    ((54.5, 39.5, 7), "Custom"),
])
def test_a_grid_is_named_after_the_preset_it_matches(spec, name):
    assert gridspec.preset_name(*spec) == name


# ---------------------------------------------------------------- the preset menu

def test_the_standard_grid_shows_gridfinity_selected(client):
    html = page(client)

    assert selected_preset(html) == "Gridfinity"
    assert "Custom" not in [value for value, _ in preset_options(html)]


def test_a_saved_raaco_grid_shows_raaco_selected(client):
    """The Gridfinity option had `selected` hard-coded, whatever was saved"""
    assert selected_preset(page(client, RAACO_COOKIE)) == "Raaco"


def test_a_grid_matching_no_preset_shows_custom_selected(client):
    html = page(client, "45.0,45.0,7.0")

    assert selected_preset(html) == "Custom"
    assert [value for value, _ in preset_options(html)] == ["Gridfinity", "Raaco", "Custom"]


def test_the_menu_carries_its_numbers_so_the_script_needs_none_of_its_own(client):
    html = page(client)

    assert re.search(r'<option[^>]*value="Raaco"[^>]*data-x="39.5"[^>]*data-y="54.5"[^>]*data-z="7"', html)
    assert 'document.getElementById("gridSizeX").value = "39.5"' not in html


# ---------------------------------------------------------------- help follows the grid

def test_help_and_descriptions_quote_the_grid_in_use(client):
    html = page(client, RAACO_COOKIE)

    assert "39.5mm" in html and "54.5mm" in html
    assert "42mm" not in html


def test_help_and_descriptions_quote_the_standard_grid_by_default(client):
    html = page(client)

    assert "42mm" in html
    assert "7mm" in html
    assert "39.5mm" not in html


def test_every_place_that_said_42_now_follows_the_grid(client):
    """Four descriptions and the size help hard-coded 42 mm / 7 mm"""
    html = page(client, "45.0,45.0,8.0")

    assert html.count("45mm") >= 5       # baseplate, classic, light, solid descriptions + size help
    assert "42mm" not in html
    assert "7mm" not in html


# ---------------------------------------------------------------- an indicator

def test_no_badge_on_the_standard_grid(client):
    assert "gfg-grid-badge" not in page(client)


def test_a_badge_names_the_active_non_standard_grid(client):
    html = page(client, RAACO_COOKIE)

    badge = re.search(r'<[^>]*gfg-grid-badge[^>]*>(.*?)</', html, re.DOTALL).group(1)
    assert "Raaco" in badge
    assert "39.5" in html[html.index("gfg-grid-badge"):html.index("gfg-grid-badge") + 400]


def test_a_custom_grid_badge_shows_the_sizes(client):
    html = page(client, "45.0,45.0,8.0")

    start = html.index("gfg-grid-badge")
    assert "Custom" in html[start:start + 300]
    assert "45" in html[start:start + 300]
