"""The page carries no inline script and no event-handler attributes.

The Content-Security-Policy the server sends allows scripts from the server itself only (SEC-6), so
that a script that finds its way into the page by mistake, through a field that is not escaped one
day, is not run. Inline <script> blocks and onclick="..." attributes would be refused with it, so
everything that used to be one lives in /static now, and buttons say what they do in data-action
(see static/page.js).
"""

import glob
import os
import re

import pytest

from conftest import REPO

TEMPLATE_SOURCES = [
    path for pattern in ("templates/*", "generators/**/*.html", "help_files/*.html")
    for path in glob.glob(os.path.join(REPO, pattern), recursive=True)
]
FIRST_PARTY_SCRIPTS = sorted(glob.glob(os.path.join(REPO, "static", "*.js")))

INLINE_SCRIPT = re.compile(r"<script\b(?![^>]*\bsrc=)", re.IGNORECASE)
HANDLER_ATTRIBUTE = re.compile(r"<[a-zA-Z][^<>]*?\s(on[a-z]+)\s*=", re.IGNORECASE)


def without_comments(markup):
    return re.sub(r"<!--.*?-->|\{#.*?#\}", "", markup, flags=re.DOTALL)


def page(client):
    return client.get("/").get_data(as_text=True)


# ---------------------------------------------------------------- the page as it is served

def test_the_page_has_no_inline_script(client):
    assert INLINE_SCRIPT.findall(without_comments(page(client))) == []


def test_the_page_has_no_event_handler_attributes(client):
    assert HANDLER_ATTRIBUTE.findall(without_comments(page(client))) == []


def test_the_page_has_no_javascript_urls(client):
    assert "javascript:" not in page(client).lower()


# ---------------------------------------------------------------- the sources, including what is only sometimes shown

def test_there_are_template_sources_to_check():
    assert len(TEMPLATE_SOURCES) > 20


@pytest.mark.parametrize("path", TEMPLATE_SOURCES, ids=lambda p: os.path.relpath(p, REPO))
def test_no_template_has_inline_script_or_handlers(path):
    with open(path, encoding="utf-8") as handle:
        markup = without_comments(handle.read())

    assert INLINE_SCRIPT.findall(markup) == []
    assert HANDLER_ATTRIBUTE.findall(markup) == []


@pytest.mark.parametrize("path", FIRST_PARTY_SCRIPTS, ids=lambda p: os.path.basename(p))
def test_no_script_builds_inline_handlers(path):
    """Markup that a script builds is as inline as markup in a template"""
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    code = "\n".join(line for line in code.splitlines() if not line.lstrip().startswith("//"))

    assert not re.search(r"\bon[a-z]+\s*=\s*[\"']", code)
    assert "javascript:" not in code


# ---------------------------------------------------------------- what the buttons say is something a script does

def keys_of(script, constant):
    """The names in `const <constant> = { 'name': ..., }` of a script"""
    with open(os.path.join(REPO, "static", script), encoding="utf-8") as handle:
        source = handle.read()
    body = re.search(rf"const {constant} = \{{(.*?)\n  \}};", source, re.DOTALL).group(1)
    return set(re.findall(r"^\s*'([a-z-]+)':", body, re.MULTILINE))


def test_every_button_action_on_the_page_has_a_handler_and_every_handler_a_button(client):
    used = set(re.findall(r'data-action="([^"]+)"', page(client)))

    assert used == keys_of("page.js", "CLICK_ACTIONS")


def test_every_generator_field_action_on_the_page_has_a_handler_and_every_handler_a_field(client):
    used = set(re.findall(r'data-change="([^"]+)"', page(client)))

    assert used == keys_of("holeybin_form.js", "CHANGE_ACTIONS")


def test_each_generator_form_names_itself_for_the_preview(client, generators):
    html = page(client)

    for name in generators:
        assert f'data-preview-form="{name}"' in html


def test_the_buttons_that_open_dialogs_name_their_generator(client, generators):
    html = page(client)

    for action in ("share-config", "save-config-dialog", "load-config-dialog"):
        for name in generators:
            assert re.search(rf'data-action="{action}"[^>]*data-form="{name}"', html), (action, name)


# ---------------------------------------------------------------- the scripts that moved out load in a workable order

def test_the_theme_is_applied_in_the_head_before_anything_is_painted(client):
    html = page(client)

    assert html.index("/static/theme_init.js") < html.index("/static/theme.css") < html.index("<body")


def test_the_page_scripts_load_after_the_code_they_call(client):
    html = page(client)
    order = [html.index(f"/static/{name}") for name in
             ("library.js", "viewer.js", "layout_editor.js", "holeybin_form.js", "previews.js", "page.js")]

    assert order == sorted(order)
