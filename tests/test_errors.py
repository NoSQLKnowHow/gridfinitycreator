"""What the user is told when a request cannot be fulfilled."""

import logging
import re

import pytest

import gfg_main
from conftest import post_form
from generators.common.errors import SettingsError


def tab_is_active(html, tab_id):
    """Whether the tab pane with this id is rendered as the open one"""
    pane = re.search(rf'<div id="{tab_id}" class="([^"]*)"', html).group(1)
    return "active" in pane.split()


def test_invalid_field_is_explained_on_the_submitted_tab(client):
    """A rejected form used to reload the page on the Home tab with no message at all"""
    response = post_form(client, "classicbin", sizeUnitsX="abc")
    html = response.get_data(as_text=True)

    assert response.status_code == 422
    assert "Width: Not a valid integer value." in html
    assert tab_is_active(html, "classicbin")
    assert not tab_is_active(html, "home")


def test_submitted_values_are_kept_so_the_user_can_correct_them(client):
    html = post_form(client, "classicbin", sizeUnitsX="abc", compartmentsX="5").get_data(as_text=True)

    assert 'value="abc"' in html
    assert 'value="5"' in html


def test_background_requests_get_json_errors(client):
    """The page's own scripts post for the dimensions readout and the preview"""
    for flag in ("dimensions", "preview"):
        response = post_form(client, "classicbin", sizeUnitsX="abc", **{flag: "true"})

        assert response.status_code == 422
        assert response.is_json
        assert response.get_json()["errors"] == ["Width: Not a valid integer value."]


def test_a_bad_csrf_token_gets_a_plain_explanation(client):
    response = post_form(client, "classicbin", token="not-a-real-token")

    assert response.status_code == 422
    assert gfg_main.STALE_PAGE_MESSAGE in response.get_data(as_text=True)


def test_csrf_tokens_do_not_expire_after_an_hour(client):
    """Anonymous, stateless app: the expiry only made forgotten tabs fail"""
    assert gfg_main.app.config["WTF_CSRF_TIME_LIMIT"] is None


def test_invalid_grid_settings_are_explained_on_the_home_tab(client):
    response = client.post("/", data=dict(advanced_settings="Save", gridSizeX="abc", gridSizeY="42", gridSizeZ="7"))
    html = response.get_data(as_text=True)

    assert response.status_code == 422
    assert "Grid size X must be a number." in html
    assert tab_is_active(html, "home")


def test_settings_errors_raised_by_a_generator_are_shown_escaped(client, generators, monkeypatch):
    def refuse(form, constants):
        raise SettingsError("<b>Too big</b> & more")

    monkeypatch.setattr(generators["classicbin"], "process", refuse)
    response = post_form(client, "classicbin")
    html = response.get_data(as_text=True)

    assert response.status_code == 422
    assert "&lt;b&gt;Too big&lt;/b&gt; &amp; more" in html  # the message is data, never markup
    assert "<b>Too big</b>" not in html
    assert tab_is_active(html, "classicbin")


def test_unexpected_failures_get_a_friendly_page_without_leaking_details(client, generators, monkeypatch, caplog):
    def explode(form, constants):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(generators["classicbin"], "process", explode)
    with caplog.at_level(logging.ERROR):
        response = post_form(client, "classicbin")
    html = response.get_data(as_text=True)

    assert response.status_code == 500
    assert gfg_main.UNEXPECTED_ERROR_MESSAGE in html
    assert "secret internal detail" not in html
    assert tab_is_active(html, "classicbin")
    assert "secret internal detail" in caplog.text  # ...but it is in the server log


def test_unexpected_failures_in_background_requests_get_json(client, generators, monkeypatch):
    def explode(form, constants):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(generators["classicbin"], "process", explode)
    response = post_form(client, "classicbin", preview="true")

    assert response.status_code == 500
    assert response.get_json() == {"errors": [gfg_main.UNEXPECTED_ERROR_MESSAGE]}


def test_ordinary_http_errors_keep_their_normal_responses(client):
    assert client.get("/no-such-page").status_code == 404
    assert client.put("/").status_code == 405
