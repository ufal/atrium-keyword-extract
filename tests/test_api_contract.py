"""tests/test_api_contract.py — ATRIUM API meta-contract conformance (strategy §4, issue #32).

Hermetic contract test: asserts the ``/info`` envelope, ``/health``, ``/ready`` (issue #55),
the advertised endpoint set, and OpenAPI validity against the in-process app. ``importorskip``-guarded and tolerant of
missing service dependencies, so it is a clean no-op in the fast lane and a real check in CI.
"""

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

# --- per-service contract parameters -----------------------------------------------------------
SERVICE = "atrium-keyword-extract"
APP_IMPORT = "service.api"
PRIMARY_ENDPOINTS = ["/extract_keywords", "/extract_keywords_text"]
# -----------------------------------------------------------------------------------------------

try:
    app = __import__(APP_IMPORT, fromlist=["app"]).app
# Only a missing dependency skips (atrium-project#53). This used to be `except Exception`,
# which turned ANY import-time failure into a green skip — including a malformed limit
# (atrium_limits.LimitConfigError), which must fail loudly.
except ImportError as exc:
    pytest.skip(f"cannot import {APP_IMPORT}.app: {exc}", allow_module_level=True)

client = TestClient(app)


def test_info_envelope_required_fields():
    """§4.1: /info always carries service, version, endpoints, limits.max_upload_mb."""
    response = client.get("/info")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == SERVICE
    assert data["version"] and data["version"] == app.version
    assert isinstance(data["endpoints"], list) and data["endpoints"]
    assert isinstance(data["limits"], dict)
    assert "max_upload_mb" in data["limits"]


def test_info_reports_every_declared_limit():
    """atrium-project#53: /info `limits` is tool_limits.LIMITS, value for value, and
    `limits_meta` names the variable that sets each one. tests/test_limits_contract.py checks
    the declaration against .env.example and the README."""
    from tool_limits import LIMITS

    data = client.get("/info").json()
    assert data["limits"] == LIMITS.values()
    assert data["limits_meta"] == LIMITS.meta()


def test_errors_have_the_harmonised_body():
    """§4.4 (atrium-project#32 item 2): every error is {status, reason, detail}."""
    body = client.get("/no-such-route").json()
    assert body == {"status": 404, "reason": None, "detail": "Not Found"}


def test_info_endpoints_match_real_routes():
    """Advertised endpoints are real routes, and every primary endpoint is advertised."""
    advertised = set(client.get("/info").json()["endpoints"])
    real = {r.path for r in app.routes if getattr(r, "methods", None)}
    assert advertised <= real
    for path in PRIMARY_ENDPOINTS:
        assert path in advertised, f"{path} missing from /info endpoints"


def test_health_shallow_ok():
    """§4.1: shallow /health is a cheap 200 liveness probe."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "degraded"}


def test_primary_endpoints_documented_in_openapi():
    paths = app.openapi()["paths"]
    for path in PRIMARY_ENDPOINTS:
        assert path in paths, f"{path} missing from OpenAPI paths"


def test_openapi_document_is_spec_valid():
    """The runtime /openapi.json validates against the OpenAPI 3.x spec (§2.2)."""
    spec_validator = pytest.importorskip("openapi_spec_validator")
    spec_validator.validate(app.openapi())


# --- §4.6 readiness + shutdown contract (issue #55) --------------------------------------------
# The state-machine itself is unit-tested once, in the hub
# (atrium-project/docs/templates/shared/test_atrium_service.py). What these assert is that THIS
# repo actually wired it up: the route exists, it is advertised, and — the one that matters —
# liveness does not start failing just because the service is draining.

try:
    _state = getattr(__import__(APP_IMPORT, fromlist=["app"]), "_state", None)
except Exception:  # noqa: BLE001 - same missing-heavy-deps case this file already guards
    # Repos guard the app import two different ways (module-level pytest.skip vs a
    # `deps_present` flag + pytestmark.skipif). Under the second style this module keeps
    # loading after a failed import, so this must not raise at import time; the skip
    # marker already stops the tests below from running.
    _state = None


def test_ready_route_is_registered_and_advertised():
    """§4.6: /ready exists, and /info advertises it like any other route."""
    assert _state is not None, (
        f"{APP_IMPORT} has no module-level `_state` — the service has not adopted "
        "ServiceState/attach_health(state=...) (issue #55)"
    )
    response = client.get("/ready")
    assert response.status_code in (200, 503)
    assert response.json()["status"] in {"ready", "starting", "draining"}
    assert "/ready" in client.get("/info").json()["endpoints"]


def test_ready_reports_starting_before_warmup_and_ready_after():
    """503 until the service's own lifespan marks it warm, 200 once it has.

    `client` above is a bare TestClient, so the ASGI lifespan has NOT run and the service is
    genuinely un-warm here — which is exactly the pre-warmup state a Kubernetes startupProbe
    sees on a cold pod.
    """
    assert _state is not None
    was_warm, was_draining = _state.warm, _state.draining
    try:
        _state.draining = False
        _state.warm = False
        assert client.get("/ready").status_code == 503
        assert client.get("/ready").json()["status"] == "starting"

        _state.warm = True
        assert client.get("/ready").status_code == 200
        assert client.get("/ready").json()["status"] == "ready"
    finally:
        _state.warm, _state.draining = was_warm, was_draining


def test_liveness_stays_200_while_draining_but_readiness_does_not():
    """The load-bearing distinction of issue #55.

    If shallow /health went 503 on SIGTERM, an orchestrator's livenessProbe would SIGKILL the
    container before its drain finished — the very failure the drain exists to prevent. Routing
    traffic away from a draining pod is /ready's job.
    """
    assert _state is not None
    was_warm, was_draining = _state.warm, _state.draining
    try:
        _state.warm = True
        _state.draining = True

        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        ready = client.get("/ready")
        assert ready.status_code == 503
        assert ready.json()["status"] == "draining"
    finally:
        _state.warm, _state.draining = was_warm, was_draining


def test_deep_health_reports_draining_with_operator_fields():
    """`?deep=true` had no coverage in any repo before issue #55."""
    assert _state is not None
    was_warm, was_draining = _state.warm, _state.draining
    try:
        _state.warm = True
        _state.draining = True
        response = client.get("/health?deep=true")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["detail"] == "shutting down"
        assert body["draining"] is True
        assert "in_flight" in body
    finally:
        _state.warm, _state.draining = was_warm, was_draining


# --- the typed contract (atrium-project#32 round 2) --------------------------------------------
# tests/test_openapi_contract.py (canonical, vendored) checks the committed spec itself. What
# these add is the part only this repo can do: drive the real endpoints and hold every response
# — 200s and refusals alike — to the schema the PUBLISHED spec declares for it. (The behaviour
# of the extraction is tests/test_api_service.py's.)

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import atrium_openapi  # noqa: E402

_SPEC = atrium_openapi.load(Path(__file__).resolve().parent.parent / "service" / "openapi.json")

_TEXT = "Archeologický výzkum odkryl zahloubený objekt se sídlištní keramikou a kamennými nástroji."


def _conforms(method, path, status, response):
    pytest.importorskip("jsonschema")
    assert response.status_code == status, response.text
    atrium_openapi.validate_response(_SPEC, path, method, status, response.json())
    return response.json()


def test_extract_text_response_conforms_to_the_published_schema():
    body = _conforms(
        "post",
        "/extract_keywords_text",
        200,
        client.post(
            "/extract_keywords_text", json={"text": _TEXT, "method": "yake", "num_keywords": 3}
        ),
    )
    assert body["keywords"] and body["paradata"]["@type"] == "CreateAction"


def test_extract_record_response_conforms_to_the_published_schema():
    record = {"doc_id": "AMCR-F-1", "lines": [{"page": "1", "line": 1, "text": _TEXT}]}
    files = {"document_json": ("r.document.json", json.dumps(record), "application/json")}
    body = _conforms(
        "post",
        "/extract_keywords",
        200,
        client.post(
            "/extract_keywords", files=files, data={"method": "yake", "kind": "statistical"}
        ),
    )
    assert body["doc_id"] == "AMCR-F-1" and body["pages"][0]["page"] == "1"


def test_the_server_default_method_applies_when_a_request_names_none(monkeypatch):
    """No `method`: the server's DEFAULT_KW_METHOD applies — the spec's default is null."""
    from service import api

    monkeypatch.setattr(api, "DEFAULT_KW_METHOD", "yake")
    body = _conforms(
        "post",
        "/extract_keywords_text",
        200,
        client.post("/extract_keywords_text", json={"text": _TEXT}),
    )
    assert body["method_requested"] == "yake"
    method = _SPEC["components"]["schemas"]["ExtractTextRequest"]["properties"]["method"]
    assert method.get("default") is None or "default" not in method


def test_the_controlled_kind_alone_is_a_501_error_body():
    body = _conforms(
        "post",
        "/extract_keywords_text",
        501,
        client.post("/extract_keywords_text", json={"text": _TEXT, "kind": "controlled"}),
    )
    assert body["status"] == 501 and body["reason"] is None


@pytest.mark.parametrize(
    "part", [b"[1]", b"{not json", b'{"schema_version": "3.0", "doc_id": "x"}']
)
def test_a_record_that_cannot_be_opened_is_422_invalid_record(part):
    files = {"document_json": ("r.document.json", part, "application/json")}
    body = _conforms(
        "post", "/extract_keywords", 422, client.post("/extract_keywords", files=files)
    )
    assert body["reason"] == "invalid_record"


@pytest.mark.parametrize(
    "data",
    [{"method": "bogus"}, {"kind": "all"}, {"lang": "de"}, {"num_keywords": "0"}],
    ids=["method", "kind", "lang", "num_keywords"],
)
def test_a_value_outside_the_published_enum_or_bounds_is_422(data):
    files = {
        "document_json": (
            "r.document.json",
            json.dumps({"doc_id": "x", "lines": []}),
            "application/json",
        )
    }
    body = _conforms(
        "post", "/extract_keywords", 422, client.post("/extract_keywords", files=files, data=data)
    )
    assert body["reason"] is None and body["errors"]


def test_over_the_upload_limit_is_413_limit_exceeded(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "0.0001")
    body = _conforms(
        "post",
        "/extract_keywords_text",
        413,
        client.post("/extract_keywords_text", json={"text": _TEXT * 20, "method": "yake"}),
    )
    assert body["reason"] == "limit_exceeded" and body["limit"]["key"] == "max_upload_mb"
