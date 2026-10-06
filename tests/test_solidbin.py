"""Solid bin form: defaults and help text."""

import re

from conftest import form_html, is_checked


def test_checkbox_defaults(client):
    """The form declared default="False", but that is a non-empty string and so
       truthy: the removal-hole and screw-hole switches rendered as checked."""
    form = form_html(client, "solidbin")

    assert is_checked(form, "addStackingLip")
    assert is_checked(form, "addMagnetHoles")
    assert not is_checked(form, "addRemovalHoles")
    assert not is_checked(form, "addScrewHoles")


def test_every_field_has_help_text(client):
    """Every "?" badge used to open an empty pop-up for this generator"""
    form = form_html(client, "solidbin")
    blocks = re.findall(r'<div id="[^"]*" class="help-content d-none">(.*?)</div>', form, flags=re.S)

    assert len(blocks) >= 9  # size x3, stacking lip, 4 magnet options, export format
    assert all(block.strip() for block in blocks)
