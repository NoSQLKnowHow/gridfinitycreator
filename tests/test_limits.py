"""Limits that stop one request from monopolising the server.

These use the dimensions request: it constructs the generator (where the limits are
enforced) but builds no geometry, so the checks stay fast.
"""

import json

import pytest

from conftest import post_form
from generators.common import limits

BIG = dict(sizeUnitsX=6, sizeUnitsY=6, sizeUnitsZ=6)  # large enough to allow up to 24 compartments per side


def dimensions(client, form_id, **overrides):
    return post_form(client, form_id, dimensions="true", **overrides)


def walls(kind, indexes, other):
    """JSON for removed divider segments, in the format the layout editor stores"""
    return json.dumps([[kind, i, other] for i in indexes])


# ---------------------------------------------------------------- divider bin

def test_the_worst_legal_divider_bin_is_refused(client):
    """6 x 6 units with 24 x 24 compartments took over 7 minutes to build"""
    response = dimensions(client, "classicbin", compartmentsX=24, compartmentsY=24, **BIG)

    assert response.status_code == 422
    [message] = response.get_json()["errors"]
    assert "1104 divider wall segments" in message
    assert "limit of 300" in message
    assert "layout editor" in message


def test_the_limit_sits_between_12_and_13_compartments_per_side(client):
    ok = dimensions(client, "classicbin", compartmentsX=12, compartmentsY=12, **BIG)   # 264 segments
    refused = dimensions(client, "classicbin", compartmentsX=13, compartmentsY=13, **BIG)  # 312 segments

    assert ok.status_code == 200
    assert refused.status_code == 422


def test_removing_walls_in_the_layout_editor_brings_a_layout_back_under_the_limit(client):
    removed = walls("v", range(1, 13), 0) # 12 walls: 312 - 12 = 300 segments, exactly the limit
    ok = dimensions(client, "classicbin", compartmentsX=13, compartmentsY=13, removedWalls=removed, **BIG)
    still_too_many = dimensions(client, "classicbin", compartmentsX=13, compartmentsY=13,
                                removedWalls=walls("v", range(1, 12), 0), **BIG)  # 11 removed -> 301

    assert ok.status_code == 200
    assert still_too_many.status_code == 422


@pytest.mark.parametrize("removed", [
    "not json at all",
    json.dumps([["v", 99, 0]] * 50),      # out of range: ignored
    json.dumps([["v", 1, 0]] * 50),       # the same segment repeated: counts once
    json.dumps([["x", 1, 0], [1, 2], "v", None]),
])
def test_junk_in_removed_walls_cannot_dodge_the_limit(client, removed):
    response = dimensions(client, "classicbin", compartmentsX=13, compartmentsY=13, removedWalls=removed, **BIG)

    assert response.status_code == 422


def test_light_bin_has_a_lower_limit_because_each_segment_costs_more(client):
    ok = dimensions(client, "lightbin", compartmentsX=9, compartmentsY=9, **BIG)         # 144 segments
    refused = dimensions(client, "lightbin", compartmentsX=10, compartmentsY=10, **BIG)  # 180 segments

    assert ok.status_code == 200
    assert refused.status_code == 422
    assert "limit of 150" in refused.get_json()["errors"][0]


def test_limits_can_be_changed_through_the_environment(client, monkeypatch):
    layout = dict(compartmentsX=6, compartmentsY=6, **BIG)  # 60 segments
    assert dimensions(client, "classicbin", **layout).status_code == 200

    monkeypatch.setenv("GFG_MAX_DIVIDER_SEGMENTS", "50")
    refused = dimensions(client, "classicbin", **layout)

    assert refused.status_code == 422
    assert "limit of 50" in refused.get_json()["errors"][0]


@pytest.mark.parametrize("junk", ["", "abc", "0", "-5", "1.5"])
def test_an_unusable_environment_value_falls_back_to_the_default(monkeypatch, junk):
    monkeypatch.setenv("GFG_MAX_DIVIDER_SEGMENTS", junk)

    assert limits.max_divider_segments() == limits.DEFAULT_MAX_DIVIDER_SEGMENTS


def test_segment_counting():
    assert limits.divider_segment_count(1, 1) == 0
    assert limits.divider_segment_count(2, 1) == 1
    assert limits.divider_segment_count(3, 3) == 12          # 2 * 3 * 2
    assert limits.divider_segment_count(12, 12) == 264       # 2 * 12 * 11
    assert limits.divider_segment_count(3, 3, removed_walls=[("v", 1, 0)] * 2) == 10


# ---------------------------------------------------------------- holey bin

def test_a_hole_grid_that_needs_an_oversized_bin_is_refused(client):
    """The size cap used to be silently undone, so 100 x 100 holes built a 29-unit bin"""
    response = dimensions(client, "holeybin", numHolesX=30, numHolesY=3)  # needs 9 x 1 units at 12 mm keepout

    assert response.status_code == 422
    [message] = response.get_json()["errors"]
    assert "9 × 1 grid units" in message
    assert "largest allowed is 6 × 6" in message


def test_a_hole_that_is_too_deep_for_the_tallest_bin_is_refused(client):
    response = dimensions(client, "holeybin", holeDepth="100")  # 1 + ceil(100 / 7) = 16 height units

    assert response.status_code == 422
    [message] = response.get_json()["errors"]
    assert "16 height units" in message
    assert "maximum hole depth is 77 mm" in message


def test_too_many_holes_are_refused(client):
    response = dimensions(client, "holeybin", numHolesX=25, numHolesY=25, keepoutDiameter="2", holeSize="1")

    assert response.status_code == 422
    assert "625 holes is more than the limit of 600" in response.get_json()["errors"][0]


def test_a_large_hole_grid_that_fits_is_accepted(client):
    response = dimensions(client, "holeybin", numHolesX=20, numHolesY=20)  # 6 x 6 units, 400 holes

    assert response.status_code == 200


def test_the_size_limit_follows_the_configured_grid(client):
    """The check depends on the grid in use, which is why it lives in the generator"""
    client.set_cookie("gridspec", "30.0,30.0,7.0")  # a smaller pitch needs more units for the same holes

    response = dimensions(client, "holeybin", numHolesX=20, numHolesY=20)

    assert response.status_code == 422
    assert "largest allowed is 6 × 6" in response.get_json()["errors"][0]
