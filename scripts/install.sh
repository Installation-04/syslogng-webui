#!/usr/bin/env bash
# Installs/updates syslogng-webui as a Docker container on Linux amd64 or arm64.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Installation-04/syslogng-webui/main/scripts/install.sh | bash
#   or, from a local clone:
#   ./scripts/install.sh
#
# Configuration (environment variables, all optional):
#   PORT            Web UI port                         (default: 8333)
#   LOG_DIR         Host directory for log storage       (default: ./syslogng-webui-logs)
#   TZ              Container timezone                   (default: UTC)
#   IMAGE_TAG       Image tag to install                 (default: latest)
#   CONTAINER_NAME  Docker container name                (default: syslogng-webui)
#   FORCE           Set to 1 to replace an existing container of the same name
set -euo pipefail

IMAGE_REPO="ghcr.io/installation-04/syslogng-webui"
PORT="${PORT:-8333}"
LOG_DIR="${LOG_DIR:-$PWD/syslogng-webui-logs}"
TZ="${TZ:-UTC}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
CONTAINER_NAME="${CONTAINER_NAME:-syslogng-webui}"
FORCE="${FORCE:-0}"

log() { printf '[install] %s\n' "$1"; }
die() { printf '[install] ERROR: %s\n' "$1" >&2; exit 1; }

# --- platform checks ---
[ "$(uname -s)" = "Linux" ] || die "this installer only supports Linux (got $(uname -s)). See README.md for other platforms."

arch="$(uname -m)"
case "$arch" in
  x86_64|amd64) docker_arch="amd64" ;;
  aarch64|arm64) docker_arch="arm64" ;;
  *) die "unsupported CPU architecture '$arch' - syslogng-webui publishes amd64 and arm64 images only." ;;
esac
log "detected architecture: $arch (docker platform: linux/$docker_arch)"

command -v docker >/dev/null 2>&1 || die "docker is required but not found. Install it first: https://docs.docker.com/engine/install/"
docker info >/dev/null 2>&1 || die "docker is installed but not usable (daemon not running, or permission denied - try with sudo or add your user to the 'docker' group)."

# --- handle an existing container ---
if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  if [ "$FORCE" != "1" ]; then
    die "a container named '$CONTAINER_NAME' already exists. Re-run with FORCE=1 to remove and reinstall it (log data in \$LOG_DIR is untouched), or 'docker rm -f $CONTAINER_NAME' yourself first."
  fi
  log "removing existing container '$CONTAINER_NAME' (FORCE=1)"
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

mkdir -p "$LOG_DIR"
log "log storage: $LOG_DIR"

log "pulling $IMAGE_REPO:$IMAGE_TAG"
docker pull --platform "linux/$docker_arch" "$IMAGE_REPO:$IMAGE_TAG"

log "starting container '$CONTAINER_NAME' on port $PORT"
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -p 514:514/udp \
  -p 514:514/tcp \
  -p "${PORT}:${PORT}" \
  -v "$LOG_DIR:/var/log/syslogng" \
  -e "PORT=${PORT}" \
  -e "TZ=${TZ}" \
  "$IMAGE_REPO:$IMAGE_TAG" >/dev/null

log "done. Web UI: http://localhost:${PORT}"
log "Point devices' remote syslog setting at this host's IP, port 514/UDP or TCP."
