"""The page's scripts, styles and fonts are served from this server.

They used to come from four third-party hosts (jsDelivr, cdnjs, code.jquery.com, Google
Fonts): every visit told those hosts who was browsing, and on a machine without internet access
(a workshop LAN) the tabs, the 3D preview and the fonts all broke. jQuery was loaded and never used.
"""

import hashlib
import os
import re

import pytest

from conftest import REPO

STATIC = os.path.join(REPO, "static")
VENDOR = os.path.join(STATIC, "vendor")
REFERENCE = re.compile(r"""(?:src|href)=["']?([^"'\s>]+)""")


def page(client):
    return client.get("/").get_data(as_text=True)


def referenced_files(html):
    """Every script, stylesheet and image address in the page (not hyperlinks or anchors)"""
    tags = re.findall(r"<(?:script|link|img)\b[^>]*>", html)
    return [url for tag in tags for url in REFERENCE.findall(tag)]


# ---------------------------------------------------------------- nothing from other hosts

def test_the_page_loads_nothing_from_other_hosts(client):
    foreign = [url for url in referenced_files(page(client)) if re.match(r"(https?:)?//", url)]

    assert foreign == []


def test_the_page_does_not_pre_connect_to_other_hosts(client):
    assert "preconnect" not in page(client)


def test_no_stylesheet_imports_from_another_host():
    """Flatly asks Google for the Lato font; the theme is set in Inter and never uses it"""
    for name in ("theme.css", "vendor/bootswatch/flatly.min.css", "vendor/fonts/fonts.css"):
        with open(os.path.join(STATIC, name), encoding="utf-8") as handle:
            css = re.sub(r"/\*.*?\*/", "", handle.read(), flags=re.DOTALL)  # licence headers quote URLs
        assert not re.search(r"https?://", css.replace("http://www.w3.org", "")), name  # (SVG namespaces)
        assert "@import" not in css, name


def test_jquery_is_gone(client):
    html = page(client)

    assert "jquery" not in html.lower()
    assert not os.path.exists(os.path.join(STATIC, "jquery.js"))


# ---------------------------------------------------------------- what the page asks for exists

def test_every_local_file_the_page_references_is_served(client):
    urls = [url for url in referenced_files(page(client)) if url.startswith("/")]

    assert len(urls) >= 10
    missing = [url for url in urls if client.get(url).status_code != 200]
    assert missing == []


def test_the_fonts_the_stylesheet_names_are_defined_here():
    with open(os.path.join(STATIC, "vendor", "fonts", "fonts.css"), encoding="utf-8") as handle:
        css = handle.read()

    assert 'font-family: "Inter"' in css
    assert 'font-family: "Space Grotesk"' in css
    for name in re.findall(r"url\(([^)]+)\)", css):
        assert os.path.exists(os.path.join(VENDOR, "fonts", name)), name


def test_scripts_load_in_dependency_order(client):
    html = page(client)
    order = [html.index(name) for name in (
        "/static/vendor/bootstrap/bootstrap.bundle.min.js", "/static/vendor/three/three.min.js",
        "/static/viewer.js")]

    assert order == sorted(order)


def test_bootstrap_is_loaded_exactly_once(client):
    """The bundle already contains Popper; a second copy registers every handler twice"""
    html = page(client)

    scripts = re.findall(r"<script\b[^>]*\bsrc=[^>]*>", html)
    assert len([tag for tag in scripts if "bootstrap" in tag]) == 1
    assert not [tag for tag in scripts if "popper" in tag.lower()]


# ---------------------------------------------------------------- vendored files are what they claim to be

def manifest():
    with open(os.path.join(VENDOR, "checksums.sha256"), encoding="utf-8") as handle:
        return dict(reversed(line.split(None, 1)) for line in handle.read().splitlines())


def sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def test_vendored_files_match_their_recorded_checksums():
    expected = {name.strip(): digest for name, digest in manifest().items()}

    changed = [name for name, digest in expected.items() if sha256(os.path.join(VENDOR, name)) != digest]
    assert changed == []


def test_every_vendored_file_is_listed_in_the_manifest():
    listed = {name.strip() for name in manifest()}
    present = {os.path.relpath(os.path.join(root, f), VENDOR) for root, _, files in os.walk(VENDOR) for f in files}

    assert present - listed == {"checksums.sha256", "README.md"}


def test_the_unmodified_libraries_are_the_published_versions():
    """Pinned: Bootstrap 5.3.2 (its SRI hash, as the page used to carry it) and three.js r128
       (the SHA-256 of the file cdnjs serves)"""
    import base64

    with open(os.path.join(VENDOR, "bootstrap", "bootstrap.bundle.min.js"), "rb") as handle:
        bundle = handle.read()
    assert base64.b64encode(hashlib.sha384(bundle).digest()).decode() == \
        "C6RzsynM9kWDrMNeT87bh95OGNyZPhcTNXj1NW7RuBCsyN/o0jlpcV8Qyq46cDfL"
    assert sha256(os.path.join(VENDOR, "three", "three.min.js")) == \
        "9274bbcec8d96168626c732b5d31c775aa8cfb7eaa0599bec0c175908a2c1ce2"
