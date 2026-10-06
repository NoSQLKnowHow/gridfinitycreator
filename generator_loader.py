"""Finds and loads the generator plugins in the generators/ folder.

Each generator lives in its own sub-folder containing a main.py. This is separate
from the web application so the processes that build models can load the same
generators without importing the web application.
"""

import importlib.machinery
import importlib.util
import logging
import os
import sys

from contextlib import contextmanager

logger = logging.getLogger('GFG')

# Absolute, so this works from any working directory
GEN_FOLDER = os.path.join(os.path.dirname(os.path.realpath(__file__)), "generators")
MAIN_MODULE = "main.py"

# Generator modules loaded in this process, by directory name
_loaded = {}

# From this StackOverflow answer: https://stackoverflow.com/a/41904558
@contextmanager
def add_to_path(p):
    old_path = sys.path
    sys.path = sys.path[:]
    sys.path.insert(0, p)
    try:
        yield
    finally:
        sys.path = old_path

def load_generators():
    """Scan for generators and load any generators found """

    generators = []

    # Each generator is contained in its own subdir
    possible_generators = sorted(os.listdir(GEN_FOLDER))
    for entry in possible_generators:
        location = os.path.join(GEN_FOLDER, entry)

        # It should be a dir and contain the main module
        if not os.path.isdir(location) or not MAIN_MODULE in os.listdir(location):
            continue

        logger.debug("Loading generator {0}".format(entry))
        fname = "{0}/{1}".format(location, MAIN_MODULE)

        # Temporarily expand the search path for modules, so the (sub-)modules needed
        # by each generator can be found
        try:
            with add_to_path(location):
                # importlib magic. Loads the module and makes it available to call
                spec = importlib.util.spec_from_loader(
                    entry,
                    importlib.machinery.SourceFileLoader(entry, fname)
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                sys.modules[entry] = module
                generators.append(module)
                _loaded[entry] = module
        except Exception as e:
            logger.error(f"Failed to load generator {entry}: {e}")

    return generators

def get(name):
    """The loaded generator module with this directory name. Loads the generators
       first if this process has not done so yet (a model-building child process
       normally inherits them already loaded)."""
    if name not in _loaded:
        load_generators()
    return _loaded[name]
