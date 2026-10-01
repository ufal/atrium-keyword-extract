"""
service/api.py — FastAPI surface for the nlp-enrich pipeline.

The typed contract (atrium-project#32 round 2). Every route declares its response model and
its error statuses, so the committed ``service/openapi.json`` — attached to every release,
and what the AMČR pipeline generates its clients from — types every field. The models below
DOCUMENT the responses (``response_model=None``): the bytes sent are what the handlers build,
and ``tests/test_api_contract.py`` validates real responses against the published schema.
The parameters with a closed set of values (``kw_method``, ``lang``, ``format``) are enums
in the spec, and the default keyword method is the SERVER's (``DEFAULT_KW_METHOD``, reported
in ``/info``), no longer baked into the spec from the environment. Refusals carry registered
reasons: an unsupported file type is 415 ``unsupported_media_type``, a record that cannot be
opened is 422 ``invalid_record`` (it was dropped with a warning before). Every JSON success
carries the run's Process Run Crate ``CreateAction`` as ``paradata`` (atrium-project#71).
Regenerate the spec after an API change::

    python atrium_openapi.py export --app service.api:app --out service/openapi.json
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask

from .atrium_service import (
    AtriumDocument,
    AtriumHTTPError,
    CreateAction,
    InfoBase,
    LimitNote,
    ServiceState,
    add_cors,
    attach_error_handlers,
    attach_health,
    attach_inflight_middleware,
    attach_openapi_contract,
    build_info,
    busy,
    check_body_size,
    error_responses,
    operation_id,
    parse_record_part,
    read_tool_version,
    read_upload_bounded,
    serve_lifecycle,
)
from .enrichment import (
    KeywordPreflightError,
    Layout,
    PipelineError,
    PipelineManager,
    UnsupportedUploadType,
    count_words,
    is_teitok_upload,
    normalize_upload,
    read_alto_upload,
    sanitize_doc_id,
)
from .jobs import Job, _jobs, create_job
from .rescale import RescaleError, RescaleTooLarge, rescale_teitok

# isort: split
# The repo root is on sys.path from here on (service/enrichment.py puts it there, for the
# `python api.py` start from service/), so the repo-root modules are imported below it.
import atrium_rocrate  # noqa: E402
from atrium_limits import LimitExceeded  # noqa: E402
from tool_limits import (  # noqa: E402
    API_JOB_TIMEOUT,
    JOB_TTL_S,
    LIMITS,
    MAX_CONCURRENT_JOBS,
    MAX_QUEUED_JOBS,
    MAX_RESCALE_DIM,
    MAX_UPLOAD,
    MAX_WORDS,
)

# ── limits ─────────────────────────────────────────────────────────────────────
# Every limit is declared in tool_limits.py (atrium-project#53, factor III) and read per
# request; /info reports them all. The upload limit's import-time value stays here for
# the callers and tests that read it.
MAX_UPLOAD_MB = MAX_UPLOAD.get()
# The server's default keyword method. It is applied per request when a client sends none,
# and reported in /info `keyword_methods.default`; it is NOT the spec's default for the
# `kw_method` parameter (atrium-project#32 round 2): a spec that changed with this setting
# would not match the one attached to the release the image was built from.
DEFAULT_KW_METHOD = os.environ.get("DEFAULT_KW_METHOD", "keybert")

#: The tool id (/info `service`, the spec's `x-atrium-service`): the repository name.
SERVICE = "atrium-nlp-enrich"

_ALLOWED_KW = ("keybert", "yake", "legacy", "none")
_ALLOWED_LANG = ("cs",)

#: The closed parameter sets, as the spec's enums (atrium-project#32 round 2). The handlers
#: still check them with their own messages (`_validate_params`); the enums tell a generated
#: client the values before it sends one.
KwMethod = Literal["keybert", "yake", "legacy", "none"]
Lang = Literal["cs"]
EnrichFormat = Literal["json", "zip"]
RescaleFormat = Literal["json", "xml"]
ProjectFormat = Literal["json", "xml"]

#: Retry-After of a `busy` refusal: a pipeline run takes tens of seconds to minutes.
_BUSY_RETRY_AFTER_S = 30


# ── the typed contract (atrium-project#32 round 2) ──────────────────────────────────────────
# These models document the responses the handlers build; they do not filter them. A field
# the handlers always send has no default (required); one they send only sometimes defaults
# to None. Descriptions are published in service/openapi.json, so they are written for the
# client.


class StageSummary(BaseModel):
    """One pipeline stage of the run, from its paradata."""

    model_config = ConfigDict(extra="allow")

    script: Optional[str] = Field(description="The stage script.")
    successfully_processed: Optional[int] = Field(description="Inputs the stage processed.")
    skipped_files: Optional[int] = Field(description="Inputs the stage skipped.")
    output_counts_by_type: Dict[str, Any] = Field(description="Outputs written, per type.")


class Keyword(BaseModel):
    """One keyword of the document, by the keyword method used."""

    model_config = ConfigDict(extra="allow")

    keyword: str
    score: float = Field(description="The method's score (higher is more relevant).")


class NamedEntity(BaseModel):
    """One named entity of a page, with how often it occurs."""

    model_config = ConfigDict(extra="allow")

    text: str
    type: Optional[str] = Field(description="The NameTag entity type.")
    count: Optional[str] = Field(
        description="How often it occurs on the page (as the summary CSV has it)."
    )


class NamedEntitySummary(BaseModel):
    """The most frequent named entities of one page."""

    model_config = ConfigDict(extra="allow")

    file: Optional[str]
    page: Optional[str]
    entities: List[NamedEntity]


class EnrichResponse(BaseModel):
    """The enriched document: TEITOK XML, keywords, entities, paradata, and the record when asked."""

    model_config = ConfigDict(extra="allow")

    doc_id: str = Field(
        description="The document's id (from the upload's name, or the body's `doc_id`)."
    )
    pages: int = Field(description="The number of pages (the highest page number).")
    stages: List[StageSummary] = Field(description="What each pipeline stage did.")
    teitok_xml: Optional[str] = Field(
        description="The NLP-enriched TEITOK XML; null when none was produced."
    )
    keywords: List[Keyword] = Field(
        description="The document's keywords; empty with `kw_method=none`."
    )
    ne_summary: List[NamedEntitySummary] = Field(description="Named entities per page.")
    paradata: Optional[CreateAction] = Field(
        description=(
            "The call's provenance: its Process Run Crate `CreateAction` (atrium-project#71), built from the "
            "pipeline run's merged paradata record, whose `@id` is the `run_uuid` stamped into `document_json`; "
            "null only when the run left no paradata."
        )
    )
    limits_applied: List[LimitNote] = Field(
        description="Every limit that shaped the result without refusing it."
    )
    method_requested: str = Field(
        description="The keyword method asked for (the server default when none was)."
    )
    method_used: Optional[str] = Field(
        description="The keyword method that ran: `keybert`, `yake`, `legacy`, `none`."
    )
    llm: Optional[Any] = Field(description="Reserved; always null.")
    layout_source: str = Field(
        description="Where the pages and boxes came from: `alto`, `teitok` or `rows`."
    )
    teitok_schema_valid: Optional[bool] = Field(
        description="The TEITOK XSD verdict; null when it could not be checked."
    )
    teitok_schema_errors: List[str] = Field(description="The XSD diagnostics.")
    document_json: Optional[AtriumDocument] = Field(
        None,
        description=(
            "Only when a record was sent: the record with nlp-enrich's `entities` merged in (null when the "
            "pipeline produced none)."
        ),
    )


class Size(BaseModel):
    """A page or image size, in its own units."""

    model_config = ConfigDict(extra="allow")

    width: float
    height: float


class RescaleFactors(BaseModel):
    """The scale factors applied to the first page."""

    model_config = ConfigDict(extra="allow")

    sx: float
    sy: float


class RescaledPage(BaseModel):
    """One page's `<surface>` before and after."""

    model_config = ConfigDict(extra="allow")

    surface: Optional[str]
    source: Size
    target: Size


class RescaleResponse(BaseModel):
    """The rescaled TEITOK document and what was changed."""

    model_config = ConfigDict(extra="allow")

    teitok_xml: str
    source: Size
    source_kind: str = Field(
        description="Where the source size came from: `surface` or `bbox-extent`."
    )
    target: Size
    scale: RescaleFactors
    pages: List[RescaledPage]
    boxes_rescaled: int
    clamped: int = Field(description="Coordinates moved onto the page.")
    name_tags_fixed: int = Field(description="Malformed `<name>…</n>` closings repaired.")
    schema_valid: Optional[bool] = Field(
        description="The TEITOK XSD verdict; null when it could not be checked."
    )
    schema_errors: List[str]


class ProjectRecordResponse(BaseModel):
    """The TEITOK document with the record projected onto its header (atrium-project#70)."""

    model_config = ConfigDict(extra="allow")

    doc_id: Optional[str] = Field(description="The record's `doc_id`.")
    teitok_xml: str
    report: Dict[str, Any] = Field(
        description=(
            "What was projected: `page_categories`, `teater_categories`, `controlled_keywords` "
            "(per language), `statistical_keywords` (always 0 here), `unresolved_pages`, `notes`, "
            "and `changed`."
        )
    )
    schema_valid: Optional[bool] = Field(
        description="The TEITOK XSD verdict; null when it could not be checked."
    )
    schema_errors: List[str]


class JobAccepted(BaseModel):
    """A job was accepted; poll `GET /jobs/{job_id}`."""

    model_config = ConfigDict(extra="allow")

    job_id: str
    status: str = Field(description="`queued`.")


class JobStatus(BaseModel):
    """A job's state."""

    model_config = ConfigDict(extra="allow")

    job_id: str
    status: str = Field(description="`queued`, `running`, `done` or `failed`.")
    error: Optional[str] = Field(description="Why the job failed.")
    reason: Optional[str] = Field(
        description="A registered reason code for the failure (`limit_exceeded`), or null."
    )


class JobDeleted(BaseModel):
    """The job was forgotten."""

    model_config = ConfigDict(extra="allow")

    status: str = Field(description="`deleted`.")


class NlpModels(BaseModel):
    """The LINDAT models the pipeline calls."""

    model_config = ConfigDict(extra="allow")

    udpipe: Optional[str]
    nametag: Optional[str]


class KeywordMethods(BaseModel):
    """The keyword methods: the server default (used when a request names none), and each one."""

    model_config = ConfigDict(extra="allow")

    default: str = Field(description="The server's `DEFAULT_KW_METHOD`.")
    available: Dict[str, str]


class NlpInfo(InfoBase):
    """`/info` of atrium-nlp-enrich."""

    stage_plan: List[str]
    core_stages_mandatory: bool
    models: NlpModels
    keyword_methods: KeywordMethods


class EnrichTextRequest(BaseModel):
    """The body of `/enrich_text`: the lines, and the options `/enrich` takes as form fields."""

    model_config = ConfigDict(extra="allow")

    lines: List[Union[str, Dict[str, Any]]] = Field(
        min_length=1,
        description=(
            "The text lines: strings (one per line, all on page 1), or objects with `text` and optional "
            "`page_num`/`line_num`. An object without a non-empty `text` is skipped."
        ),
    )
    doc_id: str = Field("document", description="The document's id.")
    kw_method: Optional[KwMethod] = Field(
        None, description="The keyword method; the server default when absent."
    )
    num_keywords: int = Field(20, ge=1, le=100, description="How many keywords to return.")
    lang: Lang = "cs"
    format: EnrichFormat = Field(
        "json", description="`json` (the envelope) or `zip` (the workspace output)."
    )
    document_json: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Optional baseline ATRIUM Document JSON, or an AMČR seed (`doc_id`, `source`): see `/enrich`. One "
            "that is not a JSON object is refused (422 `invalid_record`)."
        ),
    )
    teitok_enrichment: bool = Field(
        False,
        description=(
            "Opt-in, default false: see `/enrich`. Projects the record's page categories and "
            "this run's keywords (per document and per page) into the TEITOK header."
        ),
    )


def _enrich_200() -> Dict[str, Any]:
    """The 200 of /enrich and /enrich_text: the envelope, or the ZIP.

    A function, not a shared dict: FastAPI copies `responses` shallowly and merges into
    `content`, so one dict used by two routes would be mutated by both.
    """
    return {
        "model": EnrichResponse,
        "description": "The enriched document (`format=json`), or the workspace output as a ZIP (`format=zip`).",
        "content": {
            "application/zip": {"schema": {"type": "string", "contentMediaType": "application/zip"}}
        },
    }


class _Slots:
    """The MAX_CONCURRENT_JOBS processing slots, shared by the synchronous endpoints and
    /jobs (read per call, like every limit).

    A slot is held until the pipeline run has really ended: the run stops itself at
    API_JOB_TIMEOUT (service/bounded_run.py), so no ``asyncio.wait_for`` frees it while the
    pipeline still runs in its executor thread -- which is how MAX_CONCURRENT_JOBS used to
    be exceeded after every timeout (atrium-project#53).
    """

    def __init__(self) -> None:
        self.running = 0
        self._freed: asyncio.Condition | None = None

    def _condition(self) -> asyncio.Condition:
        if self._freed is None:  # built in the running loop, not at import
            self._freed = asyncio.Condition()
        return self._freed

    def locked(self) -> bool:
        """Every slot is taken."""
        return self.running >= MAX_CONCURRENT_JOBS.get()

    def free(self) -> int:
        return max(0, MAX_CONCURRENT_JOBS.get() - self.running)

    def take(self) -> bool:
        """Take a slot now, or say there is none (the synchronous endpoints)."""
        if self.locked():
            return False
        self.running += 1
        return True

    async def acquire(self) -> None:
        """Wait for a slot (a /jobs job)."""
        cond = self._condition()
        async with cond:
            while self.locked():
                await cond.wait()
            self.running += 1

    async def release(self) -> None:
        cond = self._condition()
        async with cond:
            self.running -= 1
            cond.notify_all()


_manager = PipelineManager()
_semaphore = _Slots()
_SERVICE_DIR = Path(__file__).resolve().parent
_state = ServiceState()

# (12-factor XI) No basicConfig() here -- this module is imported by api's own
# __main__ and by tests; the entry point decides handlers and level. (issue #61)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _manager.warmup, DEFAULT_KW_METHOD)
    _state.warm = True
    # issue #35: /jobs state (service/jobs.py's _jobs dict) is process-local -- this
    # service expects a single replica. Said once at boot, in the log a partner
    # reads when something is already wrong, not only in the 404 body.
    logger.info(
        "nlp-enrich: /jobs state is process-local; expects a single replica "
        "(atrium-project#53 factors IV/VI)"
    )
    # issue #55: composes with the existing warmup above rather than replacing it.
    # Installs the SIGTERM/SIGINT handling that flips /ready to 503 and, on shutdown,
    # waits for in-flight requests AND any job tracked via _state.track() (see
    # submit_job below) — the mechanism that stops a rolling restart from killing a
    # background /jobs run mid-pipeline, which counting in-flight requests alone
    # cannot do (the submitting request already returned).
    async with serve_lifecycle(_state):
        yield


# DEFINITION OF THE APP
app = FastAPI(
    title="ATRIUM nlp-enrich API",
    version=read_tool_version(_SERVICE_DIR.parent),
    description="Text lines (a table, a .txt, or a converted TEITOK file) → NLP-enriched "
    "TEITOK XML + keywords.",
    lifespan=lifespan,
    # The typed contract (atrium-project#32 round 2): every route documents the §4.4 error
    # body for 422 and 500 (and FastAPI's own 422 body, which is not what is sent, goes);
    # operationIds are the handler names; the spec never depends on a root_path.
    responses=error_responses(422, 500),
    generate_unique_id_function=operation_id,
    root_path_in_servers=False,
)
attach_inflight_middleware(app, _state)
# §4.4 error body {status, reason, detail} for every error (atrium-project#32 item 2, #53).
attach_error_handlers(app)
# The published spec: reason registry, record schema, service id (atrium-project#32 item 3).
attach_openapi_contract(app, SERVICE)

# Safely mount static directories if they exist
if (_SERVICE_DIR / "frontend").exists():
    app.mount(
        "/frontend",
        StaticFiles(directory=str(_SERVICE_DIR / "frontend"), html=True),
        name="frontend",
    )
if (_SERVICE_DIR / "frontend-lindat").exists():
    app.mount(
        "/frontend-lindat",
        StaticFiles(directory=str(_SERVICE_DIR / "frontend-lindat"), html=True),
        name="frontend-lindat",
    )

# issue #55, D1b: converged onto the shared helper — same ALLOWED_ORIGINS env var,
# same default "*", so this is not a behavior change, only a drift-prevention one.
add_cors(app)

# ── helpers ────────────────────────────────────────────────────────────────────


def _validate_params(kw_method: str, lang: str, num_keywords: int) -> None:
    if kw_method not in _ALLOWED_KW:
        raise HTTPException(422, f"kw_method must be one of {_ALLOWED_KW}") from None
    if lang not in _ALLOWED_LANG:
        raise HTTPException(422, f"lang must be one of {_ALLOWED_LANG} in v1") from None
    if not (1 <= num_keywords <= 100):
        raise HTTPException(422, "num_keywords must be between 1 and 100") from None


def _schema_verdict(xml_text: str) -> tuple[bool | None, List[str]]:
    """TEITOK XSD conformance verdict for a document this service produced
    (issue #28), as ``(valid, diagnostics)``.

    ``valid`` is ``None`` when no verdict could be reached — the validator or
    lxml is unavailable — so callers can tell "not conformant" apart from
    "not checked". Never raises: a reporting extra must not be able to fail a
    transform that already succeeded.
    """
    try:
        from api_util.validate_teitok_xml import validate_xml_text

        errors = validate_xml_text(xml_text)
    except Exception as exc:  # noqa: BLE001 - advisory field, never fatal
        return None, [f"schema check unavailable: {exc}"]
    return not errors, errors


async def _read_document_json(part: UploadFile | None) -> bytes | None:
    """Read an optional ``document_json`` upload part, or None (#10 J3).

    A zero-byte part counts as "not supplied": clients and form builders routinely send an
    empty file field for an optional upload, and treating that as a baseline would seed the
    bridge with an unparseable file and then report "no doc_id" — a confusing way to say
    "you sent nothing". Enforces the same size ceiling as the primary upload, since this
    part is caller-controlled too.
    """
    if part is None:
        return None
    data = await read_upload_bounded(part, MAX_UPLOAD.get(), "document_json")
    # A record that cannot be opened is refused here, before the pipeline, with 422
    # `invalid_record` (atrium-project#32 round 2). It used to reach the stats stage, which
    # warned and ran on, so the response came back with `document_json: null` and no word of
    # why. The bytes go on as sent; an empty part still counts as none.
    if parse_record_part(data, "document_json") is None:
        return None
    return data


async def _read_layout(filename: str, data: bytes, alto: UploadFile | None) -> Layout | None:
    """The layout source of an upload (issue #38, F): the file itself when it is a TEITOK
    document (flexiconv's conversion: text *and* layout), else an optional ``alto`` part for
    a table. No GPL code runs here: conversion to TEITOK stays in the CLI."""
    alto_data = (
        await read_upload_bounded(alto, MAX_UPLOAD.get(), "alto") if alto is not None else b""
    )
    if is_teitok_upload(filename, data):
        if alto_data:
            raise HTTPException(
                422, "A TEITOK file carries its own layout; do not send an alto part with it."
            ) from None
        return Layout(kind="teitok", data=data)
    if not alto_data:
        return None
    if os.path.splitext(filename or "")[1].lower() not in (".csv", ".xlsx"):
        raise HTTPException(
            422, "An alto part goes with a .csv or .xlsx table of that page's lines."
        ) from None
    try:
        return read_alto_upload(alto.filename or "upload.alto.xml", alto_data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _run_pipeline_sync(
    rows,
    doc_id,
    kw_method,
    num_keywords,
    lang,
    document_json=None,
    layout=None,
    teitok_enrichment=False,
):
    """Blocking pipeline call with graceful backend degradation configured, stopped at
    API_JOB_TIMEOUT (LimitExceeded, 504)."""
    return _manager.enrich(
        rows,
        doc_id,
        kw_method=kw_method,
        num_keywords=num_keywords,
        lang=lang,
        document_json=document_json,
        layout=layout,
        timeout=API_JOB_TIMEOUT.get(),
        teitok_enrichment=teitok_enrichment,
    ), kw_method


def _build_envelope(result, requested_method, sent=()) -> Dict[str, Any]:
    teitok_xml = PipelineManager.collect_teitok(result)
    merged = PipelineManager.collect_merged_paradata(result)
    record = (
        PipelineManager.collect_document_json(result)
        if result.document_json_out is not None
        else None
    )
    envelope = {
        "doc_id": result.doc_id,
        "pages": result.pages,
        "stages": result.stages,
        "teitok_xml": teitok_xml,
        "keywords": PipelineManager.collect_keywords(result),
        "ne_summary": PipelineManager.collect_ne_summary(result),
        "paradata": _run_action(merged, result, record, teitok_xml, sent) if merged else None,
        # Every limit that shaped this result without refusing it (atrium-project#53): the
        # stages record them in their paradata, the run's merged record carries them.
        "limits_applied": list((merged or {}).get("limits_applied") or []),
        "method_requested": requested_method,
        "method_used": result.kw_method_used,
        "llm": None,
        # issue #38, F: where the pages and boxes came from, and the contract verdict the
        # stage-4 gate reached (a run that failed it never gets here: exit 5 -> 500)
        "layout_source": result.layout_source,
    }
    envelope["teitok_schema_valid"], envelope["teitok_schema_errors"] = (
        _schema_verdict(teitok_xml) if teitok_xml else (None, [])
    )
    # (atrium-project#10, J3) Present only when the client opted into the accretion flow,
    # so the envelope of every existing caller is byte-for-byte what it was. `null` here
    # is meaningful rather than absent-by-default: it says the record was requested and
    # the pipeline produced none (see PipelineManager.collect_document_json).
    if result.document_json_out is not None:
        envelope["document_json"] = record
    return envelope


def _run_action(merged, result, record, teitok_xml, sent) -> Dict[str, Any]:
    """The call's CreateAction (atrium-project#71), from the pipeline run's merged paradata.

    Its `@id` is the `run_uuid` the stats stage stamped on the blocks it wrote (the record's
    last `nlp-enrich` contributor), so the record and the action name one run; without a
    record it is the merged run's own. `object` is what the call was sent and the record;
    `result` is the record's blocks this run stamped and the TEITOK it answers with.
    """
    ours = [
        entry
        for entry in ((record or {}).get("provenance") or {}).get("contributors") or []
        if entry.get("program") == "nlp-enrich" and entry.get("run_uuid")
    ]
    run_uuid = ours[-1]["run_uuid"] if ours else merged.get("run_uuid")
    inputs = list(sent)
    if result.document_json_out is not None:
        inputs.append(
            atrium_rocrate.record_entity(str((record or {}).get("doc_id") or result.doc_id))
        )
    outputs = atrium_rocrate.block_entities(atrium_rocrate.blocks_written(record, run_uuid or ""))
    if teitok_xml:
        outputs.append(
            atrium_rocrate.file_entity(
                f"{result.doc_id}.teitok.xml",
                teitok_xml.encode("utf-8"),
                media_type="application/xml",
            )
        )
    return atrium_rocrate.create_action(merged, inputs=inputs, outputs=outputs, action_id=run_uuid)


def _sent(name, data, media_type, alto=None, layout=None) -> List[Dict[str, Any]]:
    """What a call was sent, for its CreateAction's `object` (atrium-project#71): the upload and
    a separate `alto` part. A TEITOK upload is its own layout, so it is listed once."""
    sent = [atrium_rocrate.file_entity(name, data, media_type=media_type)]
    if alto is not None and layout is not None and layout.kind == "alto":
        sent.append(
            atrium_rocrate.file_entity(
                alto.filename or "upload.alto.xml", layout.data, media_type="application/alto+xml"
            )
        )
    return sent


async def _run_enrichment(
    rows,
    doc_id,
    kw_method,
    num_keywords,
    lang,
    fmt,
    document_json=None,
    layout=None,
    teitok_enrichment=False,
    sent=(),
) -> tuple[Any, str, Any]:
    loop = asyncio.get_event_loop()
    try:
        result, requested = await loop.run_in_executor(
            None,
            _run_pipeline_sync,
            rows,
            doc_id,
            kw_method,
            num_keywords,
            lang,
            document_json,
            layout,
            teitok_enrichment,
        )
    except KeywordPreflightError as exc:
        raise HTTPException(503, str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(exc.http_status, str(exc)) from exc

    try:
        if fmt == "zip":
            zip_path = PipelineManager.zip_workspace_output(result)
            return zip_path, "zip", result
        envelope = _build_envelope(result, requested, sent)
        return envelope, "json", result
    except Exception:
        PipelineManager.cleanup(result)
        raise


def _check_rows(rows) -> None:
    """The input checks every endpoint makes before a pipeline runs: some text, and no
    more than MAX_WORDS words (413 limit_exceeded)."""
    if not rows:
        raise HTTPException(422, "No usable text rows found in input.") from None
    words = count_words(rows)
    limit = MAX_WORDS.get()
    MAX_WORDS.check(
        words,
        value=limit,
        detail=f"Input too large: {words} words > {limit} (MAX_WORDS).",
    )


async def _enrich_common(
    rows,
    doc_id,
    kw_method,
    num_keywords,
    lang,
    fmt,
    document_json=None,
    layout=None,
    teitok_enrichment=False,
    sent=(),
):
    _validate_params(kw_method, lang, num_keywords)
    _check_rows(rows)

    if not _semaphore.take():
        raise busy(
            f"Server busy: all {MAX_CONCURRENT_JOBS.get()} processing slots are taken "
            "(MAX_CONCURRENT_JOBS). Retry later, or submit to /jobs.",
            retry_after_s=_BUSY_RETRY_AFTER_S,
        )
    try:
        data, out_fmt, result = await _run_enrichment(
            rows,
            doc_id,
            kw_method,
            num_keywords,
            lang,
            fmt,
            document_json,
            layout,
            teitok_enrichment,
            sent,
        )
    finally:
        await _semaphore.release()

    if out_fmt == "zip":
        return FileResponse(
            str(data),
            media_type="application/zip",
            filename=f"{doc_id}_enriched.zip",
            background=BackgroundTask(PipelineManager.cleanup, result),
        )
    PipelineManager.cleanup(result)
    return JSONResponse(data)


async def _run_job_background(
    job: Job,
    rows,
    doc_id,
    kw_method,
    num_keywords,
    lang,
    document_json=None,
    layout=None,
    teitok_enrichment=False,
    sent=(),
):
    try:
        # "queued" until the job holds a slot (atrium-project#53): it used to report
        # "running" while it waited for one.
        await _semaphore.acquire()
        try:
            job.status = "running"
            data, out_fmt, result = await _run_enrichment(
                rows,
                doc_id,
                kw_method,
                num_keywords,
                lang,
                fmt="json",
                document_json=document_json,
                layout=layout,
                teitok_enrichment=teitok_enrichment,
                sent=sent,
            )
            PipelineManager.cleanup(result)
            job.result = data
            job.status = "done"
        finally:
            await _semaphore.release()
    except asyncio.CancelledError:
        # issue #55: this task is now tracked via _state.track() (see submit_job), so
        # serve_lifecycle awaits it on shutdown rather than cancelling it — a clean run
        # to completion or a timeout inside its own budget is the expected path. This
        # branch exists for the one case that still cancels it directly (the drain
        # budget in serve_lifecycle elapsing with the job still running): record why
        # the job never finished, rather than leaving it reporting "running" forever to
        # a client that polls /jobs/{id} after the process has already exited. Must
        # still propagate — swallowing CancelledError breaks cooperative cancellation.
        job.error = "Cancelled: server shutdown interrupted this job before it finished."
        job.status = "failed"
        raise  # the outer `finally` below still records finished_at
    except LimitExceeded as e:  # API_JOB_TIMEOUT: the run was stopped, its workspace removed
        job.error = e.detail
        job.reason = "limit_exceeded"
        job.status = "failed"
    except HTTPException as e:
        job.error = str(e.detail)
        job.status = "failed"
    except Exception as e:
        job.error = str(e)
        job.status = "failed"
    finally:
        job.finished_at = time.time()


# ── endpoints ──────────────────────────────────────────────────────────────────


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/frontend")


@app.get(
    "/info",
    response_model=None,
    responses={200: {"model": NlpInfo, "description": "Identity, limits, capabilities."}},
)
async def info() -> Dict[str, Any]:
    facts = _manager.config_facts()
    return build_info(
        app,
        SERVICE,
        limits=LIMITS,
        stage_plan=["manifest", "udp", "nt", "stats"],
        core_stages_mandatory=True,
        models={
            "udpipe": facts.get("udpipe_model"),
            "nametag": facts.get("nametag_model"),
        },
        keyword_methods={
            "default": DEFAULT_KW_METHOD,
            "available": {
                "keybert": "best quality; GPU-capable embedding model",
                "yake": "fast CPU statistical extraction",
                "legacy": "stdlib KER lemma-frequency baseline",
                "none": "skip keyword extraction",
            },
        },
    )


def _deep_health() -> str | None:
    """Deep readiness (§4.1): the pipeline dry-run succeeds and, when configured,
    the UDPipe/NameTag backends answer.

    issue #55, D1b: this now runs ONLY under ``?deep=true``, via the shared
    ``attach_health``. Before this, the dry-run subprocess ran on EVERY shallow
    ``/health`` probe (the old handler was ``async def`` and called it unconditionally
    before checking ``deep``), which meant a 30s-interval Docker HEALTHCHECK aimed at
    this route would have spawned a subprocess every interval and blocked the whole
    event loop for its duration — the worst possible target for a liveness probe. This
    function is a plain sync ``def``, so FastAPI/Starlette dispatch it to the anyio
    threadpool instead of the event loop, same as every other repo's ``_deep_health``.
    """
    rc, tail = _manager.dry_run(kw_method="none")
    if rc != 0:
        return f"dry-run exit {rc}: {tail[-1500:]}"
    facts = _manager.config_facts()
    import urllib.request

    for url in (facts.get("udpipe_url"), facts.get("nametag_url")):
        if url:
            try:
                urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=5)
            except Exception as e:
                return f"backend unreachable ({url}): {e}"
    return None


attach_health(app, deep_check=_deep_health, state=_state)


#: Shared wording for the optional accretion part, so /enrich, /enrich_text and /jobs
#: describe one contract in one place (atrium-project#10, J3).
_DOCUMENT_JSON_HELP = (
    "Optional baseline ATRIUM Document JSON (accretion model, docs/document_schema.md / "
    "issue #13). When given, the response's `document_json` carries the record back with "
    "only nlp-enrich's contribution merged in — its `entities[]` rows (`teitok_ref` = the "
    "entity's TEITOK `<name id>`; `pages[].teitok_surface` is only set for pages with a "
    "layout: an `alto` part, or a TEITOK file with page images) — while every other tool's "
    "block (page_categories, lines, "
    "translations, enrichment, ...) passes through untouched. An AMČR seed (`doc_id`, "
    "`source`) is a valid baseline. A baseline that does not validate against "
    "atrium_document.schema.json is still accepted (rule 6); the pipeline warns and accretes "
    "onto it anyway. One that is not a JSON object is refused (422 `invalid_record`)."
)

#: The optional layout part of /enrich and /jobs (issue #38, F).
_ALTO_HELP = (
    "Optional ALTO XML of the pages a .csv/.xlsx `file` lists the lines of (e.g. "
    "alto-postprocess's DOC_LINE_CATEG table and its source ALTO): the TEITOK then carries "
    "bboxes, text blocks and a facsimile. Not with a TEITOK `file`, which brings its own "
    "layout. PAGE XML and hOCR: convert with api_flexiconv.sh and upload the TEITOK."
)

#: What `file` may be, for /enrich and /jobs.
_FILE_HELP = (
    "The text: a .csv/.xlsx table (`text`, optional `page_num`/`line_num`), a .txt (one "
    "line per row; a form feed starts a new page), or a TEITOK .xml -- e.g. flexiconv's "
    "conversion of a PDF, DOCX or PAGE XML (api_flexiconv.sh) -- whose text is annotated "
    "and whose pages, lines and boxes become the output's layout."
)


#: The keyword-method parameter's description, for /enrich and /jobs.
_KW_METHOD_HELP = (
    "The keyword method. Absent: the server's default (`/info` `keyword_methods.default`, the "
    "`DEFAULT_KW_METHOD` setting)."
)

#: The statuses the enrichment endpoints refuse or fail with (§4.4), beyond the app-wide 422/500.
_ENRICH_ERRORS = (413, 429, 502, 503, 504)

_TEITOK_ENRICHMENT_HELP = (
    "Opt-in, default false (atrium-project#70). When true, the returned TEITOK also carries the "
    "record's page categories (`pb/@ana` + a `classDecl` taxonomy; from `document_json`) and "
    "this run's keywords, for the document and for each page, in `profileDesc/textClass`. "
    "AMČR's stored TEITOK leaves it off."
)


def _normalize(filename: str, data: bytes):
    """The upload's rows, or the §4.4 refusal: 415 for a type it does not read, else 422."""
    try:
        return normalize_upload(filename, data)
    except UnsupportedUploadType as exc:
        raise AtriumHTTPError(
            415, str(exc), reason="unsupported_media_type", accepted=list(exc.accepted)
        ) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post(
    "/enrich",
    response_model=None,
    responses={200: _enrich_200(), **error_responses(415, *_ENRICH_ERRORS)},
)
async def enrich(
    file: UploadFile = File(..., description=_FILE_HELP),  # noqa: B008
    kw_method: Optional[KwMethod] = Form(None, description=_KW_METHOD_HELP),  # noqa: B008
    num_keywords: int = Form(20, ge=1, le=100),
    lang: Lang = Form("cs"),  # noqa: B008
    format: EnrichFormat = Form("json"),  # noqa: B008
    document_json: UploadFile = File(  # noqa: B008
        None,
        description=_DOCUMENT_JSON_HELP,
        json_schema_extra={"contentMediaType": "application/json"},
    ),
    alto: UploadFile = File(None, description=_ALTO_HELP),  # noqa: B008
    teitok_enrichment: bool = Form(False, description=_TEITOK_ENRICHMENT_HELP),
):
    data = await read_upload_bounded(file, MAX_UPLOAD.get(), "Upload")
    filename = file.filename or "upload.csv"
    layout = await _read_layout(filename, data, alto)
    rows = _normalize(filename, data)
    doc_id = file.filename or "document"
    baseline = await _read_document_json(document_json)
    return await _enrich_common(
        rows,
        doc_id,
        kw_method or DEFAULT_KW_METHOD,
        num_keywords,
        lang,
        format,
        baseline,
        layout,
        teitok_enrichment,
        _sent(filename, data, file.content_type, alto, layout),
    )


@app.post(
    "/enrich_text",
    response_model=None,
    responses={200: _enrich_200(), **error_responses(*_ENRICH_ERRORS)},
)
async def enrich_text(payload: EnrichTextRequest, request: Request):
    """The `/enrich` pipeline on inline lines (§4.3, the JSON sibling of the upload endpoint).

    Since atrium-project#32 round 2 the body is a typed model: a malformed value (a
    non-numeric `num_keywords`, an unknown `format`) is a 422 validation error where it
    used to be a 500 or, for `format`, silently JSON.
    """
    # The body is bounded like an upload (atrium-project#53): it had no size limit at all.
    await check_body_size(request, MAX_UPLOAD.get(), "Request body")
    rows: List[Dict[str, Any]] = []
    for i, item in enumerate(payload.lines, start=1):
        if isinstance(item, str):
            rows.append({"text": item, "page_num": 1, "line_num": i})
        elif isinstance(item, dict) and item.get("text"):
            rows.append(item)
    # Inline JSON in, inline JSON out — an embedded object rather than an upload part,
    # matching llm-enrich's /extract_keywords_text (#10 J3).
    baseline = parse_record_part(payload.document_json, "document_json")
    baseline_bytes = json.dumps(baseline).encode("utf-8") if baseline is not None else None
    lines = json.dumps(payload.lines, ensure_ascii=False).encode("utf-8")
    return await _enrich_common(
        rows,
        payload.doc_id,
        payload.kw_method or DEFAULT_KW_METHOD,
        payload.num_keywords,
        payload.lang,
        payload.format,
        baseline_bytes,
        teitok_enrichment=payload.teitok_enrichment,
        sent=_sent("lines.json", lines, "application/json"),
    )


@app.post(
    "/rescale",
    response_model=None,
    responses={
        200: {
            "model": RescaleResponse,
            "description": "The rescaled document (`format=json`), or the `.teitok.xml` file itself (`format=xml`).",
            "content": {"application/xml": {"schema": {"type": "string"}}},
        },
        **error_responses(413),
    },
)
async def rescale(
    file: UploadFile = File(..., description="A TEITOK facsimile document (.teitok.xml)."),  # noqa: B008
    width: int | None = Form(None),
    height: int | None = Form(None),
    scale: float | None = Form(None),
    format: RescaleFormat = Form("json"),  # noqa: B008
    fix_names: bool = Form(True),
):
    """Rescale a TEITOK document's coordinates to page images of another size.

    Pure XML coordinate transform (no pipeline). Either ``width`` × ``height``
    (every page image has that size) or ``scale`` (every page image is ``scale``
    times its ``<surface>``; the form for documents whose pages differ in size).
    Page by page, every ``bbox`` is scaled by the ``<surface>`` of the page it is
    on and clamped to it; each ``<surface>`` gets its own new ``lrx``/``lry``; a
    ``<change type="rescaled">`` records the transform. By default it also
    repairs the malformed ``<name>…</n>`` named-entity closings to ``</name>``
    (set ``fix_names=false`` to disable). ``format=json`` (default) returns the
    rewritten XML plus scale metadata (``pages``: source and target size of
    every page; ``clamped``: coordinates moved onto the page); ``format=xml``
    streams the rescaled ``.teitok.xml`` file.
    """
    if scale is not None:
        if width is not None or height is not None:
            raise HTTPException(422, "Give either width and height, or scale.") from None
        if not (0 < scale <= 100):
            raise HTTPException(422, "scale must be a number in (0, 100].") from None
    elif width is None or height is None:
        raise HTTPException(422, "Give width and height, or scale.") from None
    elif width < 1 or height < 1:
        raise HTTPException(422, "width and height must be positive integers.") from None
    max_dim = MAX_RESCALE_DIM.get()
    if width is not None and height is not None:
        MAX_RESCALE_DIM.check(
            max(width, height),
            value=max_dim,
            detail=f"width and height must be integers between 1 and {max_dim} (MAX_RESCALE_DIM).",
        )

    data = await read_upload_bounded(file, MAX_UPLOAD.get(), "Upload")
    try:
        xml_text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "Uploaded file is not valid UTF-8 text.") from exc
    if "<surface" not in xml_text and "bbox=" not in xml_text:
        raise HTTPException(
            422, "Input does not look like TEITOK facsimile XML (no <surface> or bbox)."
        ) from None

    try:
        result = rescale_teitok(
            xml_text, width, height, fix_name_tags=fix_names, scale=scale, max_dim=max_dim
        )
    except RescaleTooLarge as exc:  # `scale` reached past MAX_RESCALE_DIM on some page
        raise MAX_RESCALE_DIM.exceeded(exc.observed, value=max_dim, detail=str(exc)) from exc
    except RescaleError as exc:
        raise HTTPException(422, str(exc)) from exc

    # TEITOK output contract verdict (issue #28). Advisory, not a 4xx: this
    # endpoint faithfully transforms whatever it is handed, including legacy
    # documents that predate the schema, so rejecting them would break a
    # working tool. Callers that care can gate on `schema_valid`.
    result["schema_valid"], result["schema_errors"] = _schema_verdict(result["teitok_xml"])

    if format == "xml":
        name = Path(file.filename or "document").name
        for suf in (".teitok.xml", ".xml"):
            if name.lower().endswith(suf):
                name = name[: -len(suf)]
                break
        doc_id = sanitize_doc_id(name) or "document"
        return Response(
            content=result["teitok_xml"],
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{doc_id}.rescaled.teitok.xml"'},
        )
    return JSONResponse(result)


@app.post(
    "/project_record",
    response_model=None,
    responses={
        200: {
            "model": ProjectRecordResponse,
            "description": "The projected document (`format=json`), or the `.teitok.xml` file itself (`format=xml`).",
            "content": {"application/xml": {"schema": {"type": "string"}}},
        },
        **error_responses(413),
    },
)
async def project_record(
    file: UploadFile = File(  # noqa: B008
        ..., description="The document's TEITOK file (.teitok.xml), as nlp-enrich wrote it."
    ),
    document_json: UploadFile = File(  # noqa: B008
        ...,
        description="The document's finished record (after page-classification and llm-enrich).",
        json_schema_extra={"contentMediaType": "application/json"},
    ),
    format: ProjectFormat = Form("json"),  # noqa: B008
):
    """Project a finished record onto its TEITOK file (atrium-project#70, flexiconv#1).

    Pure XML transform (no pipeline), for a record that is complete only after this service ran:
    the page categories become ``pb/@ana`` plus a ``classDecl`` taxonomy, and llm-enrich's
    TEATER/AMČR categories and controlled keywords become ``profileDesc/textClass/keywords``,
    each pointing at its pages. Only the header and ``pb/@ana`` change. Re-projecting replaces
    an earlier projection. Refused (422) when the TEITOK is not the record's document (its
    ``<title>`` is neither ``doc_id`` nor the id of ``source.filename``), not this writer's
    ``teitok-2`` output, or not valid. Off AMČR's production chain, whose stored TEITOK keeps
    linguistics and layout only.
    """
    data = await read_upload_bounded(file, MAX_UPLOAD.get(), "Upload")
    try:
        xml_text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "Uploaded file is not valid UTF-8 text.") from exc
    record_bytes = await read_upload_bounded(document_json, MAX_UPLOAD.get(), "document_json")
    record = parse_record_part(record_bytes, "document_json")
    if record is None:
        raise HTTPException(422, "document_json is empty: send the record to project.") from None

    from api_util.teitok_project import ProjectionError
    from api_util.teitok_project import project_record as project_teitok

    try:
        out, report = project_teitok(xml_text, record)
    except ProjectionError as exc:
        raise HTTPException(422, str(exc)) from exc

    if format == "xml":
        doc_id = sanitize_doc_id(str(record.get("doc_id") or "document")) or "document"
        return Response(
            content=out,
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{doc_id}.teitok.xml"'},
        )
    valid, errors = _schema_verdict(out)
    return JSONResponse(
        {
            "doc_id": record.get("doc_id"),
            "teitok_xml": out,
            "report": report,
            "schema_valid": valid,
            "schema_errors": errors,
        }
    )


@app.post(
    "/jobs",
    response_model=None,
    responses={
        200: {"model": JobAccepted, "description": "Accepted; poll `GET /jobs/{job_id}`."},
        **error_responses(413, 415, 429),
    },
)
async def submit_job(
    file: UploadFile = File(..., description=_FILE_HELP),  # noqa: B008
    kw_method: Optional[KwMethod] = Form(None, description=_KW_METHOD_HELP),  # noqa: B008
    num_keywords: int = Form(20, ge=1, le=100),
    lang: Lang = Form("cs"),  # noqa: B008
    document_json: UploadFile = File(  # noqa: B008
        None,
        description=_DOCUMENT_JSON_HELP,
        json_schema_extra={"contentMediaType": "application/json"},
    ),
    alto: UploadFile = File(None, description=_ALTO_HELP),  # noqa: B008
    teitok_enrichment: bool = Form(False, description=_TEITOK_ENRICHMENT_HELP),
):
    kw_method = kw_method or DEFAULT_KW_METHOD
    _validate_params(kw_method, lang, num_keywords)
    data = await read_upload_bounded(file, MAX_UPLOAD.get(), "Upload")
    filename = file.filename or "upload.csv"
    # Read here, not in the background task, like document_json below.
    layout = await _read_layout(filename, data, alto)
    rows = _normalize(filename, data)
    # Refused now, with the synchronous endpoints' answer, rather than accepted as a job
    # that the pipeline then fails or runs over MAX_WORDS (atrium-project#53).
    _check_rows(rows)
    doc_id = file.filename or "document"
    # Read here, not in the background task: the UploadFile's spooled temp file is tied
    # to the request and is closed once this handler returns (#10 J3).
    baseline = await _read_document_json(document_json)

    _evict_finished_jobs()
    # The queue is bounded (atrium-project#53): jobs waiting for a slot may fill the slots
    # that are free now plus MAX_QUEUED_JOBS; the README promised a 429 the service never
    # gave.
    queued = sum(1 for j in _jobs.values() if j.status == "queued")
    if queued >= _semaphore.free() + MAX_QUEUED_JOBS.get():
        raise busy(
            f"Server busy: {queued} job(s) already wait for one of the "
            f"{MAX_CONCURRENT_JOBS.get()} processing slots (MAX_QUEUED_JOBS="
            f"{MAX_QUEUED_JOBS.get()}). Retry later.",
            retry_after_s=_BUSY_RETRY_AFTER_S,
        )

    job = await create_job()
    # issue #55, D1a: tracked, not a bare asyncio.create_task(). A submitted job
    # outlives this request — the request returns "queued" immediately, so a plain
    # in-flight REQUEST counter reaches zero long before the job itself finishes. A
    # bare create_task() result is also GC-eligible with nothing retaining it, task
    # or no shutdown involved. _state.track() fixes both: serve_lifecycle's drain
    # waits for this job before letting the process exit, so a rolling restart no
    # longer kills it mid-run.
    _state.track(
        _run_job_background(
            job,
            rows,
            doc_id,
            kw_method,
            num_keywords,
            lang,
            baseline,
            layout,
            teitok_enrichment,
            _sent(filename, data, file.content_type, alto, layout),
        )
    )
    return {"job_id": job.job_id, "status": "queued"}


def _evict_finished_jobs() -> None:
    """Forget the jobs that finished more than JOB_TTL_S seconds ago."""
    ttl = JOB_TTL_S.get()
    now = time.time()
    for jid in [jid for jid, j in _jobs.items() if j.finished_at and now - j.finished_at > ttl]:
        del _jobs[jid]


# nlp-enrich is the ecosystem's only stateful service: _jobs is a process-local
# dict (service/jobs.py), so a job's record does not survive a restart and is not
# visible to any other replica (atrium-project#53 factors IV/VI, atrium-project
# docs/k8s_deployment.md "Known limits"). Name that in the 404 rather than leaving
# it a bare "not found", so an operator seeing an intermittent 404 has the answer.
_JOB_NOT_FOUND_DETAIL = (
    "Job not found (job ids are local to the replica that accepted the request -- "
    "see atrium-project#53 factors IV/VI)"
)


@app.get(
    "/jobs/{job_id}",
    response_model=None,
    responses={
        200: {"model": JobStatus, "description": "The job's state."},
        **error_responses(404),
    },
)
async def get_job_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=_JOB_NOT_FOUND_DETAIL) from None
    return {"job_id": job_id, "status": job.status, "error": job.error, "reason": job.reason}


@app.get(
    "/jobs/{job_id}/result",
    response_model=None,
    responses={
        200: {
            "model": EnrichResponse,
            "description": "The finished job's envelope, as `/enrich` returns it.",
        },
        **error_responses(404, 409),
    },
)
async def get_job_result(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=_JOB_NOT_FOUND_DETAIL) from None
    if job.status != "done":
        raise HTTPException(409, f"Job not complete (status: {job.status})") from None
    return job.result


@app.delete(
    "/jobs/{job_id}",
    response_model=None,
    responses={
        200: {"model": JobDeleted, "description": "The job was forgotten."},
        **error_responses(404),
    },
)
async def cleanup_job(job_id: str):
    if job_id in _jobs:
        del _jobs[job_id]
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail=_JOB_NOT_FOUND_DETAIL) from None


if __name__ == "__main__":
    import logging
    import os
    import sys

    import uvicorn

    # (12-factor XI) Logs are an event stream: emit to stdout and let the supervisor
    # route them. The library modules only getLogger(); this is the one place allowed
    # to configure handlers. The format string is alto-postprocess's, verbatim, in all
    # five services — a partner tailing five logs wants one shape, and format drift is
    # never fixed later. (issue #61)
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )

    # (12-factor VII) The service exports itself by binding a port, and which port is
    # configuration. This was baked into an exec-form ENTRYPOINT array, where no shell
    # exists to expand a variable even if one is set — while the reference manifest we
    # hand ARÚP/ARÚB (atrium-project docs/templates/k8s/atrium-service.deployment.yaml)
    # declares `env: PORT` and service/healthcheck.py already reads it. Setting PORT
    # therefore moved the health PROBE and not the listener, so the container reported
    # unhealthy forever rather than simply ignoring the knob. (issue #58)
    reload = os.getenv("RELOAD", "false").strip().lower() in ("true", "1", "yes", "on")

    # uvicorn needs an IMPORT STRING to respawn workers on reload; everywhere else the
    # app OBJECT is correct and strictly better. Passing a string under the container
    # entrypoint (`python -m service.api`) re-imports this module under its real name
    # while it is already running as __main__: the whole body executes twice, and the
    # copy uvicorn serves is not the one __main__ built. __spec__ is None under a direct
    # `python api.py` from service/ (service/README.md's documented start), where no
    # import string resolves anyway — so reload degrades to a uvicorn warning there
    # instead of silently pretending to be on.
    _app_ref = f"{__spec__.name}:app" if reload and __spec__ is not None else app

    uvicorn.run(
        _app_ref,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=reload,
        # (12-factor IX) Disposability: this is the `--timeout-graceful-shutdown 20`
        # that moved off the ENTRYPOINT line when the port became configurable. It
        # bounds uvicorn's wait for in-flight requests; serve_lifecycle() adds its own
        # drain on top, and docs/k8s_deployment.md in the hub carries the full grace
        # budget the two have to fit inside. (issue #55)
        timeout_graceful_shutdown=int(os.getenv("GRACEFUL_SHUTDOWN_S", "20")),
    )
