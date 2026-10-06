"""Where generated files are written before they are sent to the client."""

import os

# Fallback used when GFG_TMP_DIR is not set: a directory next to the application
DEFAULT_TMP_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', '..', 'tmpfiles')

def get_tmp_dir():
    """Return the directory for temporary output files, creating it if needed.

       Set GFG_TMP_DIR to point it elsewhere - e.g. at a tmpfs mount, which keeps
       the short-lived files in RAM instead of wearing out the server's disk."""
    tmp_dir = os.environ.get('GFG_TMP_DIR') or DEFAULT_TMP_DIR
    os.makedirs(tmp_dir, exist_ok=True)
    return tmp_dir
