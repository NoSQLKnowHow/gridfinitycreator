"""The shared Bounded form validator."""

from decimal import Decimal

import pytest
from flask_wtf import FlaskForm
from wtforms import DecimalField, IntegerField

import gfg_main
from generators.common.validators import Bounded


class SampleForm(FlaskForm):
    class Meta:
        csrf = False

    count = IntegerField("Count", validators=[Bounded(1, 6)])
    size = DecimalField("Size", validators=[Bounded(1, 10)], places=2)


def validate(**data):
    with gfg_main.app.test_request_context(method="POST", data=data):
        form = SampleForm()
        form.validate()
        return form.errors, form


def test_values_inside_the_range_pass_including_both_ends():
    for count, size in [("1", "1"), ("6", "10"), ("3", "6.5")]:
        errors, _ = validate(count=count, size=size)
        assert errors == {}


@pytest.mark.parametrize("count", ["0", "7", "-1", "100000000000000000000"])
def test_integers_outside_the_range_fail(count):
    errors, _ = validate(count=count, size="5")

    assert errors == {"count": ["Must be between 1 and 6."]}


@pytest.mark.parametrize("size", ["0.99", "10.01", "-5", "NaN", "sNaN", "Infinity", "-Infinity", "inf"])
def test_decimals_outside_the_range_or_not_finite_fail_cleanly(size):
    """NaN compares false with everything (or raises), so a plain NumberRange accepts it"""
    errors, _ = validate(count="3", size=size)

    assert errors == {"size": ["Must be between 1 and 10."]}


def test_unparseable_input_gets_exactly_one_message():
    errors, _ = validate(count="abc", size="")

    assert errors == {"count": ["Not a valid integer value."], "size": ["Not a valid decimal value."]}


def test_the_limits_are_published_for_the_html_input():
    with gfg_main.app.test_request_context():
        markup = SampleForm().count()

    assert 'min="1"' in markup
    assert 'max="6"' in markup


def test_parsed_values_are_exact():
    _, form = validate(count="4", size="2.50")

    assert form.count.data == 4
    assert form.size.data == Decimal("2.50")
