#!/bin/bash

# Use the Compose plugin (`docker compose`) when it is installed, otherwise the legacy `docker-compose`
if docker compose version >/dev/null 2>&1; then COMPOSE="docker compose"; else COMPOSE="docker-compose"; fi

# The compose file attaches the container to an external network called "proxy" (for use with a
# reverse proxy). Create it if it does not exist yet, so a first start works.
docker network inspect proxy >/dev/null 2>&1 || docker network create proxy >/dev/null

$COMPOSE --env-file ./.env.container up --build --force-recreate --no-deps -d
