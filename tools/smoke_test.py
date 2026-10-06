#!/usr/bin/env python3
"""Checks a running Gridfinity Creator the way a user would: the page, a static file, the dimensions
readout, a preview, a download in two formats, and a refused request.

    python tools/smoke_test.py http://127.0.0.1:5000 [--wait SECONDS]

Exits 0 when every check passes. Standard library only, so it runs anywhere (CI runs it against the
container as it is started in production: read-only, as an ordinary user, with no capabilities).
"""

import argparse
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

FORM = dict(sizeUnitsX=1, sizeUnitsY=1, baseStyle="standard", baseThickness="2.4", magnetHoleDiameter="6.5",
            exportFormat="stl", baseplate="Generate")


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, path, data=None, timeout=240):
        """(status, headers, body); an HTTP error status is an answer, not an exception"""
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        try:
            with self.opener.open(urllib.request.Request(self.base + path, data=body), timeout=timeout) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers, error.read()

    def form(self, token, **changes):
        return {**FORM, **changes, "csrf_token": token}


def wait_for(client, seconds):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        try:
            status, _, body = client.request("/", timeout=5)
            if status == 200:
                return body.decode("utf-8", "replace")
            last = f"HTTP {status}"
        except OSError as error:
            last = str(error)
        time.sleep(1)
    raise SystemExit(f"FAIL  {client.base} did not answer within {seconds} s ({last})")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url")
    parser.add_argument("--wait", type=int, default=120, help="seconds to wait for the server to start answering")
    arguments = parser.parse_args()

    client = Client(arguments.url)
    page = wait_for(client, arguments.wait)
    failures = []

    def check(name, test):
        try:
            test()
            print(f"ok    {name}")
        except Exception as error:  # a failed check is reported; the rest still run
            failures.append(name)
            print(f"FAIL  {name}: {error}")

    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page)
    assert token, "the home page has no CSRF token"
    token = token.group(1)

    def home_page():
        assert "Gridfinity Creator" in page and 'id="main"' in page

    def static_file():
        status, _, body = client.request("/static/vendor/three/three.min.js")
        assert status == 200 and len(body) > 100_000, f"HTTP {status}, {len(body)} bytes"

    def dimensions():
        status, headers, body = client.request("/", client.form(token, dimensions="true"))
        assert status == 200, f"HTTP {status}"
        assert json.loads(body), "empty readout"

    def preview():
        status, headers, body = client.request("/", client.form(token, preview="true"))
        assert status == 200, f"HTTP {status}"
        assert len(body) > 200, f"only {len(body)} bytes"

    def download(fmt, magic):
        def run():
            status, headers, body = client.request("/", client.form(token, exportFormat=fmt))
            assert status == 200, f"HTTP {status}"
            assert "attachment" in headers.get("Content-Disposition", ""), headers.get("Content-Disposition")
            assert len(body) > 200 and body.startswith(magic) if magic else len(body) > 200, f"{len(body)} bytes, starts {body[:12]!r}"
        return run

    def refused():
        status, _, body = client.request("/", client.form(token, sizeUnitsX="99"))
        assert status == 422, f"HTTP {status}"
        assert "That didn" in body.decode("utf-8", "replace"), "no explanation shown"

    check("the home page", home_page)
    check("a static file", static_file)
    check("the dimensions readout", dimensions)
    check("a preview", preview)
    check("a download (STL)", download("stl", None))
    check("a download (3MF)", download("3mf", b"PK"))
    check("a refused request", refused)

    print(f"\n{len(failures)} of 7 checks failed" if failures else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
