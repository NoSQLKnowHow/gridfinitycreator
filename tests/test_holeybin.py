"""Holey bin geometry."""

import pytest

import grid_constants
from conftest import solid_count
from generators.common.errors import SettingsError


def build(generators, **overrides):
    module = generators["holeybin"]
    settings = module.settings.Settings()
    for key, value in overrides.items():
        setattr(settings, key, value)
    return module.generator.Generator(settings, grid_constants.Grid()).generate_model()


@pytest.mark.parametrize("lip", [True, False])
@pytest.mark.parametrize("shape", ["CIRCLE", "SQUARE", "HEXAGON"])
def test_bin_is_a_single_solid_with_or_without_stacking_lip(generators, lip, shape):
    """Without a lip the base and the walls used to be left as two touching but
       separate solids, which slicers and STEP consumers can mishandle."""
    model = build(generators, addStackingLip=lip, holeShape=shape)

    assert model.val().isValid()
    assert solid_count(model) == 1


def test_an_oversized_hole_grid_is_refused_instead_of_silently_building_a_huge_bin(generators):
    """The generator "capped" the bin size and then recalculated it from the hole grid
       straight away, so the cap never took effect: 100 x 100 holes at 1000 mm deep
       produced 29 x 29 x 144 units against limits of 6 x 6 x 12."""
    with pytest.raises(SettingsError, match="29 × 29 grid units.*largest allowed is 6 × 6"):
        build(generators, numHolesX=100, numHolesY=100, holeDepth=1000.0)


def test_removing_the_lip_only_removes_material(generators):
    with_lip = build(generators, addStackingLip=True).val().Volume()
    without_lip = build(generators, addStackingLip=False).val().Volume()

    assert 0 < without_lip < with_lip
