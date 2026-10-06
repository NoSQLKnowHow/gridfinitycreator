#!/bin/bash

# Use the Compose plugin (`docker compose`) when it is installed, otherwise the legacy `docker-compose`
if docker compose version >/dev/null 2>&1; then COMPOSE="docker compose"; else COMPOSE="docker-compose"; fi

# Local settings live in .env.container, which is not kept in git. The compose file refuses to start
# without it, so make it from the template (all comments: the defaults apply) on a first start.
[ -f ./.env.container ] || { cp ./.env.container.template ./.env.container && echo "Created .env.container from the template"; }

# The log directory that is mounted into the container. If it does not exist Docker creates it owned
# by root, which the server (it runs as uid 1000) cannot write to; made here it is yours.
DATA_ROOT_DIR="${DATA_ROOT:-$(sed -n 's/^DATA_ROOT=//p' ./.env.container | tail -n 1)}"
LOG_DIR="${DATA_ROOT_DIR:-./data}/gridfinitycreator/debug_logs"
mkdir -p "$LOG_DIR"
if [ "$(stat -c %u "$LOG_DIR" 2>/dev/null)" != "1000" ]; then
    echo "Note: $LOG_DIR is not owned by uid 1000, which the server runs as. It will still start, but log"
    echo "to a temporary directory. To keep the logs:  sudo chown 1000:1000 \"$LOG_DIR\""
fi

# See deploy.sh: the compose file needs this external network to exist
docker network inspect proxy >/dev/null 2>&1 || docker network create proxy >/dev/null

$COMPOSE --env-file ./.env.container -f docker-compose.debug.yml up -d --build
