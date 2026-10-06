"""Custom grids: every generator must honour the grid it is given, not just the standard one.

The Advanced settings (and the Raaco preset, 39.5 x 54.5 mm) let the user change the grid
pitch in X and Y and the height unit. Several generators quietly assumed 42 x 42 x 7.
These tests check properties that hold for ANY grid, so they do not depend on how a
generator is written:

  * the model is one valid solid;
  * its height is the number of height units times the unit (plus the stacking lip);
  * a model on a grid of X x Y with 2 x 1 cells is the mirror image, in volume and size,
    of the model on a grid of Y x X with 1 x 2 cells (code that reads X where it means Y
    breaks this at once);
  * across the whole range the Advanced settings accept, a model either builds or is
    refused with a message; it never crashes.
"""

import cadquery as cq
import pytest

import grid_constants
import gridspec
from generators.common.errors import SettingsError

RAACO = dict(GRID_UNIT_SIZE_X_MM=39.5, GRID_UNIT_SIZE_Y_MM=54.5)
RAACO_SWAPPED = dict(GRID_UNIT_SIZE_X_MM=54.5, GRID_UNIT_SIZE_Y_MM=39.5)


def make_grid(**changes):
    grid = grid_constants.Grid(**changes)
    grid.recalculate()
    return grid


def build(generators, name, grid, **settings):
    """The finished shape and its generator, for one generator's default settings plus overrides"""
    module = generators[name]
    generator = module.generator.Generator(module.settings.Settings(**settings), grid)
    return generator.generate_model().val(), generator


def assert_one_valid_solid(shape):
    assert shape.isValid()
    assert len(shape.Solids()) == 1


# Settings for a small model of each kind. Features that are deliberately not symmetric
# (the label ridge and the scoop run along X only) are off where symmetry is compared.
BINS = {
    "classicbin": dict(sizeUnitsX=1, sizeUnitsY=1, sizeUnitsZ=3, compartmentsX=1, compartmentsY=1,
                       addLabelRidge=True, addGrabCurve=True),
    "lightbin": dict(sizeUnitsX=1, sizeUnitsY=1, sizeUnitsZ=3, compartmentsX=1, compartmentsY=1, addLabelRidge=True),
    "solidbin": dict(sizeUnitsX=1, sizeUnitsY=1, sizeUnitsZ=3),
    "holeybin": dict(numHolesX=1, numHolesY=1, sizeUnitsX=1, sizeUnitsY=1, holeDepth=10.0),
}


# ---------------------------------------------------------------- the floor follows the height unit

def test_the_base_and_floor_always_add_up_to_one_height_unit():
    for unit in (6, 7, 7.5, 8, 10, 20):
        grid = make_grid(HEIGHT_UNITSIZE_MM=unit)

        assert grid.BASE_BOTTOM_THICKNESS + grid.BASE_TOP_THICKNESS + grid.FLOOR_THICKNESS == pytest.approx(unit)


def test_the_standard_grid_is_unchanged():
    grid = make_grid()

    assert grid.FLOOR_THICKNESS == pytest.approx(2.25)
    assert grid_constants.Grid().FLOOR_THICKNESS == pytest.approx(2.25)  # also before recalculate()


@pytest.mark.parametrize("unit", [6, 8, 10])
@pytest.mark.parametrize("name", BINS)
def test_a_bin_is_exactly_as_tall_as_its_height_units(generators, name, unit):
    """Walls scaled with the unit but the base stayed 7 mm, so a bin was off by (7 - unit)"""
    grid = make_grid(HEIGHT_UNITSIZE_MM=unit)

    shape, generator = build(generators, name, grid, addStackingLip=True)

    expected = generator.settings.sizeUnitsZ * unit + grid.STACKING_LIP_HEIGHT
    assert shape.BoundingBox().zlen == pytest.approx(expected, abs=0.05)
    assert_one_valid_solid(shape)


@pytest.mark.parametrize("unit", [6, 8, 10])
@pytest.mark.parametrize("name", ["classicbin", "lightbin"])
def test_the_label_ridge_does_not_stick_out_above_the_wall(generators, name, unit):
    """With a unit above 7 the wall stopped short of n x unit while the ridge was drawn up to it,
       so the ridge stuck out above the wall (and, being the highest point, set the bin's height)"""
    grid = make_grid(HEIGHT_UNITSIZE_MM=unit)
    others = {k: v for k, v in BINS[name].items() if k not in ("addLabelRidge", "addGrabCurve")}

    with_ridge, generator = build(generators, name, grid, addStackingLip=False, addLabelRidge=True, **others)
    without, _ = build(generators, name, grid, addStackingLip=False, addLabelRidge=False, **others)

    wall_top = without.BoundingBox().zlen
    assert with_ridge.BoundingBox().zlen == pytest.approx(wall_top, abs=0.01)   # the ridge adds no height
    assert wall_top == pytest.approx(generator.settings.sizeUnitsZ * unit, abs=0.05)


def test_a_height_unit_too_small_for_the_base_is_not_accepted():
    """The base profile alone is 4.75 mm tall; with a 3 mm unit the floor would have been negative"""
    assert gridspec.LIMITS[2][1] >= 4.75 + 1.0   # leaves at least a millimetre of floor
    assert gridspec.parse_cookie("42.0,42.0,3.0") is None
    with pytest.raises(gridspec.GridSpecError, match="Height unit"):
        gridspec.validate(["42", "42", "3"])


# ---------------------------------------------------------------- X and Y are not interchangeable

SWAP_CASES = {
    "baseplate": (dict(sizeUnitsX=2, sizeUnitsY=1, baseStyle="standard", addMagnetHoles=False, addScrewHoles=False),
                  dict(sizeUnitsX=1, sizeUnitsY=2, baseStyle="standard", addMagnetHoles=False, addScrewHoles=False)),
    "classicbin": (dict(sizeUnitsX=2, sizeUnitsY=1, sizeUnitsZ=3, compartmentsX=2, compartmentsY=1,
                        addLabelRidge=False, addGrabCurve=False),
                   dict(sizeUnitsX=1, sizeUnitsY=2, sizeUnitsZ=3, compartmentsX=1, compartmentsY=2,
                        addLabelRidge=False, addGrabCurve=False)),
    "lightbin": (dict(sizeUnitsX=2, sizeUnitsY=1, sizeUnitsZ=3, compartmentsX=2, compartmentsY=1, addLabelRidge=False),
                 dict(sizeUnitsX=1, sizeUnitsY=2, sizeUnitsZ=3, compartmentsX=1, compartmentsY=2, addLabelRidge=False)),
    "solidbin": (dict(sizeUnitsX=2, sizeUnitsY=1, sizeUnitsZ=3), dict(sizeUnitsX=1, sizeUnitsY=2, sizeUnitsZ=3)),
    "holeybin": (dict(numHolesX=2, numHolesY=1, sizeUnitsX=2, sizeUnitsY=1, holeDepth=14.0),
                 dict(numHolesX=1, numHolesY=2, sizeUnitsX=1, sizeUnitsY=2, holeDepth=14.0)),
}


@pytest.mark.parametrize("name", SWAP_CASES)
def test_a_model_and_its_mirror_image_grid_have_the_same_volume(generators, name):
    """Light bin: its feet were built square with the X pitch on both axes (+30 % volume on Raaco)"""
    wide, tall = SWAP_CASES[name]

    first, _ = build(generators, name, make_grid(**RAACO), **wide)
    second, _ = build(generators, name, make_grid(**RAACO_SWAPPED), **tall)

    assert second.Volume() == pytest.approx(first.Volume(), rel=0.001)
    a, b = first.BoundingBox(), second.BoundingBox()
    assert (a.xlen, a.ylen, a.zlen) == pytest.approx((b.ylen, b.xlen, b.zlen), abs=0.05)
    assert_one_valid_solid(first)
    assert_one_valid_solid(second)


# ---------------------------------------------------------------- the baseplate fits the grid it is made for

def test_a_raaco_baseplate_builds(generators):
    """It crashed (StdFail_NotDone) on any grid that is not square"""
    shape, _ = build(generators, "baseplate", make_grid(**RAACO), sizeUnitsX=2, sizeUnitsY=2,
                     baseStyle="standard", addMagnetHoles=False, addScrewHoles=False)

    assert_one_valid_solid(shape)
    box = shape.BoundingBox()
    assert (box.xlen, box.ylen) == pytest.approx((2 * 39.5, 2 * 54.5), abs=0.05)


def bin_in_baseplate_overlap(generators, grid, shift_x=0.0):
    """Volume (mm3) where a 1 x 1 solid bin, set into a 1 x 1 baseplate cell, overlaps the plate"""
    plate, _ = build(generators, "baseplate", grid, sizeUnitsX=1, sizeUnitsY=1, baseStyle="standard",
                     addMagnetHoles=False, addScrewHoles=False)
    solid, _ = build(generators, "solidbin", grid, sizeUnitsX=1, sizeUnitsY=1, sizeUnitsZ=2,
                     addStackingLip=False, addMagnetHoles=False)
    # The plate's cell is centred on the origin, the bin's corner is
    solid = solid.translate(cq.Vector(-grid.BRICK_UNIT_SIZE_X / 2 + shift_x, -grid.BRICK_UNIT_SIZE_Y / 2, 0))
    common = plate.intersect(solid)
    return common.Volume() if common.Solids() else 0.0


@pytest.mark.parametrize("changes", [
    dict(),
    RAACO,
    dict(GRID_UNIT_SIZE_X_MM=45, GRID_UNIT_SIZE_Y_MM=45),
    dict(GRID_UNIT_SIZE_X_MM=30, GRID_UNIT_SIZE_Y_MM=60),
], ids=["standard", "raaco", "45x45", "30x60"])
def test_a_bin_sits_in_a_baseplate_cell_without_interference(generators, changes):
    """The pocket was cut 42 mm wide whatever the grid, so on a 45 mm grid a 1.5 mm wall was left
       around every cell: the plate was 23 % heavier and overlapped a bin by 123 mm3 (it cannot fit)"""
    assert bin_in_baseplate_overlap(generators, make_grid(**changes)) < 0.5


def test_the_fit_check_does_notice_a_bin_that_is_out_of_place(generators):
    """Control for the test above: a bin shifted by 1 mm does overlap the plate (about 124 mm3)"""
    assert bin_in_baseplate_overlap(generators, make_grid(), shift_x=1.0) > 50


# ---------------------------------------------------------------- nothing crashes anywhere in the allowed range

LOW_X, HIGH_X = gridspec.LIMITS[0][1:]
LOW_Z, HIGH_Z = gridspec.LIMITS[2][1:]

EXTREME_GRIDS = [
    dict(GRID_UNIT_SIZE_X_MM=LOW_X, GRID_UNIT_SIZE_Y_MM=LOW_X),
    dict(GRID_UNIT_SIZE_X_MM=HIGH_X, GRID_UNIT_SIZE_Y_MM=HIGH_X),
    dict(GRID_UNIT_SIZE_X_MM=LOW_X, GRID_UNIT_SIZE_Y_MM=HIGH_X),
    dict(GRID_UNIT_SIZE_X_MM=HIGH_X, GRID_UNIT_SIZE_Y_MM=LOW_X),
    dict(HEIGHT_UNITSIZE_MM=LOW_Z),
    dict(HEIGHT_UNITSIZE_MM=HIGH_Z),
]

EXTREME_SETTINGS = {
    "baseplate": dict(sizeUnitsX=1, sizeUnitsY=1, baseStyle="standard", addMagnetHoles=False, addScrewHoles=False),
    "classicbin": dict(sizeUnitsX=1, sizeUnitsY=1, sizeUnitsZ=3, compartmentsX=1, compartmentsY=1),
    "lightbin": dict(sizeUnitsX=1, sizeUnitsY=1, sizeUnitsZ=3, compartmentsX=1, compartmentsY=1),
    "solidbin": dict(sizeUnitsX=1, sizeUnitsY=1, sizeUnitsZ=3),
}


@pytest.mark.parametrize("changes", EXTREME_GRIDS, ids=lambda c: ",".join(f"{k.split('_')[-2] if 'GRID' in k else 'H'}={v:g}" for k, v in c.items()))
@pytest.mark.parametrize("name", EXTREME_SETTINGS)
def test_the_extremes_of_the_allowed_range_build_or_are_refused_cleanly(generators, name, changes):
    try:
        shape, _ = build(generators, name, make_grid(**changes), **EXTREME_SETTINGS[name])
    except SettingsError:
        return  # refusing with a message is fine
    assert_one_valid_solid(shape)
