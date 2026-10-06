"""What the page loads.

jQuery (285 KB, unminified, no integrity hash, from a third-party host) was loaded on every
visit and used by nothing.
"""

import os

from conftest import REPO


def test_jquery_is_not_loaded(client):
    html = client.get("/").get_data(as_text=True)

    assert "jquery" not in html.lower()


def test_nothing_in_the_application_uses_jquery():
    """If something starts to, loading it again is a deliberate decision, not a leftover"""
    import re

    offenders = []
    for folder, extensions in (("static", (".js",)), ("templates", (".j2",))):
        for name in os.listdir(os.path.join(REPO, folder)):
            if name.endswith(extensions):
                with open(os.path.join(REPO, folder, name), encoding="utf-8") as handle:
                    if re.search(r"(?<![\w$])\$\(|jQuery|(?<![\w$])\$\.", handle.read().replace("${", "")):
                        offenders.append(f"{folder}/{name}")
    assert offenders == []
