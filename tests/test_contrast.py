"""Text colours that can be read.

WCAG AA asks 4.5:1 for normal text. Flatly's solid alert colours and its secondary button put white
text on backgrounds of 2.2 to 3.8:1 (measured in the browser), the light theme's outline buttons are
2.1 to 3.4:1 on the page, and the muted grey of the footer was 4.34:1. These tests compute the ratio
from the colours the stylesheets actually declare.
"""

import os
import re

import pytest

from conftest import REPO

AA = 4.5
STATIC = os.path.join(REPO, "static")


def read(*parts):
    with open(os.path.join(STATIC, *parts), encoding="utf-8") as handle:
        return handle.read()


THEME = read("theme.css")


def luminance(colour):
    colour = colour.lstrip("#")
    r, g, b = (int(colour[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(first, second):
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def declarations(selector, stylesheet=THEME):
    """property -> value for the rule with exactly this selector"""
    match = re.search(rf"(?m)^{re.escape(selector)}\s*\{{([^}}]*)\}}", stylesheet)
    assert match, f"{selector} is not styled in theme.css"
    return dict(re.findall(r"([\w-]+)\s*:\s*([^;]+);", match.group(1)))


def hex_of(value):
    return re.search(r"#[0-9a-fA-F]{6}", value).group(0)


def token_block(theme):
    start = THEME.index(":root") if theme == "light" else THEME.index('html[data-bs-theme="dark"]')
    return THEME[start:THEME.index("}", start)]


def token(theme, name):
    return hex_of(re.search(rf"--gfg-{name}:\s*([^;]+);", token_block(theme)).group(1))


# ---------------------------------------------------------------- the theme's own text colours

@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("surface", ["bg", "surface", "surface-2"])
def test_muted_text_is_readable_on_every_surface(theme, surface):
    assert contrast(token(theme, "text-muted"), token(theme, surface)) >= AA


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("surface", ["bg", "surface"])
def test_body_text_is_readable(theme, surface):
    assert contrast(token(theme, "text"), token(theme, surface)) >= AA


# ---------------------------------------------------------------- alerts

@pytest.mark.parametrize("kind", ["danger", "warning", "info", "success", "secondary"])
def test_alert_text_is_readable(kind):
    rule = declarations(f".alert-{kind}")

    assert contrast(hex_of(rule["color"]), hex_of(rule["background-color"])) >= AA


@pytest.mark.parametrize("kind", ["danger", "warning", "info", "success", "secondary"])
def test_alert_borders_match_their_background(kind):
    rule = declarations(f".alert-{kind}")

    assert hex_of(rule["border-color"]) == hex_of(rule["background-color"])


# ---------------------------------------------------------------- buttons

def test_secondary_button_text_is_readable_in_both_themes():
    rule = declarations(".btn-secondary")

    assert contrast(hex_of(rule["--bs-btn-color"]), hex_of(rule["--bs-btn-bg"])) >= AA
    assert contrast(hex_of(rule["--bs-btn-hover-color"]), hex_of(rule["--bs-btn-hover-bg"])) >= AA


LIGHT = ':root:not([data-bs-theme="dark"]) '


@pytest.mark.parametrize("surface", ["bg", "surface", "surface-2"])
@pytest.mark.parametrize("kind", ["danger", "info", "success", "secondary"])
def test_outline_buttons_are_readable_on_every_light_surface(kind, surface):
    """On the dark theme Flatly's own colours already pass (5.0 to 8.0), so only the light one is
       overridden. (Checked against the page alone, a green at 4.54 passed here and measured 4.49
       in the browser, on a dialog.)"""
    rule = declarations(f"{LIGHT}.btn-outline-{kind}")

    assert contrast(hex_of(rule["--bs-btn-color"]), token("light", surface)) >= AA


@pytest.mark.parametrize("kind", ["danger", "info", "success", "secondary"])
def test_outline_buttons_stay_readable_when_hovered(kind):
    rule = declarations(f"{LIGHT}.btn-outline-{kind}")

    assert contrast(hex_of(rule["--bs-btn-hover-color"]), hex_of(rule["--bs-btn-hover-bg"])) >= AA
