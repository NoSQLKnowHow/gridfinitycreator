"""Holey bin geometry."""

import pytest

import grid_constants
from conftest import solid_count


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


def test_removing_the_lip_only_removes_material(generators):
    with_lip = build(generators, addStackingLip=True).val().Volume()
    without_lip = build(generators, addStackingLip=False).val().Volume()

    assert 0 < without_lip < with_lip
