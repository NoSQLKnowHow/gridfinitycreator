"""Catch use of CadQuery APIs that are scheduled for removal.

The Docker image installs CadQuery unpinned, so a deprecated call that merely
warns today becomes a broken build after the next release. Turning every
FutureWarning into an error makes the test suite flag the next deprecation early.
"""

import warnings

import pytest

import grid_constants

GENERATORS = ["baseplate", "classicbin", "holeybin", "lightbin", "solidbin"]


@pytest.mark.parametrize("name", GENERATORS)
def test_generators_use_no_deprecated_cadquery_api(generators, name):
    module = generators[name]
    settings = module.settings.Settings()
    generator = module.generator.Generator(settings, grid_constants.Grid())

    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        generator.generate_model()
