"""Which X-Forwarded-* headers the app believes (SEC-8).

A reverse proxy tells the app who the visitor was and whether they used https in these headers.
They must be believed from the proxy and from nobody else: the app used to believe them from
anyone (X-Forwarded-Prefix even reached it through Waitress, which otherwise discards the headers),
and, when Waitress did discard them, a real proxy's were discarded too, so behind Traefik the log
showed the proxy's address and the cookies were never marked Secure.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import urllib.request

import pytest
import waitress
from werkzeug.test import EnvironBuilder

import gfg_main
import proxy_trust
from conftest import CSRF_PATTERN, DEFAULT_PAYLOADS, REPO, post_form

PROXY = "172.18.0.2"
VISITOR = "203.0.113.9"
NETWORK = proxy_trust.parse_proxies("172.18.0.0/16")
FORGED = {"X-Forwarded-For": "6.6.6.6", "X-Forwarded-Proto": "https", "X-Forwarded-Host": "evil.example",
          "X-Forwarded-Prefix": "/evil", "X-Forwarded-Port": "8443", "X-Forwarded-By": "6.6.6.6",
          "Forwarded": "for=6.6.6.6;proto=https"}
FORWARDING_KEYS = ("HTTP_X_FORWARDED_FOR", "HTTP_X_FORWARDED_PROTO", "HTTP_X_FORWARDED_HOST", "HTTP_X_FORWARDED_PREFIX",
                   "HTTP_X_FORWARDED_PORT", "HTTP_X_FORWARDED_BY", "HTTP_FORWARDED")


def echo(environ, start_response):
    """An app that reports what it was told about the request"""
    body = json.dumps({
        "addr": environ.get("REMOTE_ADDR"),
        "scheme": environ["wsgi.url_scheme"],
        "host": environ.get("HTTP_HOST"),
        "script": environ.get("SCRIPT_NAME"),
        "left": sorted(key for key in FORWARDING_KEYS if key in environ),
    }).encode()
    start_response("200 OK", [("Content-Type", "application/json")])
    return [body]


def see(trust, peer, headers):
    """What the app behind `trust` sees of a request that arrives from `peer` with these headers"""
    environ = EnvironBuilder(path="/", headers=headers, base_url="http://app.local").get_environ()
    environ["REMOTE_ADDR"] = peer
    return json.loads(b"".join(trust(environ, lambda *args: None)))


# ---------------------------------------------------------------- the settings

def test_no_setting_means_no_proxy_is_trusted():
    assert proxy_trust.parse_proxies(None) == ()
    assert proxy_trust.parse_proxies("") == ()
    assert proxy_trust.parse_proxies(" , ") == ()


def test_addresses_and_networks_can_be_listed():
    networks = proxy_trust.parse_proxies(" 172.18.0.2 ,10.0.0.0/8, fd00::/8 ")

    assert [str(n) for n in networks] == ["172.18.0.2/32", "10.0.0.0/8", "fd00::/8"]


def test_a_host_address_with_a_prefix_length_names_its_network():
    assert [str(n) for n in proxy_trust.parse_proxies("172.18.0.5/16")] == ["172.18.0.0/16"]


def test_a_typo_stops_the_server_instead_of_being_ignored():
    with pytest.raises(ValueError, match=r"GFG_TRUSTED_PROXIES.*'traefik'.*not an IP address"):
        proxy_trust.parse_proxies("172.18.0.2, traefik")


def test_the_hop_count_defaults_to_one():
    assert proxy_trust.parse_hops(None) == 1
    assert proxy_trust.parse_hops("") == 1
    assert proxy_trust.parse_hops("2") == 2


@pytest.mark.parametrize("text", ["0", "-1", "two", "1.5"])
def test_a_hop_count_that_makes_no_sense_stops_the_server(text):
    with pytest.raises(ValueError, match="GFG_PROXY_HOPS"):
        proxy_trust.parse_hops(text)


def test_waitress_is_only_told_to_pass_the_headers_on_when_there_is_a_proxy_to_believe():
    assert proxy_trust.server_options(()) == {}
    assert proxy_trust.server_options(NETWORK) == {"clear_untrusted_proxy_headers": False}


def test_the_production_server_is_started_with_those_options():
    """Left out, Waitress would discard a trusted proxy's headers before the app could look at them"""
    with open(os.path.join(REPO, "gfg_main.py"), encoding="utf-8") as handle:
        source = handle.read()

    [call] = [line for line in source.splitlines() if "waitress.serve(" in line]
    assert "**proxy_trust.server_options(trusted_proxies)" in call


@pytest.mark.parametrize("setting, value", [("GFG_TRUSTED_PROXIES", "traefik"), ("GFG_PROXY_HOPS", "0")])
def test_a_bad_setting_stops_the_server_from_starting(setting, value):
    """The README promises it: a proxy that was meant to be trusted and is not would only show as wrong addresses"""
    result = subprocess.run([sys.executable, "-c", "import gfg_main"], cwd=REPO, capture_output=True, text=True,
                            env={**os.environ, setting: value})

    assert result.returncode != 0
    assert f"ValueError: {setting}:" in result.stderr


# ---------------------------------------------------------------- the middleware

def test_without_a_trusted_proxy_nobodys_headers_are_believed():
    seen = see(proxy_trust.ProxyTrust(echo), PROXY, FORGED)

    assert seen["addr"] == PROXY
    assert seen["scheme"] == "http"
    assert seen["host"] == "app.local"
    assert seen["script"] == ""


def test_headers_nobody_believes_do_not_reach_the_app_at_all():
    """So nothing downstream can mistake them for something that was checked"""
    assert see(proxy_trust.ProxyTrust(echo), PROXY, FORGED)["left"] == []


def test_a_trusted_proxys_headers_are_believed():
    seen = see(proxy_trust.ProxyTrust(echo, NETWORK), PROXY, {
        "X-Forwarded-For": VISITOR, "X-Forwarded-Proto": "https", "X-Forwarded-Host": "gridfinity.example.com"})

    assert seen["addr"] == VISITOR
    assert seen["scheme"] == "https"
    assert seen["host"] == "gridfinity.example.com"


def test_a_visitor_who_reaches_the_app_directly_is_not_a_proxy():
    seen = see(proxy_trust.ProxyTrust(echo, NETWORK), "192.168.1.50", FORGED)

    assert (seen["addr"], seen["scheme"], seen["host"], seen["left"]) == ("192.168.1.50", "http", "app.local", [])


@pytest.mark.parametrize("peer, listed, trusted", [
    ("172.18.0.2", "172.18.0.2", True),
    ("172.18.0.3", "172.18.0.2", False),
    ("172.18.200.9", "172.18.0.0/16", True),
    ("172.19.0.1", "172.18.0.0/16", False),
    ("::ffff:172.18.0.2", "172.18.0.2", True),          # an IPv4 peer, as an IPv6 socket reports it
    ("fd00::5", "fd00::/8", True),
    ("fd00::5", "172.18.0.0/16", False),                # families do not mix
    ("172.18.0.2", "fd00::/8", False),
    ("", "172.18.0.0/16", False),                       # no peer address at all
    ("not an address", "172.18.0.0/16", False),
])
def test_the_peer_is_matched_against_the_listed_addresses_and_networks(peer, listed, trusted):
    trust = proxy_trust.ProxyTrust(echo, proxy_trust.parse_proxies(listed))

    assert trust.is_trusted(peer) is trusted


def test_the_path_prefix_is_never_believed_not_even_from_a_trusted_proxy():
    """The app does not run under a prefix; and Waitress, unlike for the others, lets this one through"""
    seen = see(proxy_trust.ProxyTrust(echo, NETWORK), PROXY, {"X-Forwarded-For": VISITOR, **FORGED})

    assert seen["script"] == ""
    # nor do the headers nobody uses stay around (the three that were used are left as they came)
    assert set(seen["left"]) == {"HTTP_X_FORWARDED_FOR", "HTTP_X_FORWARDED_PROTO", "HTTP_X_FORWARDED_HOST"}


def test_what_the_visitor_wrote_into_the_chain_is_not_believed():
    """The proxy adds the address it saw to the end of X-Forwarded-For; a visitor can only add to the front"""
    seen = see(proxy_trust.ProxyTrust(echo, NETWORK), PROXY, {"X-Forwarded-For": f"6.6.6.6, {VISITOR}"})

    assert seen["addr"] == VISITOR


def test_with_two_proxies_the_count_says_how_far_back_to_believe():
    cdn = "198.51.100.7"                                # what the second proxy saw: the first one
    chain = {"X-Forwarded-For": f"6.6.6.6, {VISITOR}, {cdn}"}
    trust = proxy_trust.ProxyTrust(echo, proxy_trust.parse_proxies(cdn), hops=2)

    assert see(trust, cdn, chain)["addr"] == VISITOR
    assert see(proxy_trust.ProxyTrust(echo, proxy_trust.parse_proxies(cdn), hops=1), cdn, chain)["addr"] == cdn


def test_a_request_without_headers_passes_through_unchanged():
    seen = see(proxy_trust.ProxyTrust(echo, NETWORK), PROXY, {})

    assert (seen["addr"], seen["scheme"], seen["host"]) == (PROXY, "http", "app.local")


def test_the_setting_can_be_changed_afterwards():
    trust = proxy_trust.ProxyTrust(echo)
    trust.configure(NETWORK)

    assert see(trust, PROXY, {"X-Forwarded-For": VISITOR})["addr"] == VISITOR


# ---------------------------------------------------------------- the real application

@pytest.fixture()
def behind_proxy():
    """Make the application trust 172.18.0.0/16 for the length of a test"""
    middleware = gfg_main.app.wsgi_app
    before = (middleware.trusted, middleware.hops)
    middleware.configure(NETWORK)
    yield
    middleware.configure(*before)


def download_cookie(client, peer, headers):
    """The Set-Cookie header the app answers a form submit with (it echoes the page's download token)"""
    response = client.post("/", data={"download_token": "token12345"}, headers=headers,
                           environ_overrides={"REMOTE_ADDR": peer})
    return next(c for c in response.headers.getlist("Set-Cookie") if c.startswith("download_token="))


def test_the_application_trusts_nobody_by_default(client):
    assert gfg_main.app.wsgi_app.trusted == ()


def test_a_spoofed_scheme_does_not_make_cookies_secure(client):
    """Marked Secure on a plain-http connection, the browser would drop the cookie"""
    assert "Secure" not in download_cookie(client, "192.168.1.50", {"X-Forwarded-Proto": "https"})


def test_behind_a_trusted_proxy_cookies_are_secure_when_the_visitor_used_https(client, behind_proxy):
    assert "Secure" in download_cookie(client, PROXY, {"X-Forwarded-Proto": "https"})
    assert "Secure" not in download_cookie(client, PROXY, {"X-Forwarded-Proto": "http"})


def test_a_form_still_submits_behind_a_proxy_that_terminates_https(client, behind_proxy):
    """Flask-WTF checks the Referer of an https submit against the host. The proxy asks the app for
       its internal name and says in X-Forwarded-Host what the visitor typed, so that has to be believed."""
    public = "gridfinity.example.com"
    internal = "http://cadquery:5000"
    headers = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": public, "X-Forwarded-For": VISITOR,
               "Referer": f"https://{public}/"}
    peer = {"REMOTE_ADDR": PROXY}
    page = client.get("/", base_url=internal, headers=headers, environ_overrides=peer)
    payload = dict(DEFAULT_PAYLOADS["solidbin"], solidbin="Generate", dimensions="true",
                   csrf_token=CSRF_PATTERN.search(page.get_data(as_text=True)).group(1))

    response = client.post("/", data=payload, base_url=internal, headers=headers, environ_overrides=peer)

    assert response.status_code == 200, response.get_data(as_text=True)[:300]


def logged_visitor(caplog, client, peer, headers):
    """The address the app logs for a generation requested from `peer` with these headers"""
    with caplog.at_level(logging.INFO, logger="GFG"):
        post_form(client, "solidbin", headers=headers, environ={"REMOTE_ADDR": peer})
    return next(r.getMessage() for r in caplog.records if r.getMessage().startswith("Generating"))


def test_the_log_names_the_visitor_not_what_the_visitor_claims(client, caplog):
    line = logged_visitor(caplog, client, "192.168.1.50", {"X-Forwarded-For": "6.6.6.6"})

    assert line.endswith("for: 192.168.1.50")


def test_behind_a_trusted_proxy_the_log_names_the_visitor_not_the_proxy(client, caplog, behind_proxy):
    line = logged_visitor(caplog, client, PROXY, {"X-Forwarded-For": VISITOR})

    assert line.endswith(f"for: {VISITOR}")


# ---------------------------------------------------------------- through a real Waitress

@pytest.fixture()
def serve():
    """Start Waitress on a free port around a proxy-trusting app that reports what it sees"""
    servers = []

    def start(trusted):
        server = waitress.create_server(proxy_trust.ProxyTrust(echo, trusted), host="127.0.0.1", port=0,
                                        **proxy_trust.server_options(trusted))
        threading.Thread(target=server.run, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.effective_port}/"

    yield start
    for server in servers:
        server.close()


def ask(url, headers):
    direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # whatever http_proxy says
    with direct.open(urllib.request.Request(url, headers=headers), timeout=10) as response:
        return json.load(response)


def test_waitress_passes_a_forged_prefix_to_the_app_and_the_app_does_not_believe_it(serve):
    seen = ask(serve(()), FORGED)

    assert seen["addr"] == "127.0.0.1"
    assert seen["scheme"] == "http"
    assert seen["script"] == ""
    assert seen["left"] == []


def test_a_proxy_named_in_the_setting_is_believed_through_waitress(serve):
    seen = ask(serve(proxy_trust.parse_proxies("127.0.0.1")), {**FORGED, "X-Forwarded-For": VISITOR})

    assert seen["addr"] == VISITOR
    assert seen["scheme"] == "https"
    assert seen["host"] == "evil.example"               # this proxy said so
    assert seen["script"] == ""                         # but nobody gets to set the prefix


def test_another_peer_is_not_believed_through_waitress(serve):
    seen = ask(serve(proxy_trust.parse_proxies("10.9.9.9")), FORGED)

    assert (seen["addr"], seen["scheme"], seen["script"], seen["left"]) == ("127.0.0.1", "http", "", [])
