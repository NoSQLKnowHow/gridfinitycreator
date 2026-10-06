"""Form validators shared by the generators."""

import math
from decimal import Decimal

from wtforms.validators import NumberRange, StopValidation, ValidationError


def _is_finite(value):
    if isinstance(value, Decimal):
        return value.is_finite()
    return math.isfinite(value)


class Bounded(NumberRange):
    """A number that must lie between min and max (inclusive).

       Unlike a plain NumberRange it also refuses NaN and infinity. DecimalField
       happily parses "NaN" and "Infinity", and every comparison with NaN is false
       (or raises), so NumberRange alone lets them straight through.

       Like NumberRange it publishes min and max to the rendered <input>, so the
       browser's own limits and the server's limits come from one definition."""

    def __init__(self, min, max, message=None):
        super().__init__(min=min, max=max, message=message or "Must be between %(min)s and %(max)s.")

    def __call__(self, form, field):
        if field.data is None:
            # The field could not be parsed ("Not a valid integer value." is already
            # reported); don't add a second, redundant message
            raise StopValidation()

        if not _is_finite(field.data):
            raise ValidationError(self.message % dict(min=self.min, max=self.max, field_name=field.label.text))

        super().__call__(form, field)
