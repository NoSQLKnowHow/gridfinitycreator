"""Limits that keep a single request from monopolising the server.

Building a model is CPU-heavy and its cost grows steeply with some settings: a
divider bin with 24 x 24 compartments takes minutes, not seconds. These limits
refuse such requests up front, with a message saying what to change.

The defaults suit a private network. Each can be overridden with an environment
variable - lower them for an instance exposed to the internet.
"""

import math
import os

# Divider-bin walls are built one segment per cell edge, and build time grows
# roughly with the square of the segment count (measured: a 6x6x12 bin takes
# ~6 s at 60 segments, ~42 s at 264, and over 7 minutes at 1104). A 12 x 12
# layout has 264 segments.
DEFAULT_MAX_DIVIDER_SEGMENTS = 300

# The light bin does more work per segment (support plugs clipped against the
# base), so its limit is lower: ~14 s at 60 segments, ~90 s at 264.
DEFAULT_MAX_LIGHT_DIVIDER_SEGMENTS = 150

# Each hole is cut separately from the whole bin (1.5 s for 64 holes, 12.5 s for 576)
DEFAULT_MAX_HOLES = 600


def _positive_int_from_env(name, default):
    try:
        value = int(os.environ.get(name, default))
    except ValueError:
        return default
    return value if value > 0 else default


def max_divider_segments():
    return _positive_int_from_env("GFG_MAX_DIVIDER_SEGMENTS", DEFAULT_MAX_DIVIDER_SEGMENTS)


def max_light_divider_segments():
    return _positive_int_from_env("GFG_MAX_LIGHT_DIVIDER_SEGMENTS", DEFAULT_MAX_LIGHT_DIVIDER_SEGMENTS)


def max_holes():
    return _positive_int_from_env("GFG_MAX_HOLES", DEFAULT_MAX_HOLES)


def at_least_one(settings, *names):
    """Raise any of these integer settings that is below 1 up to 1.

       The forms reject such values, but a divide-by-zero while building a model
       is a poor way to find out about one that got through."""
    for name in names:
        setattr(settings, name, max(1, getattr(settings, name)))


def divider_segment_count(compartments_x, compartments_y, removed_walls=()):
    """How many divider wall segments are actually built for a compartment grid
       (every interior cell edge, less the segments removed in the layout editor)"""
    total = (compartments_x - 1) * compartments_y + (compartments_y - 1) * compartments_x
    return total - len(removed_walls)


def divider_limit_message(segments, limit):
    """Explain a refused compartment layout, in terms of the grid size the user will recognise"""
    # An n x n grid of compartments has 2n(n-1) interior wall segments
    side = int((1 + math.sqrt(1 + 2 * limit)) / 2)
    return (f"That layout has {segments} divider wall segments, more than the limit of {limit} "
            f"(roughly a {side} × {side} grid of compartments). Use fewer compartments, or remove "
            f"walls in the layout editor to merge cells.")
