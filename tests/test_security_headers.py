"""The security headers every response carries (SEC-6), and what the page has to be like for them.

The Content-Security-Policy lets the page run scripts and load styles, fonts, images and data from this
server only. That is only workable because the page is clean: no inline scripts or handlers (see
test_no_inline_code.py), no inline styles, no other host. Those are tested here, next to the policy
that depends on them, together with a real browser's verdict recorded in the commit that added it.
"""

import glob
import os
import re
import subprocess
import sys

import pytest
from werkzeug.wrappers import Response

import gfg_main
import proxy_trust
import security_headers
from conftest import REPO, post_form
from test_no_inline_code import FIRST_PARTY_SCRIPTS, TEMPLATE_SOURCES, without_comments

POLICY = security_headers.CONTENT_SECURITY_POLICY


def directives(policy):
    """{"script-src": ["'self'"], ...}"""
    return {parts[0]: parts[1:] for parts in (part.split() for part in policy.split(";")) if parts}


# ---------------------------------------------------------------- every response carries them

def a_page(client):
    return client.get("/")


def a_script(client):
    return client.get("/static/page.js")


def a_stylesheet(client):
    return client.get("/static/theme.css")


def a_missing_page(client):
    return client.get("/nothing-here")


def a_wrong_method(client):
    return client.put("/")


def a_dimensions_readout(client):
    return post_form(client, "classicbin", dimensions="true")


def a_refused_form(client):
    return post_form(client, "classicbin", sizeUnitsX="0")


def a_download(client):
    return post_form(client, "solidbin")


RESPONSES = [a_page, a_script, a_stylesheet, a_missing_page, a_wrong_method, a_dimensions_readout, a_refused_form, a_download]


@pytest.mark.parametrize("request_it", RESPONSES, ids=lambda f: f.__name__)
def test_every_kind_of_response_carries_the_headers(client, request_it):
    response = request_it(client)

    for name, value in security_headers.HEADERS.items():
        assert response.headers.get(name) == value, (name, response.status_code)


def test_the_kinds_of_response_are_what_they_say_they_are(client):
    assert [f(client).status_code for f in RESPONSES] == [200, 200, 200, 404, 405, 200, 422, 200]


def test_a_header_a_route_set_itself_is_left_alone():
    response = Response("x", headers={"Content-Security-Policy": "default-src 'none'"})

    assert security_headers.apply(response, secure=False).headers["Content-Security-Policy"] == "default-src 'none'"


# ---------------------------------------------------------------- the policy

def test_scripts_come_from_this_server_only():
    assert directives(POLICY)["script-src"] == ["'self'"]


def test_nothing_is_allowed_that_the_page_does_not_need():
    allowed = {"'self'", "'none'", "data:"}

    for name, sources in directives(POLICY).items():
        assert set(sources) <= allowed, name
    assert "unsafe" not in POLICY
    assert directives(POLICY)["img-src"] == ["'self'", "data:"]     # for Bootstrap's icons, which are data URIs
    assert [n for n, s in directives(POLICY).items() if "data:" in s] == ["img-src"]


def test_everything_else_defaults_to_this_server():
    assert directives(POLICY)["default-src"] == ["'self'"]


def test_plugins_framing_base_tags_and_foreign_form_targets_are_ruled_out():
    found = directives(POLICY)

    assert found["object-src"] == ["'none'"]
    assert found["frame-ancestors"] == ["'none'"]
    assert found["base-uri"] == ["'none'"]
    assert found["form-action"] == ["'self'"]


def test_an_instance_on_a_private_network_is_not_forced_onto_https():
    assert "upgrade-insecure-requests" not in POLICY


def test_the_referrer_is_still_sent_to_this_server():
    """Over https Flask-WTF checks the Referer of a form submit against the host, so no-referrer would break it"""
    assert security_headers.HEADERS["Referrer-Policy"] == "same-origin"


# ---------------------------------------------------------------- what the page has to be like for it

def test_the_page_has_no_inline_styles(client):
    html = without_comments(client.get("/").get_data(as_text=True))

    assert not re.search(r"<[a-zA-Z][^<>]*?\sstyle\s*=", html)
    assert not re.search(r"<style\b", html, re.IGNORECASE)


@pytest.mark.parametrize("path", TEMPLATE_SOURCES, ids=lambda p: os.path.relpath(p, REPO))
def test_no_template_has_inline_styles(path):
    with open(path, encoding="utf-8") as handle:
        markup = without_comments(handle.read())

    assert not re.search(r"<[a-zA-Z][^<>]*?\sstyle\s*=", markup)
    assert not re.search(r"<style\b", markup, re.IGNORECASE)


@pytest.mark.parametrize("path", FIRST_PARTY_SCRIPTS, ids=lambda p: os.path.basename(p))
def test_no_script_builds_inline_styles(path):
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    code = "\n".join(line for line in code.splitlines() if not line.lstrip().startswith("//"))

    assert not re.search(r"\sstyle\s*=\s*[\"']", code)
    assert not re.search(r"setAttribute\(\s*[\"']style[\"']", code)


def test_the_page_loads_nothing_from_another_host(client):
    html = client.get("/").get_data(as_text=True)

    assert not re.search(r"<(?:script|link|img|source|iframe)\b[^>]*\b(?:src|href)\s*=\s*[\"']?(?:https?:)?//", html, re.IGNORECASE)


@pytest.mark.parametrize("path", glob.glob(os.path.join(REPO, "static", "**", "*.css"), recursive=True),
                         ids=lambda p: os.path.relpath(p, REPO))
def test_no_stylesheet_loads_anything_from_another_host(path):
    with open(path, encoding="utf-8") as handle:
        css = handle.read()

    assert not re.search(r"url\(\s*[\"']?(?:https?:)?//", css)
    assert not re.search(r"@import\s+(?:url\()?[\"']?(?:https?:)?//", css)


# ---------------------------------------------------------------- strict transport security

HTTPS = "https://localhost"


def hsts(client, base_url, **kwargs):
    return client.get("/", base_url=base_url, **kwargs).headers.get("Strict-Transport-Security")


def test_hsts_is_not_sent_unless_asked_for(client):
    assert hsts(client, HTTPS) is None


def test_hsts_is_sent_over_https_when_configured(client, monkeypatch):
    monkeypatch.setattr(gfg_main, "HSTS_MAX_AGE", 3600)

    assert hsts(client, HTTPS) == "max-age=3600"


def test_hsts_is_never_sent_over_plain_http(client, monkeypatch):
    """A browser ignores it there, and a header that says "https only" on an http answer is a configuration mistake"""
    monkeypatch.setattr(gfg_main, "HSTS_MAX_AGE", 3600)

    assert hsts(client, "http://localhost") is None


@pytest.fixture()
def behind_proxy():
    middleware = gfg_main.app.wsgi_app
    before = (middleware.trusted, middleware.hops)
    middleware.configure(proxy_trust.parse_proxies("172.18.0.0/16"))
    yield
    middleware.configure(*before)


def test_behind_a_trusted_proxy_that_says_https_hsts_is_sent(client, behind_proxy, monkeypatch):
    monkeypatch.setattr(gfg_main, "HSTS_MAX_AGE", 3600)

    assert hsts(client, "http://localhost", headers={"X-Forwarded-Proto": "https"},
                environ_overrides={"REMOTE_ADDR": "172.18.0.2"}) == "max-age=3600"


def test_a_visitor_cannot_get_it_by_claiming_https(client, behind_proxy, monkeypatch):
    monkeypatch.setattr(gfg_main, "HSTS_MAX_AGE", 3600)

    assert hsts(client, "http://localhost", headers={"X-Forwarded-Proto": "https"},
                environ_overrides={"REMOTE_ADDR": "192.168.1.50"}) is None


def test_the_setting_is_a_number_of_seconds():
    assert security_headers.parse_hsts_max_age(None) == 0
    assert security_headers.parse_hsts_max_age("") == 0
    assert security_headers.parse_hsts_max_age("0") == 0
    assert security_headers.parse_hsts_max_age(" 15552000 ") == 15552000


@pytest.mark.parametrize("text", ["-1", "a year", "1.5"])
def test_a_setting_that_is_not_a_number_of_seconds_stops_the_server(text):
    with pytest.raises(ValueError, match="GFG_HSTS_MAX_AGE"):
        security_headers.parse_hsts_max_age(text)


def test_a_bad_setting_stops_the_server_from_starting():
    result = subprocess.run([sys.executable, "-c", "import gfg_main"], cwd=REPO, capture_output=True, text=True,
                            env={**os.environ, "GFG_HSTS_MAX_AGE": "forever"})

    assert result.returncode != 0
    assert "ValueError: GFG_HSTS_MAX_AGE:" in result.stderr
