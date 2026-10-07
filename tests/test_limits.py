"""tests/test_limits.py — every limit is a setting, and none cuts an input quietly.

atrium-project#53 (factor III), for this repo: the limits are declared in tool_limits.py, an
input over one is refused with the harmonised error, a full service answers 429 ``busy``, and
every limit that shapes a result without refusing it is recorded (``limits_applied``). The
endpoint-level cases (413, 422, 429) are in tests/test_api_service.py and test_api_contract.py;
tests/test_limits_contract.py (canonical) checks the declaration against .env.example and
service/README.md.

The controlled kind's limits came with llm-enrich's engine (atrium-digital-convert 31534d5,
atrium-keyword-extract#1), and so did their tests below: the context window defaults per backend,
a reply cut at the token cap is never used, only transient failures are retried, and the
vocabulary cut is reported.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import keywords as kw
import tool_limits
from atrium_limits import LimitExceeded
from llm_client_shared import (
    ReplyTruncated,
    RequestRefused,
    build_document_schema,
    build_schema,
    run_document_level,
    run_line_level,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# ── the declaration ─────────────────────────────────────────────────────────────────────


def test_every_limit_is_an_environment_setting_with_a_default():
    env = {spec.env for spec in tool_limits.LIMITS}
    assert {
        "MAX_UPLOAD_MB",
        "MAX_DOCUMENT_WORDS",
        "MAX_KEYWORDS",
        "MAX_CONCURRENT_REQUESTS",
        "KEYBERT_CHUNK_WORDS",
        "KEYBERT_CHUNK_OVERLAP",
        "LLM_CONTEXT_WINDOW",
        "LLM_MAX_NEW_TOKENS",
        "LLM_TIMEOUT",
        "LLM_MAX_RETRIES",
        "LLM_MAX_CONSECUTIVE_ERRORS",
    } == env
    assert tool_limits.MAX_UPLOAD.get() == 10


def test_a_malformed_setting_stops_the_process_naming_the_variable(monkeypatch):
    from atrium_limits import LimitConfigError

    monkeypatch.setenv("MAX_KEYWORDS", "many")
    with pytest.raises(LimitConfigError, match="MAX_KEYWORDS"):
        tool_limits.MAX_KEYWORDS.get()


def test_over_max_keywords_is_limit_exceeded_with_status_422(monkeypatch):
    monkeypatch.setenv("MAX_KEYWORDS", "5")
    with pytest.raises(LimitExceeded) as caught:
        tool_limits.MAX_KEYWORDS.check(6)
    assert caught.value.http_status == 422 and caught.value.key == "max_keywords"


def test_over_max_document_words_is_limit_exceeded_with_status_413(monkeypatch):
    monkeypatch.setenv("MAX_DOCUMENT_WORDS", "10")
    with pytest.raises(LimitExceeded) as caught:
        tool_limits.MAX_DOCUMENT_WORDS.check(11)
    assert caught.value.http_status == 413


# ── notes: KeyBERT chunking ─────────────────────────────────────────────────────────────


class _Encoder:
    max_seq_length = 8

    @staticmethod
    def tokenizer(text):
        return {"input_ids": ["[CLS]", *text.split(), "[SEP]"]}


class _KeyBERT:
    model = SimpleNamespace(embedding_model=_Encoder())

    def extract_keywords(self, chunks, **_kw):
        return [[(chunk.split()[0], 0.5)] for chunk in chunks]


def test_keybert_chunking_is_a_setting_and_is_counted(monkeypatch):
    monkeypatch.setenv("KEYBERT_CHUNK_WORDS", "10")
    monkeypatch.setenv("KEYBERT_CHUNK_OVERLAP", "2")
    monkeypatch.setattr(kw, "_get_keybert_model", lambda _name: _KeyBERT())
    monkeypatch.setattr(
        kw,
        "_extract_surface_text",
        lambda p: " ".join(f"w{i}" for i in range(25)) if p == "long" else "a b",
    )
    counts: dict = {}
    result = kw._extract_keybert(["long", "short"], 5, limit_counts=counts)
    assert len(result) == 2 and result[1] == [("a", 0.5)]
    # 25 words, chunks of 10 starting every 8 words: w0-w9, w8-w17, w16-w24 (over the 8-token
    # window) and w24 (not over it) -- the chunking the literal 400/50 always did.
    assert counts == {"split": 1, "trimmed": 3, "window": 8}
    assert [c.split()[0] for c in kw._chunk_words([f"w{i}" for i in range(25)], 10, 2)] == [
        "w0",
        "w8",
        "w16",
        "w24",
    ]


def test_the_text_entry_point_chunks_the_same_way(monkeypatch):
    monkeypatch.setenv("KEYBERT_CHUNK_WORDS", "10")
    monkeypatch.setenv("KEYBERT_CHUNK_OVERLAP", "2")
    monkeypatch.setattr(kw, "_get_keybert_model", lambda _name: _KeyBERT())
    counts: dict = {}
    result = kw.extract_from_texts(
        [" ".join(f"w{i}" for i in range(25)), "a b", ""], "keybert", 5, limit_counts=counts
    )
    assert [len(r) for r in result] == [4, 1, 0]
    assert counts["split"] == 1


def test_keybert_notes_reach_the_paradata(tmp_path):
    from atrium_paradata import ParadataLogger

    logger = ParadataLogger(program="keyword-extract", config={}, paradata_dir=str(tmp_path))
    kw._note_keybert_limits(logger, {"split": 2, "trimmed": 5, "window": 128})
    notes = {n["limit"]: n for n in logger.limits_applied}
    assert (notes["keybert_chunk_words"]["effect"], notes["keybert_chunk_words"]["count"]) == (
        "split",
        2,
    )
    assert (notes["keybert_max_seq_tokens"]["value"], notes["keybert_max_seq_tokens"]["count"]) == (
        128,
        5,
    )


# ── the controlled kind: the context window, per backend, then the config file, then the env ──

_LINE_REPLY = json.dumps(
    {
        "extracted_keywords_cs": ["kostel"],
        "extracted_keywords_en": ["church"],
        "teater_category": "kostel",
        "confidence_score": 0.9,
    }
)
_CSV = (
    "text,page_num,line_num,categ,quality_score\n"
    "Výzkum odhalil základy gotického kostela.,1,1,Clear,0.9\n"
    "Další řádek o nálezu keramiky u kostela.,1,2,Clear,0.9\n"
    "Třetí řádek o hrobech na hřbitově.,1,3,Clear,0.9\n"
)


def _resp(status=200, payload=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload or {}
    r.text = text or json.dumps(payload or {})
    return r


def _run(code: str, **env) -> subprocess.CompletedProcess:
    """Import tool_limits in a fresh interpreter (its defaults are read at import)."""
    import os

    full = {k: v for k, v in os.environ.items() if not k.startswith("LLM_")}
    full.update(env)
    return subprocess.run(
        [sys.executable, "-c", code], cwd=REPO_ROOT, env=full, capture_output=True, text=True
    )


def test_the_context_window_defaults_per_backend():
    code = "import tool_limits as t; print(t.LLM_CONTEXT_WINDOW.default, t.context_window())"
    assert _run(code).stdout.split() == ["128000", "128000"]
    assert _run(code, LLM_BACKEND="ollama").stdout.split() == ["32000", "32000"]
    assert _run(code, LLM_BACKEND="ollama", LLM_CONTEXT_WINDOW="64000").stdout.split() == [
        "32000",
        "64000",
    ]


def test_the_config_files_context_window_comes_before_the_default(tmp_path, monkeypatch):
    cfg = tmp_path / "llm_config.txt"
    cfg.write_text('# comment\nCONTEXT_WINDOW="16000"\n', encoding="utf-8")
    monkeypatch.setenv("LLM_CONFIG", str(cfg))
    monkeypatch.delenv("LLM_CONTEXT_WINDOW", raising=False)
    assert tool_limits.context_window() == 16000
    assert tool_limits.LIMITS.meta()["llm_context_window"]["source"] == "config"
    monkeypatch.setenv("LLM_CONTEXT_WINDOW", "20000")
    assert tool_limits.context_window() == 20000
    assert tool_limits.vocab_prompt_budget_tokens() == 20000 - 2048 - 512


def test_a_window_with_no_room_for_the_prompt_fails_at_import():
    result = _run("import tool_limits", LLM_CONTEXT_WINDOW="2000")
    assert result.returncode != 0
    assert "LimitConfigError" in result.stderr and "LLM_CONTEXT_WINDOW" in result.stderr


def test_a_malformed_limit_fails_at_import_naming_it():
    result = _run("import tool_limits", LLM_MAX_NEW_TOKENS="lots")
    assert result.returncode != 0 and "LLM_MAX_NEW_TOKENS" in result.stderr


# ── the clients: the cap is sent, a cut reply is refused, only transient errors retried ──


def test_openrouter_sends_the_cap_and_refuses_a_cut_reply(monkeypatch):
    from openrouter_client import make_chat_fn

    monkeypatch.setenv("LLM_MAX_NEW_TOKENS", "64")
    session = MagicMock()
    session.post.return_value = _resp(
        payload={"choices": [{"message": {"content": "{"}, "finish_reason": "length"}]}
    )
    chat = make_chat_fn(session, {}, "m", None, 3, 7, None)
    with pytest.raises(ReplyTruncated, match="64 tokens") as info:
        chat([{"role": "user", "content": "x"}])
    assert info.value.max_new_tokens == 64
    assert session.post.call_count == 1  # not retried
    assert session.post.call_args.kwargs["json"]["max_tokens"] == 64
    assert session.post.call_args.kwargs["timeout"] == 7


def test_openrouter_does_not_retry_a_4xx_and_keeps_its_body(monkeypatch):
    from openrouter_client import make_chat_fn

    monkeypatch.setattr("openrouter_client.time.sleep", lambda _s: None)
    session = MagicMock()
    session.post.return_value = _resp(400, text='{"error": "context length exceeded"}')
    chat = make_chat_fn(session, {}, "m", None, 3, 7, None)
    with pytest.raises(RequestRefused, match="context length exceeded"):
        chat([{"role": "user", "content": "x"}])
    assert session.post.call_count == 1

    session.post.reset_mock()
    session.post.return_value = _resp(503, text="overloaded")
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        chat([{"role": "user", "content": "x"}])
    assert session.post.call_count == 3


def test_ollama_gets_the_window_and_the_cap_and_refuses_a_cut_reply(monkeypatch):
    from ollama_client import make_chat_fn

    monkeypatch.setattr("ollama_client.time.sleep", lambda _s: None)
    monkeypatch.setenv("LLM_MAX_NEW_TOKENS", "128")
    monkeypatch.setenv("LLM_CONTEXT_WINDOW", "16000")
    session = MagicMock()
    session.post.return_value = _resp(payload={"message": {"content": "{}"}, "done_reason": "stop"})
    chat = make_chat_fn(session, "http://o", "m", {}, 2, 9)
    assert chat([{"role": "user", "content": "x"}]) == "{}"
    options = session.post.call_args.kwargs["json"]["options"]
    assert (options["num_ctx"], options["num_predict"]) == (16000, 128)

    session.post.return_value = _resp(
        payload={"message": {"content": "{"}, "done_reason": "length"}
    )
    with pytest.raises(ReplyTruncated):
        chat([{"role": "user", "content": "x"}])

    session.post.reset_mock()
    session.post.return_value = _resp(404, text="model 'm' not found")
    with pytest.raises(RequestRefused, match="not found"):
        chat([{"role": "user", "content": "x"}])
    assert session.post.call_count == 1


# ── the shared drivers count what the limits did ─────────────────────────────────────


def _truncating_chat(_messages):
    raise ReplyTruncated("cut", 2048)


def test_line_mode_counts_cut_replies_and_the_stop(tmp_path):
    csv_path = tmp_path / "d.csv"
    csv_path.write_text(_CSV, encoding="utf-8")
    records, stats = run_line_level(
        csv_path, _truncating_chat, "p", build_schema(["kostel"]), max_consecutive_errors=2
    )
    assert records == []
    assert (stats["truncated"], stats["aborted"], stats["unprocessed"]) == (2, 1, 1)


def test_document_mode_raises_in_strict_mode_only(tmp_path):
    doc = tmp_path / "d.md"
    doc.write_text("Výzkum odhalil základy kostela.", encoding="utf-8")
    model = build_document_schema(["kostel"])
    records, stats = run_document_level(doc, _truncating_chat, "p", model)
    assert (records, stats["aborted"], stats["truncated"]) == ([], 1, 1)
    with pytest.raises(ReplyTruncated):
        run_document_level(doc, _truncating_chat, "p", model, strict=True)


# ── the service ──────────────────────────────────────────────────────────────────────

_RECORD = {
    "schema_version": "1.0",
    "record_type": "atrium-document",
    "doc_id": "CTX1",
    "lines": [
        {
            "page": "1",
            "line": n,
            "text": f"Řádek {n} o základech gotického kostela.",
            "categ": "Clear",
        }
        for n in range(1, 4)
    ],
}


def _post(client, kind="controlled"):
    files = {"document_json": ("r.document.json", json.dumps(_RECORD), "application/json")}
    return client.post("/extract_keywords", files=files, data={"kind": kind, "method": "yake"})


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from service import api

    return TestClient(api.app)


def test_line_mode_notes_cut_replies_and_the_stop(client, controlled, monkeypatch):
    import keywords

    def yake(text, num_keywords, lang="cs", max_words=3, source="text"):
        return [("kostel", 0.9)]

    monkeypatch.setattr(keywords, "_yake_from_text", yake)
    monkeypatch.setenv("LLM_MAX_CONSECUTIVE_ERRORS", "2")
    replies = iter([_LINE_REPLY])

    def first_then_cut(_messages):
        try:
            return next(replies)
        except StopIteration:
            raise ReplyTruncated("cut", 2048) from None

    controlled.chat.reply = first_then_cut
    response = _post(client, kind="both")
    assert response.status_code == 200
    notes = {n["limit"]: n for n in response.json()["limits_applied"]}
    assert (notes["llm_max_new_tokens"]["effect"], notes["llm_max_new_tokens"]["count"]) == (
        "skipped",
        2,
    )
    assert notes["llm_max_consecutive_errors"]["effect"] == "stopped"
    assert "0 line(s) after them" in notes["llm_max_consecutive_errors"]["detail"]
    assert len(response.json()["enrichment"]["items"]) == 1  # the line before keeps its result


def test_every_reply_cut_is_422_limit_exceeded_not_a_backend_error(client, controlled):
    controlled.chat.reply = _truncating_chat
    response = _post(client)
    assert response.status_code == 422
    body = response.json()
    assert body["reason"] == "limit_exceeded" and body["limit"]["key"] == "llm_max_new_tokens"


def test_exhausted_retries_are_502_not_an_empty_200(client, controlled):
    def failing(_messages):
        raise RuntimeError("OpenRouter request failed after 3 attempts: HTTP 503")

    controlled.chat.reply = failing
    response = _post(client)
    assert response.status_code == 502 and "after 3 attempts" in response.json()["detail"]


def test_info_reports_every_limit(client, monkeypatch):
    monkeypatch.setenv("LLM_MAX_NEW_TOKENS", "1024")
    data = client.get("/info").json()
    assert data["limits"] == tool_limits.LIMITS.values()
    assert data["limits"]["vocab_prompt_budget_tokens"] == tool_limits.context_window() - 1024 - 512
    assert data["limits_meta"]["vocab_prompt_budget_tokens"]["source"] == "derived"


def test_the_engine_records_the_vocabulary_cut_and_every_response_carries_it(
    client, monkeypatch, caplog
):
    if not (REPO_ROOT / "data_samples" / "vocab" / "union_nested.json").is_file():
        pytest.skip("no shipped vocabulary here")
    import openrouter_client
    from service import api
    from tests.conftest import StubChat

    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")
    monkeypatch.setenv("LLM_CONTEXT_WINDOW", "8000")
    chat = StubChat()
    monkeypatch.setattr(openrouter_client, "make_chat_fn", lambda *_a, **_kw: chat)
    with caplog.at_level("WARNING", logger="service.api"):
        engine = api._load_controlled()
    vocab = engine["vocabulary"]
    assert vocab["prompt_terms"] < vocab["terms"]
    [note] = engine["vocab_notes"].as_list()
    assert note["count"] == vocab["terms"] - vocab["prompt_terms"]
    assert note["value"] == 8000 - 2048 - 512
    assert "vocabulary terms left out" in caplog.text

    # At 8k the facets past the cut are not offered (`kostel` among them): answer meta-text,
    # which every prompt offers first.
    chat.reply = lambda _messages: json.dumps(
        {
            "extracted_keywords_cs": [],
            "extracted_keywords_en": [],
            "teater_category": "Nerelevantní (meta-text)",
            "confidence_score": 1.0,
        }
    )
    monkeypatch.setattr(api, "_controlled", engine)
    body = _post(client).json()
    assert body["limits_applied"][0]["limit"] == "vocab_prompt_budget_tokens"
    assert body["limits_applied"][0]["count"] == note["count"]
