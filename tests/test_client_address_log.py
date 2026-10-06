"""Whether the visitor's address goes into the log (GFG_LOG_CLIENT_IP).

The log names the visitor's address for every model that is generated. In some places that is
personal data, so a deployment can choose not to keep it.
"""

import logging

import pytest

import gfg_main
from conftest import post_form

VISITOR = "192.168.1.50"


def address_for_log(environ):
    with gfg_main.app.test_request_context("/", environ_base={"REMOTE_ADDR": VISITOR}):
        return gfg_main.client_address_for_log(environ)


def test_the_address_is_logged_unless_told_otherwise():
    assert address_for_log({}) == VISITOR
    assert address_for_log({"GFG_LOG_CLIENT_IP": "true"}) == VISITOR
    assert address_for_log({"GFG_LOG_CLIENT_IP": ""}) == VISITOR


@pytest.mark.parametrize("value", ["false", "False", "0", "no", "off", " OFF "])
def test_the_address_can_be_left_out(value):
    assert address_for_log({"GFG_LOG_CLIENT_IP": value}) == "-"


def generation_logged(caplog, client):
    with caplog.at_level(logging.INFO, logger="GFG"):
        post_form(client, "solidbin", environ={"REMOTE_ADDR": VISITOR})
    return next(r.getMessage() for r in caplog.records if r.getMessage().startswith("Generating"))


def test_a_generation_is_logged_with_the_address_by_default(client, caplog):
    assert generation_logged(caplog, client).endswith(f"for: {VISITOR}")


def test_a_generation_is_logged_without_the_address_when_so_configured(client, caplog, monkeypatch):
    monkeypatch.setenv("GFG_LOG_CLIENT_IP", "false")

    line = generation_logged(caplog, client)

    assert line.endswith("for: -")
    assert VISITOR not in caplog.text
