#!/usr/bin/env bash
# Start the ATRIUM keyword-extract API server and wait until it is READY (strategy Appendix C).
#
# Behaviour:
#   1. GET <base-url>/ready answers 200 -> exit 0 (idempotent).
#   2. Otherwise start it: Docker Compose (`api` profile) by default, --gpu adds the GPU overlay,
#      --local runs the service in the repository's venv. Docker first pulls the released image of
#      this branch's version (para_config.txt [tool] version), which also carries the AMČR/TEATER
#      vocabulary the controlled kind needs; when it cannot, compose builds the image from this
#      checkout, and then only the statistical kind is available.
#   3. Poll /ready for up to 15 minutes (the first start downloads the KeyBERT model); on timeout
#      say where the logs are and exit non-zero.
#
# Polls /ready, not /info (issue #55): /info answers as soon as the process is up, /ready only once
# the KeyBERT model and, when configured, the controlled kind have warmed up.
#
# Usage:
#   bash scripts/server.sh            # Docker, or local when Docker is not available
#   bash scripts/server.sh --gpu      # Docker with the GPU overlay (docker-compose.gpu.yaml)
#   bash scripts/server.sh --local    # skip Docker, run the service in venv-kw
#
# Environment:
#   ATRIUM_KW_PORT  - port to serve on (default: 8000)
#   ATRIUM_KW_URL   - health-check target (default: http://localhost:$ATRIUM_KW_PORT)
#   ATRIUM_VERSION  - image tag to run (default: this branch's release, e.g. 1.4.0-beta)
#   LLM_BACKEND, OPENROUTER_API_KEY, OPENROUTER_MODEL, OLLAMA_HOST, OLLAMA_MODEL
#                   - the controlled kind's backend (in .env for Docker); without one, the
#                     statistical kind still works

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${ATRIUM_KW_PORT:-8000}"
BASE_URL="${ATRIUM_KW_URL:-http://localhost:${PORT}}"
HEALTH_URL="${BASE_URL}/ready"
MODE="auto"

for arg in "$@"; do
    case "$arg" in
        --gpu)   MODE="gpu" ;;
        --local) MODE="local" ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    echo "✅ API already ready at ${BASE_URL}"
    exit 0
fi

cd "$REPO_ROOT"

start_docker() {
    # The image tag is the release this branch was derived from, without the leading "v".
    ATRIUM_VERSION="${ATRIUM_VERSION:-$(sed -n 's/^version *= *v\{0,1\}//p' para_config.txt | head -1)}"
    export ATRIUM_VERSION PORT
    echo "🐳 Starting keyword-extract ${ATRIUM_VERSION} via docker compose ($* api profile)..."
    docker compose "$@" --profile api pull kw-api \
        || echo "Could not pull the ${ATRIUM_VERSION} image; building it from this checkout (statistical kind only)."
    docker compose "$@" --profile api up -d kw-api
}

start_local() {
    echo "🐍 Starting the service locally (statistical kind; the vocabulary is in the published image)..."
    if [ ! -d "venv-kw" ]; then
        echo "No venv found - creating venv-kw and installing requirements.txt and service/requirements.txt..."
        python3 -m venv venv-kw
        # shellcheck disable=SC1091
        source venv-kw/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt -r service/requirements.txt
    else
        # shellcheck disable=SC1091
        source venv-kw/bin/activate
    fi
    PORT="$PORT" nohup python -m service.api > api_server.log 2>&1 &
    echo "Server PID: $! (logs: api_server.log)"
}

case "$MODE" in
    gpu)   start_docker -f docker-compose.yaml -f docker-compose.gpu.yaml ;;
    local) start_local ;;
    auto)
        if command -v docker > /dev/null 2>&1 && docker info > /dev/null 2>&1; then
            start_docker
        else
            start_local
        fi
        ;;
esac

echo "⏳ Waiting for ${HEALTH_URL} (the first start downloads the KeyBERT model, ~500 MB)..."
DEADLINE=$((SECONDS + 900))
until curl -sf "$HEALTH_URL" > /dev/null 2>&1; do
    if [ "$SECONDS" -ge "$DEADLINE" ]; then
        echo "❌ Server did not become ready within 15 minutes." >&2
        echo "   Check: api_server.log (local) or 'docker compose --profile api logs kw-api' (Docker)." >&2
        exit 1
    fi
    sleep 5
done

echo "✅ API ready at ${BASE_URL}"
