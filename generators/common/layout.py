"""Shared parsing for custom compartment layouts.

The layout editor in the UI stores removed divider-wall segments as a JSON
list in the form's hidden removedWalls field, e.g. [["v",1,0],["h",0,1]]:
  "v", i, j - the wall between column i-1 and i, at row j (1 <= i < compartmentsX)
  "h", i, j - the wall between row j-1 and j, at column i (1 <= j < compartmentsY)
An empty string means no walls are removed (full uniform grid).
"""

import json

def parse_removed_walls(settings):
    """Parse settings.removedWalls into a set of ('v'|'h', i, j) tuples,
       silently ignoring anything malformed or out of range."""
    removed = set()
    raw = getattr(settings, 'removedWalls', '') or ''
    if not raw:
        return removed

    cX = settings.compartmentsX
    cY = settings.compartmentsY
    try:
        for item in json.loads(raw):
            if not (isinstance(item, list) and len(item) == 3):
                continue
            kind, i, j = item
            if not (isinstance(i, int) and isinstance(j, int)):
                continue
            if kind == 'v' and 1 <= i < cX and 0 <= j < cY:
                removed.add(('v', i, j))
            elif kind == 'h' and 0 <= i < cX and 1 <= j < cY:
                removed.add(('h', i, j))
    except (ValueError, TypeError):
        pass

    return removed
