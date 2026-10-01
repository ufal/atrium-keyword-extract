# syntax=docker/dockerfile:1.7
FROM python:3.11-slim AS base

ARG ATRIUM_RUNNER_IMAGE=""
ARG ATRIUM_RUNNER_REPO="https://github.com/ufal/atrium-keyword-extract"
ARG ATRIUM_RUNNER_REF=""

ENV ATRIUM_RUNNER_IMAGE=${ATRIUM_RUNNER_IMAGE} \
    ATRIUM_RUNNER_REPO=${ATRIUM_RUNNER_REPO} \
    ATRIUM_RUNNER_REF=${ATRIUM_RUNNER_REF} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/cache/huggingface

# ── Distro security patches, applied at build time ───────────────────────────
# `python:3.11-slim` is a floating TAG, and nothing in this ecosystem bumps it:
# no repo declares a `docker` dependabot ecosystem (docker_gha_roadmap.md, H6),
# so the base layer is whatever Docker Hub last rebuilt. On 2026-09-15 that layer
# carried perl-base 5.40.1-6 with three FIXABLE CRITICAL CVEs — CVE-2026-13221,
# CVE-2026-42496 and CVE-2026-8376, all fixed in 5.40.1-6+deb13u1. The release
# gate in atrium-project's docker-tool.reusable.yml ("Fail the release on fixable
# CRITICAL vulnerabilities") therefore failed on ALL THREE matrix targets of
# v0.20.2 (run 34970419474), and because the promotion step is `if: success()`,
# v0.20.2 was published by DIGEST ONLY: the `:0.20.2` and `:latest` tags were
# never applied. The same commit passed on `master` and on `test`, because the
# gate is `if: startsWith(github.ref, 'refs/tags/')` — only a release is stopped.
#
# `upgrade` rather than `install --only-upgrade perl-base`, deliberately. The gate
# blocks on *fixable* CRITICALs — precisely those the distro already ships a patch
# for — so the fix that matches the gate's own definition is "apply the distro's
# available patches", not a package name that has to be edited by hand the next
# time a different one is announced.
#
# CACHE INTERACTION, which is what makes this hold rather than run once: the build
# uses `cache-from: type=gha`, so an apt layer high in the file would be served
# from cache forever and silently stop patching. It sits HERE, immediately after
# the ENV block that embeds ATRIUM_RUNNER_REF, because CI passes that as
# `github.ref_name` — a value unique to each release tag. The ENV layer therefore
# changes on every release, busting this layer with it, so every released image is
# scanned against a freshly patched base while day-to-day `test` pushes still hit
# the cache. Do not move this above the ENV block.
#
# One apt layer, not two: the upgrade and the install share a single `apt-get
# update`, so the package lists are fetched once and removed once.
# Guarded by tests/test_dockerfile_security_layer.py (atrium-project#53).
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Runtime requirements only (atrium-project#69, roadmap H4). requirements-test.txt (pytest,
# pytest-cov, httpx, openapi-spec-validator, PyYAML, …) used to be installed here too:
# nothing the ENTRYPOINTs reach imports a package only it carries, so it only added to all
# three images and to the Trivy surface the release gate scans. The tests run on the CI
# runner, never in an image. The `api` stage gets fastapi/pydantic (exact pins) and
# uvicorn from service/requirements.txt, as before.
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Non-root runtime user. Owned atrium:0 and group-writable (`g=u`): the arbitrary-UID
# convention (OpenShift's), atrium-project#69 / roadmap B6. docker-compose.yaml runs these
# images as `user: "${ATRIUM_UID:-10001}:0"`, so on Linux the container can run as the uid
# that owns the ./data bind mount, and a uid with no passwd entry still reaches /app,
# /cache, /data and $HOME through group 0. HOME is explicit because without a passwd entry
# it would be `/`. The default runtime -- uid 10001 as the owner -- is unchanged.
RUN useradd --create-home --uid 10001 atrium \
    && mkdir -p /cache/huggingface /data \
    && chown -R atrium:0 /app /cache /data /home/atrium \
    && chmod -R g=u /app /cache /data /home/atrium
ENV HOME=/home/atrium

USER atrium

# The batch form of the stage: the statistical keywords of CoNLL-U files (nlp-enrich's UDP/ output) or
# TEITOK, `python keywords.py -i <dir> -m keybert|yake|legacy`. Published as :<version>, never pinned;
# the production image is `api` below.
ENTRYPOINT ["python", "keywords.py"]
CMD []


# ---------------------------------------------------------------------------
# API surface — published as :<version>-api
# ---------------------------------------------------------------------------
FROM base AS api

USER root
COPY service/requirements.txt ./service_requirements.txt
RUN pip install -r service_requirements.txt
# Same arbitrary-UID ownership as `base` (atrium:0, g=u), re-applied to what this stage adds.
RUN chown -R atrium:0 /app /home/atrium \
    && chmod -R g=u /app /home/atrium
USER atrium

# EXPOSE tracks the DEFAULT port: it is image metadata and cannot read $PORT at
# runtime. Set PORT to move the listener, and publish with `-p <port>:<port>` to
# match. (issue #58)
EXPOSE 8000

# STOPSIGNAL is the default (SIGTERM) — declared explicitly so it is never silently
# changed by a future edit; service/api.py's lifespan (via serve_lifecycle,
# service/atrium_service.py) chains to uvicorn's own handler for it (issue #55).
STOPSIGNAL SIGTERM

# PORT and HOST are read by service/api.py's __main__ block; PORT is also the port
# service/healthcheck.py probes, which is why setting it used to make the container
# permanently unhealthy — the probe moved and the listener did not. Declared here so
# `docker inspect` is self-documenting and so the probe still has a value if the code
# default ever drifts. (issue #58)
#
# GRACEFUL_SHUTDOWN_S carries the `--timeout-graceful-shutdown 20` that used to sit on
# the ENTRYPOINT line. It bounds uvicorn's own wait for in-flight HTTP
# requests (20s here). --start-period
# on HEALTHCHECK below covers first-run model downloads (the KeyBERT embedding model); see docs/docker_gha.md §3.4
# and docs/k8s_deployment.md for the full grace-period budget this is sized against.
ENV PORT=8000 GRACEFUL_SHUTDOWN_S=20

# `python -m service.api`, NOT `python service/api.py`: a script launch puts
# sys.path[0] at /app/service with no package context, so `from .atrium_service import ...`
# raises "attempted relative import with no known parent package" before the app is
# built. `-m` keeps sys.path[0] at /app — byte for byte the environment the old
# `uvicorn service.api:app` entrypoint ran in, so every repo-root import still
# resolves. (issue #58)
ENTRYPOINT ["python", "-m", "service.api"]
CMD []
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD ["python", "/app/service/healthcheck.py"]


# ---------------------------------------------------------------------------
# Optional LLM/GPU variant — published as :<version>-llm
# ---------------------------------------------------------------------------
FROM base AS llm

USER root
COPY requirements_llm.txt ./

# Dynamically remove the strict torch==2.7.0 pin so vllm can install its required version
RUN sed -i '/^torch==/d' requirements_llm.txt \
    && pip install \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements_llm.txt

# Same arbitrary-UID ownership as `base` (atrium:0, g=u), re-applied to what this stage adds.
RUN chown -R atrium:0 /app /home/atrium \
    && chmod -R g=u /app /home/atrium
USER atrium

ENTRYPOINT ["python", "llm_run.py"]
CMD ["llm_config.txt"]