"""Repo-local declarations for tests/test_openapi_contract.py (atrium-project#32 round 2).

Never vendored, never in para-drift, never in the ruff [format] exclude — unlike the
canonical test that reads it, this file's content is per repo by design: which services the
repo runs, where their committed specs live, which settings could reach a spec, and which
requirement files pin fastapi and pydantic. See the canonical test's docstring.
"""

from __future__ import annotations

#: One entry per HTTP service of this repo. `primary`: the domain endpoints whose JSON 200
#: must be a named model (strategy §4.2).
SERVICES = [
    {
        "service": "atrium-keyword-extract",
        "service_previous": "atrium-nlp-enrich",
        "app": "service.api:app",
        "spec": "service/openapi.json",
        "primary": ["/extract_keywords", "/extract_keywords_text"],
    },
]

#: Settings besides every [limit] variable (which the test perturbs from tool_limits.LIMITS)
#: that a deployment changes and that must not change the spec. DEFAULT_KW_METHOD is the one
#: that did (atrium-project#32 round 2): it was the `kw_method` form default.
ENV_PERTURB = {
    "DEFAULT_KW_METHOD": "yake",
    "ALLOWED_ORIGINS": "https://example.org",
}

#: Every requirements file a lane or an image installs fastapi or pydantic from: the api image
#: (service/requirements.txt) and the light and docker-tool test lanes (requirements-test.txt).
PIN_FILES = ["service/requirements.txt", "requirements-test.txt"]

#: Run before the app is imported (``MODULE:FUNCTION``), or None: this service imports light.
PREPARE = None
