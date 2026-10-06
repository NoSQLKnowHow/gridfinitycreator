"""Custom grids: every generator must honour the grid it is given, not just the standard one.

The Advanced settings (and the Raaco preset, 39.5 x 54.5 mm) let the user change the grid
pitch in X and Y and the height unit. Several generators quietly assumed 42 x 42 x 7.
These tests check properties that hold for ANY grid, so they do not depend on how a
generator is written:

  * the model is one valid solid;
  * its height is the number of height units times the unit (plus the stacking lip).
"""

import pytest

import grid_constants
import gridspec

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
