"""Baseline behaviour: the app serves its page and every generator builds a sound model."""

import os

import pytest

import grid_constants
from conftest import post_form, solid_count

GENERATORS = ["baseplate", "classicbin", "holeybin", "lightbin", "solidbin"]
TITLES = ["Baseplate", "Divider bin", "Holey bin", "Light bin", "Solid bin"]


def test_home_page_lists_every_generator(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    for title in TITLES:
        assert title in html


@pytest.mark.parametrize("name", GENERATORS)
def test_default_model_is_one_valid_solid(generators, name):
    module = generators[name]
    settings = module.settings.Settings()
    grid = grid_constants.Grid()
    shape = module.generator.Generator(settings, grid).generate_model()

    assert shape.val().isValid()
    assert solid_count(shape) == 1


@pytest.mark.parametrize("name", ["baseplate", "solidbin"])
def test_form_post_downloads_a_file_and_cleans_up(client, tmp_output, name):
    response = post_form(client, name)

    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]
    assert len(response.data) > 1000
    # The temporary file is removed once the response has been sent
    assert os.listdir(tmp_output) == []
