"""The page on a phone.

At 375 px wide the page was 12 px wider than the screen (the footer was a Bootstrap .row outside any
container, and rows have negative margins), the six tabs wrapped onto three lines, and every settings
card was 106 px wide because the columns were col-6 at every width.
"""

import os
import re

from conftest import REPO


def page(client):
    return client.get("/").get_data(as_text=True)


def css():
    with open(os.path.join(REPO, "static", "theme.css"), encoding="utf-8") as handle:
        return handle.read()


def rule(selector, stylesheet):
    """The declarations of the (first) rule for exactly this selector, outside any media query"""
    match = re.search(rf"(?m)^{re.escape(selector)}\s*\{{([^}}]*)\}}", stylesheet)
    assert match, f"no rule for {selector}"
    return match.group(1)


def media_rules(stylesheet, condition):
    """The text of every @media block whose condition contains this string"""
    blocks = []
    for match in re.finditer(r"@media[^{]*\{", stylesheet):
        if condition in match.group(0):
            depth, i = 1, match.end()
            while depth:
                depth += {"{": 1, "}": -1}.get(stylesheet[i], 0)
                i += 1
            blocks.append(stylesheet[match.end():i - 1])
    return "\n".join(blocks)


# ---------------------------------------------------------------- no bare row outside a container

def test_the_footer_is_not_a_row_outside_a_container(client):
    """A .row has negative side margins; with no padded parent it pushed the page 12 px sideways"""
    html = page(client)

    assert "<footer" in html
    assert 'class="row text-center pb-4"' not in html


# ---------------------------------------------------------------- columns that adapt

def test_settings_cards_are_one_per_line_on_a_phone(client):
    html = page(client)

    assert '<div class="col-6">' not in html
    assert '<div class="col-12 col-sm-6">' in html


def test_the_description_stacks_above_its_picture_on_a_phone(client):
    html = page(client)

    assert '<div class="col-9">' not in html
    assert "col-12 col-md-9" in html


# ---------------------------------------------------------------- the tab strip scrolls instead of wrapping

def test_the_tab_strip_stays_on_one_line_and_scrolls(client):
    strip = rule(".nav-tabs", css())

    assert "flex-wrap: nowrap" in strip
    assert "overflow-x: auto" in strip
    assert "max-width: 100%" in strip
    assert "white-space: nowrap" in rule(".nav-tabs .nav-link", css())


# ---------------------------------------------------------------- the shell gives the content room

def test_the_shell_is_less_padded_on_a_phone():
    phone = media_rules(css(), "max-width: 575.98px")

    assert ".gfg-shell" in phone
    assert re.search(r"\.gfg-shell\s*\{[^}]*padding", phone)


def test_the_hero_buttons_may_wrap_rather_than_overflow():
    assert "flex-wrap: wrap" in rule(".gfg-hero-actions", css())


def test_the_script_that_keeps_the_active_tab_in_view_is_loaded(client):
    """With a strip that scrolls, the open tab can be out of sight (e.g. after a refused submit)"""
    assert "/static/tabs.js" in page(client)
