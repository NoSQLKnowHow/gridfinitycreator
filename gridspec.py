"""The user-adjustable grid specification (grid pitch and height unit) and how it
is remembered between visits.

The values arrive from two untrusted places - the "Advanced settings" form and a
cookie - so everything is validated here before it can reach the geometry code.
"""

import math

COOKIE_NAME = "gridspec"
COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # remember the choice for a year

# (field label, minimum mm, maximum mm) for grid size X, grid size Y and the
# height unit, in the order they are stored in the cookie. The generators were
# checked to build valid models across this whole range.
#
# The base profile is 4.75 mm tall and the floor above it fills the rest of the first
# height unit, so the unit must leave room for a floor that can be printed: 6 mm gives 1.25 mm.
LIMITS = (
    ("Grid size X", 20.0, 150.0),
    ("Grid size Y", 20.0, 150.0),
    ("Height unit", 6.0, 20.0),
)


# The grids the Advanced settings offer as presets: (name, grid size X, grid size Y, height unit) in mm.
# The first is the standard, the one nothing needs pointing out for.
PRESETS = (
    ("Gridfinity", 42.0, 42.0, 7.0),
    ("Raaco", 39.5, 54.5, 7.0),
)
CUSTOM = "Custom"


def preset_name(x, y, z):
    """The name of the preset that is exactly this grid, or "Custom" when there is none"""
    for name, preset_x, preset_y, preset_z in PRESETS:
        if all(math.isclose(a, b, abs_tol=1e-9) for a, b in ((x, preset_x), (y, preset_y), (z, preset_z))):
            return name
    return CUSTOM


class GridSpecError(ValueError):
    """A grid value is missing, not a number, or outside the supported range.
       The message is written to be shown to the user."""


def validate(values):
    """Return the three values as floats, or raise GridSpecError for the first bad one"""
    result = []
    for value, (label, low, high) in zip(values, LIMITS):
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise GridSpecError(f"{label} must be a number.") from None

        # Comparisons with NaN are always false, so test for finiteness explicitly
        if not math.isfinite(number) or not low <= number <= high:
            raise GridSpecError(f"{label} must be between {low:g} and {high:g} mm.")
        result.append(number)
    return tuple(result)


def parse_cookie(raw):
    """Parse a cookie value such as "42.0,42.0,7.0".

       Returns None when the cookie is missing or unusable, so the caller can fall
       back to the standard grid instead of failing the whole page."""
    if not raw:
        return None

    parts = raw.split(",")
    if len(parts) != len(LIMITS):
        return None

    try:
        return validate(parts)
    except GridSpecError:
        return None


def from_form(form):
    """Read the values posted by the Advanced settings form (raises GridSpecError)"""
    return validate([form.get("gridSizeX"), form.get("gridSizeY"), form.get("gridSizeZ")])


def serialize(x, y, z):
    """The cookie value for a grid specification"""
    return f"{x},{y},{z}"
