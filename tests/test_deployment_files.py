"""The Docker, compose and script files: mistakes in these only show up on someone's
server, so check the ones that have already bitten.
"""

import glob
import os
import re
import subprocess

import pytest
import yaml

from conftest import REPO

COMPOSE_FILES = ["docker-compose.yml", "docker-compose.debug.yml", "docker-compose.portainer.yml"]


def read(name):
    with open(os.path.join(REPO, name), encoding="utf-8") as handle:
        return handle.read()


class StrictLoader(yaml.SafeLoader):
    """A YAML loader that refuses duplicate keys. Most loaders silently keep the last one,
       and Docker Compose v2 refuses the file outright."""


def _no_duplicates(loader, node, deep=False):
    keys = [loader.construct_object(key, deep=deep) for key, _ in node.value]
    duplicates = {key for key in keys if keys.count(key) > 1}
    if duplicates:
        raise yaml.constructor.ConstructorError(None, None, f"duplicate key(s): {sorted(duplicates)}", node.start_mark)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)


def load_compose(name):
    return yaml.load(read(name), Loader=StrictLoader)


def dockerfile_env(name):
    """The value of an ENV variable set in the Dockerfile"""
    match = re.search(rf"\b{name}=(\S+)", read("Dockerfile"))
    assert match, f"{name} is not set in the Dockerfile"
    return match.group(1)


def container_path(volume):
    """The path inside the container of a "host:container[:mode]" volume. (Not simply the
       second field: the host part may contain colons, as in ${DATA_ROOT:-./data}.)"""
    host_and_container, _, last = volume.rpartition(":")
    if last in ("ro", "rw", "z", "Z"):
        host_and_container, _, last = host_and_container.rpartition(":")
    return last


def services(name):
    return load_compose(name)["services"].items()


@pytest.mark.parametrize("name", COMPOSE_FILES)
def test_compose_files_have_no_duplicate_keys(name):
    """docker-compose.debug.yml defined `environment:` twice, which Compose v2 refuses to parse"""
    load_compose(name)


@pytest.mark.parametrize("name", COMPOSE_FILES)
def test_the_ram_disk_and_the_log_volume_are_mounted_where_the_app_writes(name):
    """The app writes to GFG_TMP_DIR and GFG_LOG_DIR; a mount anywhere else is silently unused"""
    tmp_dir, log_dir = dockerfile_env("GFG_TMP_DIR"), dockerfile_env("GFG_LOG_DIR")

    for service_name, service in services(name):
        assert tmp_dir in [entry.split(":")[0] for entry in service.get("tmpfs", [])], service_name
        mounted = [container_path(volume) for volume in service.get("volumes", []) if isinstance(volume, str)]
        assert log_dir in mounted, service_name


def test_the_debug_server_is_only_published_on_the_loopback_address():
    """Its interactive debugger can run code on the machine"""
    [(_, service)] = services("docker-compose.debug.yml")

    assert service["ports"]
    assert all(port.startswith("127.0.0.1:") for port in service["ports"])
    assert service["environment"]["GFG_BIND"] == "0.0.0.0"  # needed inside the container for the port to reach it


def test_a_first_start_does_not_need_a_data_root():
    """The compose files used to refuse to start unless DATA_ROOT was set"""
    for name in ("docker-compose.yml", "docker-compose.debug.yml"):
        assert "DATA_ROOT:?" not in read(name)
        assert "DATA_ROOT:-" in read(name)


def test_the_image_has_its_working_directories_and_a_health_check():
    dockerfile = read("Dockerfile")

    assert re.search(r"mkdir -p /tmpfiles /logs", dockerfile)
    assert "HEALTHCHECK" in dockerfile


def test_the_docker_build_context_excludes_private_and_unneeded_files():
    ignored = read(".dockerignore").split()

    for entry in (".git", ".env*", "tests", "logs", "tmpfiles"):
        assert entry in ignored


@pytest.mark.parametrize("script", ["build.sh", "deploy.sh", "debug.sh"])
def test_scripts_are_valid_shell(script):
    subprocess.run(["bash", "-n", os.path.join(REPO, script)], check=True)


def test_scripts_work_with_both_compose_flavours():
    for script in ("deploy.sh", "debug.sh"):
        text = read(script)
        assert "docker compose version" in text and "docker-compose" in text


def test_every_setting_the_code_reads_is_documented():
    """A GFG_* variable the code reads but the README does not mention is invisible to users"""
    used = set()
    for path in glob.glob(os.path.join(REPO, "**", "*.py"), recursive=True):
        if os.sep + "tests" + os.sep in path or "/venv/" in path:
            continue
        used |= set(re.findall(r"\bGFG_[A-Z_]+\b", open(path, encoding="utf-8").read()))

    readme = read("README.md")
    undocumented = sorted(name for name in used if name not in readme)

    assert used, "expected to find GFG_ settings in the code"
    assert undocumented == [], f"not documented in the README: {undocumented}"
