"""Preloaded by the multiprocessing fork server (see model_builder).

Importing this module loads CadQuery and every generator once, in the fork server
itself. Each model build is then forked from that warm copy, instead of paying for a
fresh import of CadQuery (about 4 s) every time.
"""

import generator_loader

generator_loader.load_generators()
