"""The page's structure, as a keyboard or screen-reader user meets it.

An axe-core audit of the rendered page (all six tabs) found, among others: the same field ids in
all five forms (so clicking a label in one form focuses the input in the first), 53 "?" help
badges that were <span>s a keyboard could not reach, an Advanced-settings label pointing at the
wrong field, and 38 images without alt text. These tests parse the page properly and pin the
structure that fixes that.
"""

import collections
from html.parser import HTMLParser

import pytest

FORMS = ["baseplate", "classicbin", "holeybin", "lightbin", "solidbin"]


class Page(HTMLParser):
    """Every element of a page with its attributes, the <form> it is in, and its text"""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.elements = []
        self._forms = []
        self._open = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        element = dict(tag=tag, attrs=attrs, form=self._forms[-1] if self._forms else None, text="", inside=list(self._open))
        self.elements.append(element)
        if tag == "form":
            self._forms.append(attrs.get("id"))
        if tag not in self.VOID:
            self._open.append(element)

    def handle_endtag(self, tag):
        if tag == "form" and self._forms:
            self._forms.pop()
        if tag not in self.VOID:
            while self._open and self._open[-1]["tag"] != tag:
                self._open.pop()
            if self._open:
                self._open.pop()

    def handle_data(self, data):
        for element in self._open:
            element["text"] += data

    def by_id(self):
        return {e["attrs"]["id"]: e for e in self.elements if "id" in e["attrs"]}

    def with_class(self, name):
        return [e for e in self.elements if name in e["attrs"].get("class", "").split()]


@pytest.fixture()
def page(client):
    return Page(client.get("/").get_data(as_text=True))


# ---------------------------------------------------------------- ids

def test_no_id_appears_twice(page):
    """Ids were shared by all five forms: sizeUnitsX x5, exportFormat x5, csrf_token x5, content x53"""
    counts = collections.Counter(e["attrs"]["id"] for e in page.elements if "id" in e["attrs"])

    assert {name: n for name, n in counts.items() if n > 1} == {}


@pytest.mark.parametrize("form_id", FORMS)
def test_every_field_of_a_form_has_an_id_that_starts_with_the_forms_name(page, form_id):
    fields = [e for e in page.elements if e["tag"] in ("input", "select", "textarea") and e["form"] == f"{form_id}_form"]

    assert fields
    assert [f["attrs"].get("id") for f in fields if not str(f["attrs"].get("id", "")).startswith(f"{form_id}_")] == []


def test_posted_field_names_are_unchanged(page):
    """The ids changed; the names the server and the scripts read did not"""
    names = {e["attrs"].get("name") for e in page.elements if e["tag"] == "input" and e["form"] == "classicbin_form"}

    assert {"sizeUnitsX", "sizeUnitsY", "sizeUnitsZ", "compartmentsX", "compartmentsY", "csrf_token"} <= names


# ---------------------------------------------------------------- labels

def test_every_label_points_at_a_field_in_its_own_form(page):
    ids = page.by_id()
    wrong = []
    for label in (e for e in page.elements if e["tag"] == "label" and "for" in e["attrs"]):
        target = ids.get(label["attrs"]["for"])
        if target is None or target["form"] != label["form"]:
            wrong.append((label["attrs"]["for"], label["text"].strip(), label["form"]))
    assert wrong == []


def test_the_advanced_settings_labels_point_at_their_own_fields(page):
    """The Y label said for="gridSizeZ", so clicking "Grid size Y" focused the height field"""
    labels = {e["text"].strip(): e["attrs"]["for"] for e in page.elements
              if e["tag"] == "label" and e["attrs"].get("for", "").startswith("gridSize")}

    assert labels == {"Grid size X": "gridSizeX", "Grid size Y": "gridSizeY", "Height unit": "gridSizeZ"}


# ---------------------------------------------------------------- the "?" help badges

def test_help_badges_are_buttons_a_keyboard_can_reach(page):
    badges = page.with_class("help-button")

    assert len(badges) >= 40
    assert [b["tag"] for b in badges if b["tag"] != "button"] == []
    assert [b for b in badges if b["attrs"].get("type") != "button"] == []


def test_every_help_badge_names_its_field(page):
    badges = page.with_class("help-button")

    unnamed = [b for b in badges if not b["attrs"].get("aria-label", "").startswith("Help: ")
               or not b["attrs"]["aria-label"][len("Help: "):].strip()]
    assert unnamed == []


def test_every_help_badge_leads_to_its_text(page):
    ids = page.by_id()
    broken = []
    for badge in page.with_class("help-button"):
        target = ids.get(badge["attrs"].get("data-help-target"))
        if target is None or "help-content" not in target["attrs"].get("class", "").split():
            broken.append(badge["attrs"].get("aria-label"))
    assert broken == []


def test_help_text_sits_outside_the_button(page):
    """A button may only contain phrasing content, and its accessible name would swallow the text"""
    for badge in page.with_class("help-button"):
        assert badge["text"].strip() == "?"


def test_help_texts_are_not_empty(page):
    texts = page.with_class("help-content")

    assert len(texts) >= 40
    assert [t for t in texts if not t["text"].strip()] == []


# ---------------------------------------------------------------- the help dialog

def test_the_help_dialog_is_named_and_can_be_closed_without_a_pointer(page):
    ids = page.by_id()
    dialog = ids["help-modal"]
    close = [e for e in page.elements if e["tag"] == "button" and e["attrs"].get("data-bs-dismiss") == "modal"
             and dialog in e["inside"]]

    assert dialog["attrs"].get("aria-label") == "Help"
    assert close and close[0]["text"].strip() == "Close"


def test_the_help_text_goes_into_a_block_not_a_paragraph(page):
    """The help texts contain paragraphs and pictures, which may not sit inside a <p>"""
    target = page.by_id()["help-modal-text"]

    assert target["tag"] == "div"


# ---------------------------------------------------------------- images

def test_every_image_has_alt_text(page):
    """All 38 images had none (the help dialogs repeat the same nine pictures)"""
    images = [e for e in page.elements if e["tag"] == "img"]

    assert len(images) >= 30
    assert [i["attrs"].get("src") for i in images if not i["attrs"].get("alt", "").strip()] == []


def test_alt_text_describes_the_picture_rather_than_naming_the_file(page):
    for image in (e for e in page.elements if e["tag"] == "img"):
        alt = image["attrs"].get("alt", "")
        assert len(alt.split()) >= 4, (image["attrs"]["src"], alt)
        assert ".jpg" not in alt.lower() and "image of" not in alt.lower()


# ---------------------------------------------------------------- landmarks and headings

def test_the_page_has_one_main_landmark_that_holds_the_tab_panels(page):
    mains = [e for e in page.elements if e["tag"] == "main"]

    assert len(mains) == 1
    assert all(mains[0] in page.by_id()[form_id]["inside"] for form_id in ["home"] + FORMS)


def test_the_hero_is_a_banner_and_the_footer_is_a_page_footer(page):
    hero = page.with_class("gfg-hero")[0]
    footer = next(e for e in page.elements if e["tag"] == "footer")

    assert hero["attrs"].get("role") == "banner"
    assert {e["tag"] for e in footer["inside"]} <= {"html", "body"}   # only a footer directly in <body> is a landmark


def test_keyboard_users_can_skip_to_the_content(page):
    first_link = next(e for e in page.elements if e["tag"] == "a")

    assert first_link["attrs"]["href"] == "#main"
    assert "visually-hidden-focusable" in first_link["attrs"]["class"].split()
    assert page.by_id()["main"]["tag"] == "main"


def test_headings_never_skip_a_level(page):
    """h1, then h5 straight away, is what screen-reader users navigate by. (The help texts are
       inserted into their own dialog, which starts again at the top.)"""
    headings = [e for e in page.elements if e["tag"] in {"h1", "h2", "h3", "h4", "h5", "h6"}
                and not any("help-content" in o["attrs"].get("class", "").split() for o in e["inside"])]
    levels = [int(h["tag"][1]) for h in headings]

    assert levels.count(1) == 1 and levels[0] == 1
    assert [(a, b) for a, b in zip(levels, levels[1:]) if b > a + 1] == []


# ---------------------------------------------------------------- tabs

def test_tabs_are_wired_to_their_panels(page):
    ids = page.by_id()
    tabs = [e for e in page.elements if e["tag"] == "button" and "nav-link" in e["attrs"].get("class", "").split()]

    assert len(tabs) == 6
    for tab in tabs:
        panel = ids[tab["attrs"]["aria-controls"]]
        assert tab["attrs"].get("role") == "tab"
        assert tab["attrs"]["data-bs-target"] == "#" + tab["attrs"]["aria-controls"]
        assert "href" not in tab["attrs"]                       # not valid on a button
        assert panel["attrs"].get("role") == "tabpanel"
        assert panel["attrs"]["aria-labelledby"] == tab["attrs"]["id"]
    assert [t["attrs"]["aria-selected"] for t in tabs].count("true") == 1


# ---------------------------------------------------------------- everything that can be named has a name

def test_dialogs_and_panels_are_named(page):
    ids = page.by_id()
    unnamed = []
    for element in page.elements:
        classes = element["attrs"].get("class", "").split()
        if "modal" in classes or "offcanvas" in classes:
            label = element["attrs"].get("aria-label") or ids.get(element["attrs"].get("aria-labelledby"), {}).get("text", "")
            if not label.strip():
                unnamed.append(element["attrs"].get("id"))
    assert unnamed == []


def test_close_buttons_are_named(page):
    closes = page.with_class("btn-close")

    assert len(closes) >= 4
    assert [c for c in closes if not c["attrs"].get("aria-label", "").strip()] == []


def test_the_header_buttons_are_named(page):
    buttons = page.with_class("gfg-chip")

    assert len(buttons) == 3
    assert [b for b in buttons if not (b["attrs"].get("aria-label") or b["text"].strip())] == []


def test_the_preset_menu_has_a_label(page):
    menu = page.by_id()["grid-presets"]
    label = page.by_id().get(menu["attrs"].get("aria-labelledby"))

    assert label is not None and label["text"].strip()


def test_the_preview_placeholder_is_named_by_its_own_text(page):
    """Its aria-label ("Load the 3D preview") did not contain the words shown on it"""
    placeholders = page.with_class("viewer-placeholder")

    assert len(placeholders) == 5
    assert [p for p in placeholders if "aria-label" in p["attrs"]] == []
    assert all("3D preview is off" in p["text"] for p in placeholders)
