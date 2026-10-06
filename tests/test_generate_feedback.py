"""Telling the page that its download has arrived.

Generate is an ordinary form submit and the answer is a file, so the page never navigates and the
browser tells it nothing when the response comes. The page therefore sends a random token with the
submit and watches for the server to hand it back in a cookie (static/generate_feedback.js). Only
then can it stop showing "Generating..." and let the user go again.
"""

import pytest

from conftest import post_form

TOKEN = "abcDEF123456_-xyz"


def cookies(response):
    return {c.split("=", 1)[0]: c for c in response.headers.getlist("Set-Cookie")}


def test_the_token_is_handed_back_in_a_cookie(client):
    response = post_form(client, "baseplate", dimensions="true", download_token=TOKEN)

    assert response.status_code == 200
    assert cookies(response)["download_token"].startswith(f"download_token={TOKEN};")


def test_it_is_handed_back_when_the_request_is_refused_too(client):
    """The page is replaced by the error page then, but a client that only looks at the cookie must not hang"""
    response = post_form(client, "baseplate", dimensions="true", download_token=TOKEN, sizeUnitsX="99")

    assert response.status_code == 422
    assert cookies(response)["download_token"].startswith(f"download_token={TOKEN};")


def test_the_cookie_is_readable_by_the_page_and_short_lived(client):
    cookie = cookies(post_form(client, "baseplate", dimensions="true", download_token=TOKEN))["download_token"]

    assert "HttpOnly" not in cookie              # the page has to read it
    assert "SameSite=Lax" in cookie
    assert "Path=/" in cookie
    assert "Max-Age=120" in cookie               # it is only needed for the length of a download


def test_no_token_means_no_cookie(client):
    response = post_form(client, "baseplate", dimensions="true")

    assert "download_token" not in cookies(response)


@pytest.mark.parametrize("bad", ["", "short", "has space in it", "semi;colon12345", "new\nline12345678", "x" * 65, "ünïcödé12345678"])
def test_a_token_that_is_not_a_plain_random_string_is_ignored(client, bad):
    """It goes into a response header, so it is never echoed unless it is a plain word"""
    response = post_form(client, "baseplate", dimensions="true", download_token=bad)

    assert "download_token" not in cookies(response)


def test_other_requests_are_left_alone(client):
    assert "download_token" not in cookies(client.get("/"))


def test_the_page_loads_the_script_that_uses_it(client):
    html = client.get("/").get_data(as_text=True)

    assert "/static/generate_feedback.js" in html
