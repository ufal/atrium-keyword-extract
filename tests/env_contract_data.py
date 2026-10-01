"""Repo-local declarations for tests/test_env_contract.py (atrium-project#60).

Never vendored, never in para-drift, never in docs/templates/ruff.toml's [format]
exclude — unlike test_env_contract.py itself, this file's SHAPE is per-repo by
design. See the canonical test's module docstring for the full rationale.
"""

from __future__ import annotations

# Read by shipped code but deliberately absent from .env.example, each with a reason: the batch
# CLIs (keywords.py, llm_run.py) have their own settings (kw_config.txt, llm_config.txt), distinct
# from the api image's HTTP entrypoint. The api entrypoint (service/api.py) never imports these.
NOT_PUBLISHED: dict[str, str] = {
    "HF_TOKEN": "read only by llm_run.py, the research LLM batch CLI (llm_run.py); service/api.py never imports it",
    "PARADATA_DIR": "read only by keywords.py, the batch CLI; not reachable from the service entrypoint",
    "PROMPT_TEMPLATE": "read only by prompt_template.py via llm_run.py, the batch CLI; not reachable from the service entrypoint",
    "PROMPT_GEO_GUARDRAIL": "read only by prompt_template.py via llm_run.py, the batch CLI; not reachable from the service entrypoint",
    "PROMPT_VOCAB_GROUPING": "read only by prompt_template.py via llm_run.py, the batch CLI; not reachable from the service entrypoint",
}

# In .env.example but read by no Python in this repo — each with a reason.
CONSUMED_ELSEWHERE: dict[str, str] = {
    "ATRIUM_VERSION": "read only by docker-compose.yaml to pick the image tag; no Python here reads it",
    "ATRIUM_UID": "read only by docker-compose.yaml (`user: ${ATRIUM_UID:-10001}:0`); no Python here reads it",
    "HF_HOME": "read by huggingface_hub itself, set by the Dockerfile and docker-compose.yaml",
}

# service/README.md or .env.example cells whose value is prose rather than a literal
# the code-default resolver can compare against.
PROSE_DEFAULTS: dict[str, str] = {
    "API_JOBS_ROOT": "computed from the repo root at runtime; the .env.example comment gives it in prose, not as a literal",
    "API_KEEP_WORKSPACES": "README describes the default in prose ('unset') rather than repeating the blank literal",
}
