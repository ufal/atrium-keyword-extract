"""
openrouter_client.py — Remote LLM-as-a-service backend (BACKEND=openrouter).

Reuses the same quality filter, context-window builder, archaeological
schema, and validate_llm_output() as the transformers/vLLM engine (via
llm_client_shared.py — see that module's docstring for why this is a
duplicate front-end rather than an import of llm_utils.py/llm_run.py).

The prompt is the GPU path's: prompts/system_prompt.txt under the PROMPT_* flags of
the config file (llm_config.txt), with the vocabulary laid out per PROMPT_VOCAB_GROUPING,
and every result carries teater_category_ids (EMIT_CATEGORY_IDS) with a bracketed
homonym's qualifier stripped back off. A run refuses to start when the configured
guardrail wording contradicts the vocabulary (llm_client_shared.prompt_contradictions).

Two input modes, dispatched by file name:
  * .csv / *.teitok.xml / *.document.json — line-level enrichment, one OpenRouter call
    per qualifying line (matches the transformers/vLLM backends' contract); a record
    (the record after nlp-enrich) is read through its lines[] and is also the default
    baseline of --document-json-out.
  * .md / .txt — whole-document enrichment, one OpenRouter call per document (see
    llm_client_shared.run_document_level()). Optionally sent as a file attachment
    via --attach-as-file (see _build_attachment_content — best-effort,
    provider/model-dependent, per #24's "explore file-attachment options").

Data-sovereignty: --provider-data-collection deny restricts routing to
OpenRouter providers that don't retain prompts/completions. This does not by
itself resolve model licensing — see the TODO in para_config.txt.

Env:
  OPENROUTER_API_KEY — required unless --api-key is passed.
"""

import argparse
import base64
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests
from tqdm import tqdm

import prompt_template
import tool_limits
from atrium_document import canonical_doc_id
from atrium_paradata import ParadataLogger
from llm_client_shared import (
    OUTCOME_EMPTY,
    OUTCOME_FAILED,
    PROGRAM,
    TAXONOMY_CONFIG,
    ReplyTruncated,
    RequestRefused,
    attach_category_ids,
    build_document_schema,
    build_document_system_prompt,
    build_schema,
    build_system_prompt,
    category_maps,
    classify_outcome,
    contributes_document_record,
    excluded_prompt_themes,
    has_reader,
    http_error_detail,
    is_document_level,
    is_record_input,
    load_config,
    prompt_contradictions,
    redact_secrets,
    repo_path,
    run_document_level,
    run_line_level,
    write_document_record,
)
from vocab_manager import VocabularyManager, vocabulary_provenance

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# The reply cap and the tokens kept free for it are limits since atrium-project#53
# (tool_limits.py: LLM_MAX_NEW_TOKENS, read on every call). These names are their values
# at import, kept for the callers that read them; llm_utils.py (the torch path) keeps its
# own copy of the default, 2048.
MAX_NEW_TOKENS = tool_limits.LLM_MAX_NEW_TOKENS.get()
CONTEXT_RESERVED = tool_limits.reserved_tokens()
#: --context-window default: the window the service also assumes for this backend.
DEFAULT_CONTEXT_WINDOW = tool_limits.BACKEND_CONTEXT_WINDOW["openrouter"]
_DOC_INPUT_EXTENSIONS = {".md", ".txt"}


def _build_headers(
    api_key: str, site_url: Optional[str], app_name: Optional[str]
) -> Dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name
    return headers


def _build_provider_block(
    data_collection: Optional[str], only: Optional[str], order: Optional[str]
) -> Optional[Dict[str, Any]]:
    """OpenRouter 'provider' routing preferences. data_collection='deny'
    restricts routing to providers that don't retain prompts/completions —
    the data-sovereignty option requested in #24."""
    provider: Dict[str, Any] = {}
    if data_collection:
        provider["data_collection"] = data_collection
    if only:
        provider["only"] = [p.strip() for p in only.split(",") if p.strip()]
    if order:
        provider["order"] = [p.strip() for p in order.split(",") if p.strip()]
    return provider or None


def _build_attachment_content(doc_text: str, filename: str, as_file: bool) -> Any:
    """
    Best-effort file-attachment path (per #24: "explore file-attachment
    options"). as_file=True sends the document as an OpenRouter file content
    part (base64 data URL); support for this varies by model/provider, and
    falls back silently to plain inlined text on providers that ignore it.
    as_file=False (default) inlines the markdown directly as message text,
    which works uniformly across every OpenRouter model.
    """
    if not as_file:
        return f"DOCUMENT:\n{doc_text}"

    b64 = base64.b64encode(doc_text.encode("utf-8")).decode("ascii")
    return [
        {"type": "text", "text": "DOCUMENT (attached below):"},
        {
            "type": "file",
            "file": {
                "filename": filename,
                "file_data": f"data:text/markdown;base64,{b64}",
            },
        },
    ]


def make_chat_fn(
    session: requests.Session,
    headers: Dict[str, str],
    model: str,
    schema: Optional[dict],
    max_retries: int,
    timeout: int,
    provider_block: Optional[Dict[str, Any]],
    max_new_tokens: Optional[int] = None,
):
    """Returns a llm_client_shared.ChatFn bound to this OpenRouter model/session.

    Only a timeout, a connection error, HTTP 429 or 5xx is retried (atrium-project#53):
    another 4xx is refused at once as :class:`RequestRefused`, with the provider's reply.
    A reply cut at ``max_new_tokens`` (``finish_reason == "length"``, default
    ``LLM_MAX_NEW_TOKENS``) raises :class:`ReplyTruncated` and is never used.
    """

    def chat_fn(messages: List[Dict[str, str]]) -> str:
        cap = max_new_tokens if max_new_tokens is not None else tool_limits.LLM_MAX_NEW_TOKENS.get()
        body: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": cap,
            "response_format": (
                {"type": "json_schema", "json_schema": {"name": "enrichment", "schema": schema}}
                if schema is not None
                else {"type": "json_object"}
            ),
        }
        if provider_block:
            body["provider"] = provider_block

        last_exc: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = session.post(OPENROUTER_API_URL, headers=headers, json=body, timeout=timeout)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise requests.HTTPError(http_error_detail(resp, 200))
                if resp.status_code >= 400:
                    raise RequestRefused(
                        f"OpenRouter refused the request: {http_error_detail(resp)}"
                    )
                data = resp.json()
                choice = data["choices"][0]
                if choice.get("finish_reason") == "length":
                    raise ReplyTruncated(
                        f"OpenRouter cut the reply at {cap} tokens (LLM_MAX_NEW_TOKENS); "
                        "it is not used.",
                        cap,
                    )
                return choice["message"]["content"]
            except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
                last_exc = exc
                if attempt < max_retries:
                    time.sleep(min(2**attempt, 30))
        raise RuntimeError(f"OpenRouter request failed after {max_retries} attempts: {last_exc}")

    return chat_fn


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="llm_config.txt", help="Shared config file.")
    parser.add_argument(
        "--input", type=Path, default=None, help="File or directory (overrides INPUT_DIR)."
    )
    parser.add_argument("--output-dir", type=Path, default=None, help="Overrides OUTPUT_DIR.")
    parser.add_argument(
        "--model", default=None, help="OpenRouter model slug, e.g. 'openai/gpt-4o-mini'."
    )
    parser.add_argument("--api-key", default=None, help="Overrides OPENROUTER_API_KEY.")
    parser.add_argument(
        "--site-url", default=None, help="Sent as HTTP-Referer (OpenRouter app attribution)."
    )
    parser.add_argument(
        "--app-name", default=None, help="Sent as X-Title (OpenRouter app attribution)."
    )
    parser.add_argument("--provider-data-collection", choices=["allow", "deny"], default=None)
    parser.add_argument("--provider-only", default=None, help="Comma-separated provider allowlist.")
    parser.add_argument(
        "--provider-order", default=None, help="Comma-separated provider preference order."
    )
    parser.add_argument(
        "--structured-outputs",
        action="store_true",
        help="Send response_format=json_schema instead of json_object.",
    )
    parser.add_argument(
        "--attach-as-file",
        action="store_true",
        help="Send .md/.txt input as a file content part (best-effort).",
    )
    parser.add_argument(
        "--detail",
        choices=["full", "standard", "minimal"],
        default="full",
        help=(
            "Cue profile of a .md input (atrium-project#70), named by the record's "
            "regenerable.markdown recipe after a document-mode run. full keeps every layout cue."
        ),
    )
    parser.add_argument(
        "--document-json-dir",
        type=Path,
        default=None,
        help=(
            "Enable the paired per-document record (atrium_document.py): read "
            "<doc_id>.document.json from this dir as the baseline and write it back with "
            "keyword-extract's enrichment block updated. Other tools' blocks pass through."
        ),
    )
    parser.add_argument(
        "--document-json",
        type=Path,
        default=None,
        help=(
            "Single-file convenience form of --document-json-dir (issue #13): baseline "
            "ATRIUM Document JSON for a ONE-document run (--input must be a single file, "
            "not a directory). Mutually redirects into --document-json-dir internally. "
            "Default: the input itself when it is a record (*.document.json)."
        ),
    )
    parser.add_argument(
        "--document-json-out",
        type=Path,
        default=None,
        help="Exact path to write the updated ATRIUM Document JSON. Pairs with --document-json "
        "or with --input pointed at a single file.",
    )
    parser.add_argument(
        "--context-window",
        type=int,
        default=DEFAULT_CONTEXT_WINDOW,
        help="Model context window, for vocab-truncation budget.",
    )
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=120)
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    args = build_arg_parser().parse_args(argv)
    config = load_config(args.config)

    api_key = (
        args.api_key or os.environ.get("OPENROUTER_API_KEY") or config.get("OPENROUTER_API_KEY")
    )
    if not api_key:
        print(
            "[ERROR] No OpenRouter API key: pass --api-key or set OPENROUTER_API_KEY.",
            file=sys.stderr,
        )
        sys.exit(1)

    model = args.model or config.get("OPENROUTER_MODEL")
    if not model:
        print(
            "[ERROR] No model: pass --model or set OPENROUTER_MODEL in llm_config.txt.",
            file=sys.stderr,
        )
        sys.exit(1)

    input_path = args.input or Path(config.get("INPUT_DIR", "data_samples/DOC_LINE_CATEG"))
    vocab_path = str(repo_path(config.get("VOCAB_PATH", "data_samples/vocab/union_nested.json")))
    paradata_dir = config.get("PARADATA_DIR", "paradata")

    model_suffix = model.replace("/", "_").replace(".", "").replace(":", "_")
    output_base = Path(config.get("OUTPUT_DIR", "data_samples/KW_PER_DOC_LLM"))
    output_dir = args.output_dir or (output_base.parent / f"{output_base.name}_{model_suffix}")
    output_dir.mkdir(parents=True, exist_ok=True)

    include_non_text = config.get("INCLUDE_NON_TEXT", "true").lower() == "true"
    min_char_count = int(config.get("MIN_CHAR_COUNT", "3"))
    min_char_non_text = int(config.get("MIN_CHAR_NON_TEXT", "8"))
    min_alpha_ratio_non_text = float(config.get("MIN_ALPHA_RATIO_NON_TEXT", "0.40"))
    # M7 (issue #6): the id passthrough stays behind a switch, as in llm_run.py.
    emit_category_ids = config.get("EMIT_CATEGORY_IDS", "true").lower() == "true"

    provider_block = _build_provider_block(
        args.provider_data_collection, args.provider_only, args.provider_order
    )

    print(
        f"\n=== LLM Semantic Enrichment Pipeline (BACKEND=openrouter) ===\n    model:   {model}\n    output:  {output_dir}\n"
    )
    if provider_block:
        print(f"  Provider routing: {provider_block}")

    # D3 (issue #6): which vocabulary build the prompt carried, and its sources' licences.
    provenance = vocabulary_provenance(vocab_path)
    logger = ParadataLogger(
        program=PROGRAM,
        config={
            **redact_secrets(config),
            "backend": "openrouter",
            "model": model,
            "output_dir_resolved": str(output_dir),
            **({"vocabulary": provenance} if provenance else {}),
        },
        paradata_dir=paradata_dir,
        output_types=["json"],
    )
    print(prompt_template.describe(config))
    for component in provenance.get("components", []):
        logger.log_component(component)

    with logger:
        vocab_mgr = VocabularyManager(
            vocab_path=vocab_path, config_path=str(repo_path(TAXONOMY_CONFIG))
        )
        # auto_sync=False: never harvest inside a pipeline run. Besides the
        # multi-minute OAI-PMH round trip, the sync path can no longer build a
        # usable vocabulary — fetch_amcr_vocab() emits bare {"cs", "en"} pairs
        # with no "source"/"scheme", so assign_theme() drops every term into
        # "Other", which excluded_prompt_themes() withholds from the prompt. The
        # result is an enum holding only "Nerelevantní (meta-text)", which then
        # rejects every correct answer the model gives as a validation error.
        # A missing vocabulary is a configuration fault: say so and stop.
        vocab_data = vocab_mgr.load(auto_sync=False)

        # Which themes reach the model is a taxonomy_config decision (in_prompt),
        # not a literal in the prompt builder — see excluded_prompt_themes().
        excluded_themes = excluded_prompt_themes(vocab_mgr)

        # The build refuses a vocabulary whose guardrail contradicts the wording the config
        # selects; a run under another config could still send one. Refuse that too.
        contradictions = prompt_contradictions(vocab_mgr, config)
        if contradictions:
            print(
                "[ERROR] the prompt contradicts the vocabulary: " + "; ".join(contradictions),
                file=sys.stderr,
            )
            sys.exit(1)

        max_input_tokens = args.context_window - CONTEXT_RESERVED
        line_prompt, line_terms = build_system_prompt(
            vocab_data,
            max_tokens=max_input_tokens,
            excluded_themes=excluded_themes,
            prompt_config=config,
        )
        doc_prompt, doc_terms = build_document_system_prompt(
            vocab_data,
            max_tokens=max_input_tokens,
            excluded_themes=excluded_themes,
            prompt_config=config,
        )
        LineModel = build_schema(line_terms)
        DocModel = build_document_schema(doc_terms)
        line_maps = category_maps(vocab_data, line_terms, excluded_themes)
        doc_maps = category_maps(vocab_data, doc_terms, excluded_themes)

        headers = _build_headers(api_key, args.site_url, args.app_name)
        session = requests.Session()

        line_schema = LineModel.model_json_schema() if args.structured_outputs else None
        doc_schema = DocModel.model_json_schema() if args.structured_outputs else None
        line_chat_fn = make_chat_fn(
            session, headers, model, line_schema, args.max_retries, args.timeout, provider_block
        )
        doc_chat_fn = make_chat_fn(
            session, headers, model, doc_schema, args.max_retries, args.timeout, provider_block
        )

        def _make_doc_builder(filename: str) -> Callable[[str], Any]:
            """Per-document user-content builder for run_document_level(); routes
            the .md/.txt body through _build_attachment_content so --attach-as-file
            actually takes effect (inlined text when the flag is off)."""
            return lambda doc_text: _build_attachment_content(
                doc_text, filename, args.attach_as_file
            )

        if input_path.is_file():
            input_files = [input_path]
        else:
            input_files = sorted(
                p
                for p in input_path.iterdir()
                if p.suffix.lower() in _DOC_INPUT_EXTENSIONS
                or is_record_input(p)
                or p.suffix.lower() == ".csv"
                or p.name.lower().endswith(".teitok.xml")
            )

        # Fail before spending anything on a file no branch can read. Directory
        # enumeration above already filters to readable types, so in practice this
        # catches an explicit --input naming the wrong thing — which is exactly how
        # a *.document.json record used to reach the line-level branch and enrich
        # nothing while exiting 0 (atrium-project run 34039707673).
        unreadable = [p for p in input_files if not has_reader(p)]
        if unreadable:
            print(
                "[ERROR] no reader for: "
                + ", ".join(p.name for p in unreadable)
                + ". Expected .csv / *.teitok.xml / *.document.json (line-level) or "
                ".md / .txt (document-level). Convert a PDF or DOCX with "
                "atrium-digital-convert and send its record.",
                file=sys.stderr,
            )
            sys.exit(1)

        # --document-json/--document-json-out (issue #13): a single-file convenience
        # wrapper around the existing, working --document-json-dir path below. Redirect
        # into it here so the write_document_record() call site further down needs no
        # changes at all.
        doc_json_scratch_dir: Optional[Path] = None
        if args.document_json or args.document_json_out:
            if len(input_files) != 1:
                print(
                    f"[document] --document-json/-out require exactly one input file, "
                    f"got {len(input_files)} — skipping the document record for this run",
                    file=sys.stderr,
                )
            else:
                doc_json_scratch_dir = Path(tempfile.mkdtemp(prefix="atrium_document_json_"))
                # A record input is its own baseline unless one is named: its lines are
                # what was enriched, so the record they came from is what gets the block.
                baseline = args.document_json or (
                    input_files[0] if is_record_input(input_files[0]) else None
                )
                if baseline:
                    if not Path(baseline).exists():
                        print(
                            f"[document] baseline {baseline} not found — "
                            "emitting keyword-extract's own part only",
                            file=sys.stderr,
                        )
                    else:
                        # Must agree with the loop's derivation below, or the copy is
                        # filed under a name write_document_record() never looks for
                        # (atrium-project#10, D1).
                        doc_id = canonical_doc_id(input_files[0])
                        shutil.copyfile(baseline, doc_json_scratch_dir / f"{doc_id}.document.json")
                args.document_json_dir = doc_json_scratch_dir

        total_processed = total_errors = total_aborted = 0
        #: doc_id -> the record THIS RUN wrote, as returned by write_document_record().
        #: Tracked rather than re-discovered by globbing the scratch dir, because that dir
        #: already holds the copy of the caller's `--document-json` baseline: a glob cannot
        #: tell "this run wrote this" from "this run was handed this" (atrium-project#49).
        document_records: dict = {}
        for f in tqdm(input_files, desc="Documents", unit="doc", dynamic_ncols=True):
            # canonical_doc_id(), never Path.stem (atrium-project#10, D1). `.stem` strips
            # only the LAST extension, so an accepted `CTX000000001.teitok.xml` input gave
            # the doc_id `CTX000000001.teitok`; write_document_record() then looked for a
            # baseline named `CTX000000001.teitok.document.json`, which no upstream tool
            # ever writes, so DocumentRecord.open() fell back to rule 3 and DISCARDED every
            # upstream block (pages/lines/entities/translations) — emitting an orphan record
            # under a doc_id nothing else in the pipeline uses. llm_run.py has always
            # derived it correctly; this loop and ollama_client.py's were the two that did not.
            doc_id = canonical_doc_id(f)
            out_file = output_dir / f"{doc_id}_enriched.json"
            if out_file.exists():
                logger.log_skip(f.name, "already_exists")
                continue

            try:
                document_mode = is_document_level(f)
                if document_mode:
                    results, stats = run_document_level(
                        f,
                        doc_chat_fn,
                        doc_prompt,
                        DocModel,
                        user_content_builder=_make_doc_builder(f.name),
                    )
                else:
                    results, stats = run_line_level(
                        f,
                        line_chat_fn,
                        line_prompt,
                        LineModel,
                        include_non_text=include_non_text,
                        min_char_count=min_char_count,
                        min_char_non_text=min_char_non_text,
                        min_alpha_ratio_non_text=min_alpha_ratio_non_text,
                        max_consecutive_errors=tool_limits.LLM_MAX_CONSECUTIVE_ERRORS.get(),
                    )
                attach_category_ids(
                    results, *(doc_maps if document_mode else line_maps), emit_category_ids
                )

                total_processed += stats["processed"]
                total_errors += stats["skipped_error"]
                total_aborted += int(bool(stats.get("aborted")))

                outcome = classify_outcome(results, stats)

                if results:
                    with open(out_file, "w", encoding="utf-8") as out_f:
                        json.dump(results, out_f, indent=4, ensure_ascii=False)
                    tqdm.write(f"  -> {len(results)} records -> {out_file.name}")
                    logger.log_success("json", count=1)
                    logger.log_document_success()
                elif outcome == OUTCOME_EMPTY:
                    # NOT an error, and not silence either. The model was asked and
                    # located nothing enrichable; say so on stdout so a CI log reader
                    # can tell this apart from the failure branch below without
                    # diffing artifacts (atrium-project#49).
                    tqdm.write(f"  -> 0 records: the model located nothing enrichable in {f.name}")
                    logger.log_skip(f.name, "No records produced (model located nothing).")
                elif outcome == OUTCOME_FAILED:
                    tqdm.write(
                        f"  -> 0 records: every inference call for {f.name} failed "
                        f"({stats['skipped_error']} error(s)"
                        f"{', aborted' if stats.get('aborted') else ''})"
                    )
                    logger.log_skip(f.name, "No records produced (inference failed).")
                else:  # OUTCOME_NOT_ASKED
                    tqdm.write(
                        f"  -> 0 records: nothing in {f.name} was ever sent to the model "
                        f"({stats['skipped_filter']} line(s) dropped by the quality filter)"
                    )
                    logger.log_skip(f.name, "No records produced (nothing reached the model).")

                # The document record is this stage's account of ITS OWN RUN, not a
                # wrapper around the enriched json — so it is written for a verdict of
                # "nothing here" exactly as it is for a verdict with items in it, and
                # withheld only when there is no verdict at all. Guarding it on
                # `if results:` conflated the two and is what atrium-project#49 is.
                if args.document_json_dir is not None and contributes_document_record(
                    results, stats
                ):
                    record_path = write_document_record(
                        doc_id,
                        results,
                        args.document_json_dir,
                        run_id=logger.run_id,
                        run_uuid=logger.run_uuid,
                        paradata_ref=logger.paradata_ref,
                        # No records means no `*_enriched.json` was written, so there is
                        # nothing to point `derived_from` at. Claiming a file that is not
                        # on disk would be a worse record than omitting the link.
                        enriched_path=out_file if results else None,
                        used_markdown_input=document_mode,
                        detail=args.detail,
                        license_detail=logger.get_license_block(),
                        # Same directory the prompt vocabulary was loaded from, so
                        # entities[].pid resolves against the artifacts this run actually
                        # used rather than resolve_pid's built-in default path.
                        vocab_dir=os.path.dirname(vocab_path) or ".",
                    )
                    if record_path is not None:
                        document_records[doc_id] = Path(record_path)

            except Exception as exc:
                tqdm.write(f"  Critical error on {f.name}: {exc}")
                logger.log_skip(f.name, str(exc))

        print(
            f"\n=== Run complete ===\n"
            f"    records enriched:  {total_processed}\n"
            f"    inference errors:  {total_errors}\n"
            f"    aborted documents: {total_aborted}\n"
            f"    files processed:   {len(input_files)}\n"
        )
        logger.finalize(input_total=len(input_files))

        if doc_json_scratch_dir is not None and args.document_json_out:
            # `document_records`, NOT a glob of the scratch dir. The scratch dir is seeded
            # with a copy of `--document-json` before the loop runs, so globbing it finds a
            # file whether or not this run contributed anything — which is how run
            # 34090340995 shipped the caller's own baseline back as "the llm-enrich stage's
            # record", printed "Record written", and exited 0 (atrium-project#49, when this
            # code was llm-enrich's).
            if not document_records:
                print(
                    f"[document] keyword-extract contributed no enrichment verdict, so "
                    f"{args.document_json_out} was NOT written. The baseline passed in via "
                    f"--document-json is unchanged and is NOT this stage's output — "
                    f"re-emitting it would claim a contribution that did not happen. "
                    f"See the per-document lines above for which outcome this was.",
                    file=sys.stderr,
                )
                sys.exit(1)
            out_path = Path(args.document_json_out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(next(iter(document_records.values())), out_path)
            print(f"[document] Record written → {out_path}", flush=True)


if __name__ == "__main__":
    main()
