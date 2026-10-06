# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Web app that dynamically generates STL/STEP files for Gridfinity-compatible 3D-printable components using CadQuery. Fork of jeroen94704/gridfinitycreator; the active branch (`more-new-features`) and the `feature/config-library` branch belong to the NoSQLKnowHow fork.

## Commands

Deployment is Docker-based. Tests run directly: `pip install cadquery==2.8.0 -r requirements-dev.txt && pytest` (needs CadQuery; about a minute; also runs `tests/js` if Node is installed). CI also builds the image, tests inside it and smoke-tests the hardened container (`tools/smoke_test.py`).

- `./build.sh` — build the Docker image (tagged `cadquery`)
- `./deploy.sh` — production deployment via Waitress (`docker-compose --env-file ./.env.container up`)
- `./debug.sh` — development mode using the built-in Flask server (`docker-compose.debug.yml`), with debugging conveniences
- `docker-compose.portainer.yml` — simplified stack for Portainer (no `DATA_ROOT` env or external `proxy` network required)
- Server listens on port 5000 (`FLASK_PORT`); every `GFG_*` setting is documented in the README

## Architecture — plugin-based generators

- `gfg_main.py` is the Flask entry point. At startup, `load_generators()` scans `generators/` and imports each subdirectory's `main.py` via importlib; routes and the UI are built dynamically from whatever generators are found.
- Each generator directory (e.g. `generators/classicbin/`) contains: `main.py` (plugin entry), `*_generator.py` (CadQuery geometry), `*_form.py` (Flask-WTF settings form), `*_settings.py`, and `*_description.html` (help text).
- `generators/common/` holds shared code: `bin_base.py`, `dimensions.py`, `export.py` (STL/STEP export), `layout.py`, and the shared settings-form template.
- `grid_constants.py` defines Gridfinity dimensional constants; `help_provider.py` + `help_files/` serve the help pages.
- To add a new component type, copy the structure of an existing generator directory — no central registration needed.

## Request flow and process model

- `gfg_main.py` validates the submitted form (Flask-WTF; numeric fields use `generators/common/validators.Bounded`), then asks the generator to build. Refusals that depend on the grid in use raise `generators/common/errors.SettingsError` (from the generator's `__init__`/`validate_settings`) and are shown to the user as a 422; cost limits live in `generators/common/limits.py`.
- Building a model is CPU-heavy and CadQuery's native calls hold the GIL, so builds never run in the web server's threads: `model_builder.build()` runs them in a child process (multiprocessing fork server, pre-loaded via `build_preload.py`) with a hard timeout, and `job_limiter.py` bounds how many run or wait at once. Cheap requests (page loads, the `dimensions` readout) never take a slot.
- A script that launches the server must keep that behind `if __name__ == "__main__"`: build children import the launching script by path.
- Abandoned requests are dropped, not built: the page aborts the preview request it replaces (`static/latest_request.js`), and `gfg_main.generate()` hands waitress's `waitress.client_disconnected` check to `limiter.slot()` (a waiting request leaves the queue) and `model_builder.stop_when_gone()` (a running build's child is killed); the client gets a 499 nobody reads. Waitress only reports a hang-up to a running request when started with `channel_request_lookahead` > 0, so start it with `job_limiter.server_options(limiter)`. Flask's own dev server provides no such check, and everything then behaves as before.
- `generator_loader.py` discovers the generator plugins (shared by the web app and the build processes); `gridspec.py` validates the grid cookie and the Advanced settings form.
- Add a test with each fix: `tests/conftest.py` has helpers that submit forms the way the browser does (`post_form`), and `dimensions="true"` runs all validation without building any geometry.
