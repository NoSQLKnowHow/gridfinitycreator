# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Web app that dynamically generates STL/STEP files for Gridfinity-compatible 3D-printable components using CadQuery. Fork of jeroen94704/gridfinitycreator; the active branch (`more-new-features`) and the `feature/config-library` branch belong to the NoSQLKnowHow fork.

## Commands

All Docker-based; there is no test suite.

- `./build.sh` — build the Docker image (tagged `cadquery`)
- `./deploy.sh` — production deployment via Waitress (`docker-compose --env-file ./.env.container up`)
- `./debug.sh` — development mode using the built-in Flask server (`docker-compose.debug.yml`), with debugging conveniences
- `docker-compose.portainer.yml` — simplified stack for Portainer (no `DATA_ROOT` env or external `proxy` network required)
- Server listens on port 5000

## Architecture — plugin-based generators

- `gfg_main.py` is the Flask entry point. At startup, `load_generators()` scans `generators/` and imports each subdirectory's `main.py` via importlib; routes and the UI are built dynamically from whatever generators are found.
- Each generator directory (e.g. `generators/classicbin/`) contains: `main.py` (plugin entry), `*_generator.py` (CadQuery geometry), `*_form.py` (Flask-WTF settings form), `*_settings.py`, and `*_description.html` (help text).
- `generators/common/` holds shared code: `bin_base.py`, `dimensions.py`, `export.py` (STL/STEP export), `layout.py`, and the shared settings-form template.
- `grid_constants.py` defines Gridfinity dimensional constants; `help_provider.py` + `help_files/` serve the help pages.
- To add a new component type, copy the structure of an existing generator directory — no central registration needed.
