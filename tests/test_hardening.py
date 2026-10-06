"""The container runs as an ordinary user on a read-only filesystem, its dependencies are pinned to
what the tests ran against, and a CI workflow builds the image and tests it.

Most of this only shows on someone's server (or in a CI run), so the choices are pinned here.
"""

import os
import re
import subprocess

import pytest
import yaml

from conftest import REPO
from test_deployment_files import COMPOSE_FILES, StrictLoader, read, services


def dockerfile_lines():
    return [line.strip() for line in read("Dockerfile").splitlines() if line.strip() and not line.strip().startswith("#")]


# ---------------------------------------------------------------- the image

def test_the_image_does_not_run_as_root():
    users = [line.split(None, 1)[1] for line in dockerfile_lines() if line.upper().startswith("USER ")]

    assert users, "the Dockerfile has no USER, so the server runs as root"
    assert users[-1].split(":")[0] not in ("root", "0")


def test_the_working_directories_belong_to_that_user():
    """A volume that Docker creates is root's; the directories in the image must be the user's"""
    text = read("Dockerfile")

    assert re.search(r"chown\b[^\n]*(/tmpfiles)[^\n]*(/logs)|chown\b[^\n]*(/logs)[^\n]*(/tmpfiles)", text)


def test_the_image_pins_cadquery_to_a_tested_version():
    """Unpinned, every rebuild may bring a new CadQuery: the history has two breakages from that"""
    assert re.search(r"cadquery=2\.\d+\.\d+", read("Dockerfile"))


def test_the_image_does_not_update_conda_at_build_time():
    """`conda update conda` makes two builds of the same commit differ"""
    assert "conda update conda" not in read("Dockerfile")


def test_the_graphics_library_comes_from_packages_that_exist_on_current_debian():
    """libgl1-mesa-glx was dropped in Debian 13, which the next base image may be"""
    instructions = "\n".join(dockerfile_lines())   # not the comments, which explain what was replaced

    assert "libgl1-mesa-glx" not in instructions
    assert re.search(r"\blibgl1\b", instructions)


def test_the_base_image_is_a_specific_release():
    assert re.search(r"^FROM continuumio/miniconda3:\d+\.\d+\.\d+-\d+\s*$", read("Dockerfile"), re.M)


def test_python_does_not_try_to_write_bytecode_into_a_read_only_filesystem():
    assert "PYTHONDONTWRITEBYTECODE" in read("Dockerfile")


# ---------------------------------------------------------------- the compose files

@pytest.mark.parametrize("name", COMPOSE_FILES)
def test_every_service_runs_unprivileged(name):
    for service_name, service in services(name):
        assert str(service.get("user", "")).split(":")[0] not in ("", "root", "0"), service_name
        assert "ALL" in service.get("cap_drop", []), service_name
        assert "no-new-privileges:true" in service.get("security_opt", []), service_name


@pytest.mark.parametrize("name", COMPOSE_FILES)
def test_the_root_filesystem_is_read_only_and_the_scratch_space_is_bounded(name):
    for service_name, service in services(name):
        assert service.get("read_only") is True, service_name
        tmpfs = {entry.split(":")[0]: entry for entry in service["tmpfs"]}
        assert "/tmp" in tmpfs, f"{service_name}: the model builder's fork server needs a writable /tmp"
        for path in ("/tmpfiles", "/tmp"):
            assert "size=" in tmpfs[path], f"{service_name}: {path} is a RAM disk with no size limit"
        # the user the server runs as must be able to write to it
        assert re.search(r"uid=1000", tmpfs["/tmpfiles"]), service_name


@pytest.mark.parametrize("name", COMPOSE_FILES)
def test_memory_is_limited_and_the_limit_can_be_changed(name):
    """Under deploy.resources, not mem_limit: as far as I know legacy docker-compose (which deploy.sh falls
       back to) rejects mem_limit in a version 3 file (not run here: only Compose v2 is available), while
       Compose v2 and Portainer honour the deploy limit"""
    for service_name, service in services(name):
        assert "mem_limit" not in service, service_name
        assert "GFG_MEM_LIMIT" in str(service["deploy"]["resources"]["limits"]["memory"]), service_name


@pytest.mark.parametrize("name", COMPOSE_FILES)
def test_no_linuxserver_style_user_settings_that_nothing_reads(name):
    """PUID and PGID do something for LinuxServer.io images; nothing in this image reads them"""
    for service_name, service in services(name):
        environment = service.get("environment", {})
        names = set(environment) if isinstance(environment, dict) else {entry.split("=")[0] for entry in environment}
        assert not names & {"PUID", "PGID"}, service_name


# ---------------------------------------------------------------- the settings file

def test_the_local_settings_file_is_not_in_the_repository():
    """It is one person's settings (the author's real domain); editing it conflicted with every pull"""
    try:
        tracked = subprocess.run(["git", "ls-files", ".env.container"], cwd=REPO, capture_output=True, text=True)
    except FileNotFoundError:
        pytest.skip("git is not installed (as in the image CI tests in)")
    if tracked.returncode != 0:
        pytest.skip("not a git checkout")

    assert tracked.stdout.strip() == ""
    assert ".env.container" in read(".gitignore").split()


def test_the_template_has_no_placeholder_that_would_be_used_as_a_value():
    """A first start copies it; DATA_ROOT=/path/to/your/logs would have created that path at the
       root of the disk, and the domain placeholder is not a domain"""
    values = [line for line in read(".env.container.template").splitlines() if line.strip() and not line.lstrip().startswith("#")]

    assert [line for line in values if "YOURDOMAIN" in line or "/path/to" in line] == []


@pytest.mark.parametrize("script", ["deploy.sh", "debug.sh"])
def test_the_scripts_create_the_settings_file_when_it_is_missing(script):
    """compose refuses to start if the env_file does not exist, and a fresh clone no longer has it"""
    assert re.search(r"\[ -f \./\.env\.container \]|test -f \./\.env\.container", read(script))


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


