"""Helpers for reporting real-world dimensions of generated models.

Each generator exposes get_dimensions() returning a list of sections:
    [{"title": "Outer", "rows": [["Footprint", "83.5 x 83.5 mm"], ...]}, ...]
which the frontend renders in a panel next to the 3D preview, so users can
check whether their items will actually fit before printing.
"""

def mm(value):
    """Format a single millimeter value"""
    return f"{value:.1f} mm"

def mm2(x, y):
    """Format an X x Y footprint"""
    return f"{x:.1f} × {y:.1f} mm"

def mm3(x, y, z):
    """Format an X x Y x Z space"""
    return f"{x:.1f} × {y:.1f} × {z:.1f} mm"

def ml(x_mm, y_mm, z_mm):
    """Format the volume of a box given in mm as milliliters"""
    return ml_from_mm3(x_mm * y_mm * z_mm)

def ml_from_mm3(volume_mm3):
    """Format a raw mm^3 volume as milliliters"""
    volume = max(volume_mm3, 0) / 1000.0
    if volume >= 100:
        return f"{volume:.0f} ml"
    return f"{volume:.1f} ml"

def bin_outer_section(gen):
    """Shared 'Outer' section for all bin generators (which precalculate
       brickSizeX/Y/Z and honor addStackingLip)."""
    totalHeight = gen.brickSizeZ
    if getattr(gen.settings, "addStackingLip", False):
        totalHeight += gen.grid.STACKING_LIP_HEIGHT

    return {
        "title": "Outer",
        "rows": [
            ["Footprint", mm2(gen.brickSizeX, gen.brickSizeY)],
            ["Total height", mm(totalHeight)],
        ],
    }

def lip_pocket_volume(gen):
    """Volume of the open pocket inside the stacking lip: the cavity continues
       above the nominal height by the lip's height, minus the chamfered ring
       at the rim (triangle cross-section swept along the inner perimeter)."""
    if not getattr(gen.settings, "addStackingLip", False):
        return 0

    X, Y = gen.internalSizeX, gen.internalSizeY
    chamfer = gen.grid.WALL_THICKNESS - gen.grid.CHAMFER_EPSILON
    ring = (chamfer * chamfer / 2) * 2 * (X + Y)
    return X * Y * gen.grid.STACKING_LIP_HEIGHT - ring

def interior_section(gen, usableDepth, displacedVolume=0):
    """Shared 'Interior' section: the bin's overall inner cavity, before any
       divider walls are taken into account. displacedVolume (mm^3) accounts
       for features protruding into the interior (label tab, scoop ramp).

       'Inner size' quotes the stack-safe depth (fill to here and another bin
       still stacks flush). With a stacking lip the cavity physically continues
       up to the rim - 'Depth to rim' shows that, and 'Inner volume' counts the
       full cavity including the lip pocket."""
    boxVolume = gen.internalSizeX * gen.internalSizeY * usableDepth
    rows = [["Inner size", mm3(gen.internalSizeX, gen.internalSizeY, usableDepth)]]

    lipVolume = lip_pocket_volume(gen)
    if lipVolume > 0:
        rows.append(["Depth to rim", mm(usableDepth + gen.grid.STACKING_LIP_HEIGHT)])

    rows.append(["Inner volume", ml_from_mm3(boxVolume + lipVolume - displacedVolume)])

    return {"title": "Interior", "rows": rows}

def compartment_section(gen, usableDepth, displacedPerCompartment=0):
    """Shared 'Per compartment' section for bins with divider walls.
       usableDepth differs per generator (floor thickness varies).
       displacedPerCompartment (mm^3) accounts for label tab / scoop ramp
       intrusions that apply to every compartment.
       Returns None for a single undivided compartment - the Interior
       section already covers that case."""
    cX = gen.settings.compartmentsX
    cY = gen.settings.compartmentsY
    if cX * cY <= 1:
        return None

    t = gen.settings.dividerThickness

    # The usable space per compartment is the internal size minus the
    # divider walls, split over the number of compartments
    usableX = (gen.internalSizeX - t * (cX - 1)) / cX
    usableY = (gen.internalSizeY - t * (cY - 1)) / cY

    return {
        "title": "Per compartment",
        "rows": [
            ["Compartments", f"{cX} × {cY}"],
            ["Usable space", mm3(usableX, usableY, usableDepth)],
            ["Volume", ml_from_mm3(usableX * usableY * usableDepth - displacedPerCompartment)],
        ],
    }
