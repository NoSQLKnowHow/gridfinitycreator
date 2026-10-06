#!/bin/bash

# Use the Compose plugin (`docker compose`) when it is installed, otherwise the legacy `docker-compose`
if docker compose version >/dev/null 2>&1; then COMPOSE="docker compose"; else COMPOSE="docker-compose"; fi

# See deploy.sh: the compose file needs this external network to exist
docker network inspect proxy >/dev/null 2>&1 || docker network create proxy >/dev/null

$COMPOSE --env-file ./.env.container -f docker-compose.debug.yml up -d --build
