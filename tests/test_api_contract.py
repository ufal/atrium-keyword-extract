"""tests/test_api_contract.py — ATRIUM API meta-contract conformance (strategy §4, issue #32).

Hermetic contract test: asserts the ``/info`` envelope, ``/health``, ``/ready`` (issue #55),
the advertised endpoint set, and OpenAPI validity against the in-process app. ``importorskip``-guarded and tolerant of
missing service dependencies, so it is a clean no-op in the fast lane and a real check in CI.
"""

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

# --- per-service contract parameters -----------------------------------------------------------
SERVICE = "atrium-nlp-enrich"
APP_IMPORT = "service.api"
PRIMARY_ENDPOINTS = ["/enrich", "/enrich_text", "/rescale", "/jobs"]
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
# these add is the part only this repo can do: drive the real endpoints (the pipeline replaced
# by a stand-in for run_pipeline.py, as tests/test_api_service.py does) and hold every
# response — 200s and refusals alike — to the schema the PUBLISHED spec declares for it.

import json  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import atrium_openapi  # noqa: E402
from service import enrichment as _enr  # noqa: E402

_SPEC = atrium_openapi.load(Path(__file__).resolve().parent.parent / "service" / "openapi.json")

_TEITOK = """<?xml version="1.0" encoding="utf-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang="cs">
  <facsimile><surface id="d.surface1" lrx="1000" lry="2000"><graphic url="d-1.png"/></surface></facsimile>
  <text><body><pb n="1" id="d.pb1" facs="d-1.png"/>
    <div type="Zone" id="d.b1" bbox="100 200 300 400"><s id="d.s1" text="Praha"><tok id="d.s1.w1" bbox="100 200 150 240">Praha</tok></s></div>
  </body></text>
</TEI>
"""


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    """A stand-in for run_pipeline.py: a TEITOK output and nothing else (no network, no models)."""
    calls = []

    def _run(cmd, **_kwargs):
        calls.append(list(cmd))
        workspace = Path(cmd[cmd.index("--config") + 1]).parent
        teitok_dir = workspace / "out" / "TEITOK"
        teitok_dir.mkdir(parents=True, exist_ok=True)
        (teitok_dir / "doc.teitok.xml").write_text("<TEI/>", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(_enr, "_API_JOBS_ROOT", tmp_path)
    monkeypatch.setattr(_enr.subprocess, "run", _run)
    return calls


def _conforms(method, path, status, response, spec_path=None):
    pytest.importorskip("jsonschema")
    assert response.status_code == status, response.text
    atrium_openapi.validate_response(_SPEC, spec_path or path, method, status, response.json())
    return response.json()


def test_enrich_response_conforms_to_the_published_schema(pipeline):
    response = client.post(
        "/enrich",
        files={"file": ("doc.csv", b"text\nPraha\n", "text/csv")},
        data={"kw_method": "none"},
    )
    body = _conforms("post", "/enrich", 200, response)
    assert body["method_requested"] == "none" and body["llm"] is None


def test_enrich_text_uses_the_server_default_method_and_conforms(pipeline, monkeypatch):
    """No `kw_method`: the server's DEFAULT_KW_METHOD applies — the spec's default is null."""
    from service import api

    monkeypatch.setattr(api, "DEFAULT_KW_METHOD", "none")
    body = _conforms(
        "post", "/enrich_text", 200, client.post("/enrich_text", json={"lines": ["Praha"]})
    )
    assert body["method_requested"] == "none"
    kw = _SPEC["components"]["schemas"]["EnrichTextRequest"]["properties"]["kw_method"]
    assert kw.get("default") is None


def test_an_unsupported_file_type_is_415_unsupported_media_type(pipeline):
    response = client.post("/enrich", files={"file": ("doc.pdf", b"%PDF-1.7", "application/pdf")})
    body = _conforms("post", "/enrich", 415, response)
    assert body["reason"] == "unsupported_media_type" and ".csv" in body["accepted"]
    assert body["detail"].startswith("Unsupported file type '.pdf'.")
    assert pipeline == []


@pytest.mark.parametrize(
    "part", [b"[1]", b"{not json", b'{"schema_version": "3.0", "doc_id": "x"}']
)
def test_a_record_that_cannot_be_opened_is_422_invalid_record_before_the_pipeline(pipeline, part):
    files = {
        "file": ("doc.csv", b"text\nPraha\n", "text/csv"),
        "document_json": ("doc.document.json", part, "application/json"),
    }
    body = _conforms(
        "post", "/enrich", 422, client.post("/enrich", files=files, data={"kw_method": "none"})
    )
    assert body["reason"] == "invalid_record" and pipeline == []


def test_an_inline_record_that_cannot_be_opened_is_422_invalid_record(pipeline):
    response = client.post(
        "/enrich_text",
        json={"lines": ["Praha"], "kw_method": "none", "document_json": {"schema_version": "2.0"}},
    )
    body = _conforms("post", "/enrich_text", 422, response)
    assert body["reason"] == "invalid_record" and pipeline == []


@pytest.mark.parametrize(
    "data",
    [{"kw_method": "bogus"}, {"format": "tar"}, {"lang": "de"}, {"num_keywords": "0"}],
    ids=["kw_method", "format", "lang", "num_keywords"],
)
def test_a_value_outside_the_published_enum_or_bounds_is_422(pipeline, data):
    """The spec's enums and bounds are what the server enforces (an unknown `format` used to
    fall back to JSON silently)."""
    files = {"file": ("doc.csv", b"text\nPraha\n", "text/csv")}
    body = _conforms("post", "/enrich", 422, client.post("/enrich", files=files, data=data))
    assert body["reason"] is None and body["errors"] and pipeline == []


#: An AMČR seed (atrium-project#71): the file id and the archive's own view of the original.
_AMCR_SEED = {
    "doc_id": "C-202000543A-DT-27",
    "source": {"sha512": "c" * 128, "filename": "zprava.pdf", "media_type": "application/pdf"},
}


@pytest.fixture
def pipeline_run(tmp_path, monkeypatch):
    """The stand-in above, plus what a real run leaves for the envelope: the stats stage's
    paradata, the run's merged record, and the record that stage stamped with its run_uuid."""
    from atrium_document import DocumentRecord
    from atrium_paradata import ParadataLogger, merge_run_paradata

    def _run(cmd, **_kwargs):
        out = Path(cmd[cmd.index("--config") + 1]).parent / "out"
        (out / "TEITOK").mkdir(parents=True, exist_ok=True)
        (out / "TEITOK" / "doc.teitok.xml").write_text(_TEITOK, encoding="utf-8")
        stage = ParadataLogger(
            "nlp-enrich", {"script": "api_4_stats"}, paradata_dir=str(out / "paradata")
        )
        merge_run_paradata(
            [stage.finalize()],
            str(out / "paradata" / f"{stage.run_id}_nlp-enrich_pipeline-run.json"),
            pipeline="nlp-enrich",
        )
        if "--document-json-out" in cmd:
            with DocumentRecord.open(
                "doc",
                "nlp-enrich",
                baseline=cmd[cmd.index("--document-json") + 1],
                run_id=stage.run_id,
                run_uuid=stage.run_uuid,
                paradata_ref=stage.paradata_ref,
            ) as doc:
                doc.add_derived_from("teitok", "TEITOK/doc.teitok.xml")
                doc.finalize(cmd[cmd.index("--document-json-out") + 1])
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(_enr, "_API_JOBS_ROOT", tmp_path)
    monkeypatch.setattr(_enr.subprocess, "run", _run)


def test_an_amcr_seed_keeps_its_identity_and_the_run_is_returned(pipeline_run):
    """atrium-project#71 through /enrich: the seed's id and source come back unchanged, and
    `paradata` is the run's CreateAction, whose @id is the run_uuid the stats stage stamped."""
    from atrium_rocrate import action_problems

    files = {
        "file": ("doc.csv", b"text\nPraha\n", "text/csv"),
        "document_json": (
            "seed.document.json",
            json.dumps(_AMCR_SEED).encode(),
            "application/json",
        ),
    }
    body = _conforms(
        "post", "/enrich", 200, client.post("/enrich", files=files, data={"kw_method": "none"})
    )
    record, action = body["document_json"], body["paradata"]
    assert record["doc_id"] == _AMCR_SEED["doc_id"] and record["source"] == _AMCR_SEED["source"]

    assert action_problems(action) == []
    assert action["@id"] == record["assembled"]["blocks"]["derived_from"]["run_uuid"]
    assert [e["name"] for e in action["object"]] == ["doc.csv", "C-202000543A-DT-27.document.json"]
    assert {"#block-derived_from"} <= {e["@id"] for e in action["result"]}
    assert "doc.teitok.xml" in {e["name"] for e in action["result"]}


def test_without_a_record_the_action_is_the_merged_runs(pipeline_run):
    from atrium_rocrate import action_problems

    body = _conforms(
        "post",
        "/enrich_text",
        200,
        client.post("/enrich_text", json={"lines": ["Praha"], "kw_method": "none"}),
    )
    action = body["paradata"]
    assert action_problems(action) == []
    assert action["@id"] == action["paradataRecord"]["run_uuid"]  # the merged run's own id
    assert [e["name"] for e in action["object"]] == ["lines.json"]


def test_the_jobs_api_conforms_to_the_published_schema(pipeline):
    accepted = client.post(
        "/jobs",
        files={"file": ("doc.csv", b"text\nPraha\n", "text/csv")},
        data={"kw_method": "none"},
    )
    job_id = _conforms("post", "/jobs", 200, accepted)["job_id"]
    status = client.get(f"/jobs/{job_id}")
    _conforms("get", f"/jobs/{job_id}", 200, status, spec_path="/jobs/{job_id}")
    missing = client.get("/jobs/no-such-job")
    _conforms("get", "/jobs/no-such-job", 404, missing, spec_path="/jobs/{job_id}")
    unfinished = client.get("/jobs/no-such-job/result")
    _conforms("get", "/jobs/no-such-job/result", 404, unfinished, spec_path="/jobs/{job_id}/result")


def test_rescale_response_conforms_to_the_published_schema():
    response = client.post(
        "/rescale",
        files={"file": ("d.teitok.xml", _TEITOK.encode(), "application/xml")},
        data={"scale": "0.5"},
    )
    body = _conforms("post", "/rescale", 200, response)
    assert body["pages"][0]["target"] == {"width": 500, "height": 1000}
