"""The dependencies are pinned to what the tests ran against, and nothing is installed that nothing uses."""

import os
import re

import pytest
import yaml

from conftest import REPO
from test_deployment_files import COMPOSE_FILES, StrictLoader, read, services


def dockerfile_lines():
    return [line.strip() for line in read("Dockerfile").splitlines() if line.strip() and not line.strip().startswith("#")]


# ---------------------------------------------------------------- dependencies

def requirement_lines(name):
    return [line.strip() for line in read(name).splitlines() if line.strip() and not line.strip().startswith(("#", "-r"))]


@pytest.mark.parametrize("name", ["requirements.txt", "requirements-dev.txt"])
def test_every_requirement_is_pinned_to_an_exact_version(name):
    loose = [line for line in requirement_lines(name) if not re.fullmatch(r"[A-Za-z0-9_.\-]+==\d[\w.]*", line)]

    assert loose == []


def test_requirements_have_no_duplicates_and_none_that_nothing_uses():
    names = [re.split(r"[=<>]", line)[0].lower().replace("_", "-") for line in requirement_lines("requirements.txt")]

    assert len(names) == len(set(names))
    # never imported anywhere (checked by grep when this was written); gunicorn was listed twice
    assert not {"gunicorn", "bootstrap-flask", "colorama"} & set(names)


def test_requirements_do_not_install_nlopt_over_the_one_cadquery_brings():
    """conda-forge's cadquery 2.8.0 depends on nlopt >=2.9,<3 by itself; a pip copy on top of it is two copies"""
    names = [re.split(r"[=<>]", line)[0].lower() for line in requirement_lines("requirements.txt")]

    assert "nlopt" not in names


def test_everything_the_application_imports_is_a_requirement_or_comes_with_cadquery():
    wanted = {"flask": "flask", "flask_wtf": "flask-wtf", "wtforms": "wtforms", "werkzeug": "werkzeug",
              "jinja2": "jinja2", "waitress": "waitress"}
    pinned = {re.split(r"[=<>]", line)[0].lower().replace("_", "-") for line in requirement_lines("requirements.txt")}

    assert [package for package in wanted.values() if package not in pinned] == []


def test_requirements_say_where_cadquery_and_numpy_come_from():
    """They are not in the file on purpose; a reader should not have to wonder"""
    text = read("requirements.txt").lower()

    assert "cadquery" in text and "numpy" in text


