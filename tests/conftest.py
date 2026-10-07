"""
tests/conftest.py
=================
Shared pytest fixtures and sys.path wiring for atrium-keyword-extract unit tests.

sys.path is patched here (once, at collection time) so that every test module
can import from the repo root (``keywords.py``, ``atrium_paradata.py``).
"""

import sys
from pathlib import Path

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow integration smoke tests")


# ── path wiring ───────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── CoNLL-U fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def sample_conllu(tmp_path):
    """
    Three-sentence CoNLL-U file written to a temp path.

    Sentences:
        1. "Archeologický výzkum byl proveden."   (ADJ NOUN AUX VERB PUNCT)
        2. "Nalezená keramika a nádoby."           (ADJ NOUN CCONJ NOUN PUNCT)
        3. "Starý výzkum trval."                   (ADJ NOUN VERB PUNCT)

    Lemma counts: výzkum=2, archeologický=1, nalezený=1,
                  keramika=1, nádoba=1, starý=1

    SpaceAfter=No is set on every VERB/ADJ token immediately before a period,
    so "proveden." / "nádoby." / "trval." have no space between word and stop.
    """
    content = (FIXTURES_DIR / "sample.conllu").read_text(encoding="utf-8")
    dest = tmp_path / "sample.conllu"
    dest.write_text(content, encoding="utf-8")
    return str(dest)


@pytest.fixture
def empty_conllu(tmp_path):
    """CoNLL-U file with only a comment header — no token lines."""
    dest = tmp_path / "empty.conllu"
    dest.write_text("# newdoc\n", encoding="utf-8")
    return str(dest)


# ── the controlled kind: the real engine, a stubbed LLM ───────────────────────


class StubChat:
    """The LLM backend's chat function, stubbed: records the messages, answers with ``reply``.

    ``reply`` takes the messages and returns the model's raw text (or raises, like a failing
    backend). The default labels a target line by the first vocabulary term it contains, from
    the few the tests use, and anything else as meta-text — a schema-valid answer either way.
    """

    LABELS = (("kostel", "kostel"), ("zámek", "zámek (sídlo elity)"), ("keramik", "keramika"))

    def __init__(self) -> None:
        self.calls: list = []
        self.reply = self.default_reply

    @staticmethod
    def target(messages) -> str:
        user = messages[-1]["content"]
        return user.split("<target_line>", 1)[1].split("</target_line>", 1)[0]

    @classmethod
    def default_reply(cls, messages) -> str:
        import json

        line = cls.target(messages).lower()
        for needle, label in cls.LABELS:
            if needle in line:
                return json.dumps(
                    {
                        "extracted_keywords_cs": [needle],
                        "extracted_keywords_en": [needle],
                        "teater_category": label,
                        "confidence_score": 0.8,
                    },
                    ensure_ascii=False,
                )
        return json.dumps(
            {
                "extracted_keywords_cs": ["x"],
                "extracted_keywords_en": ["x"],
                "teater_category": "Nerelevantní (meta-text)",
                "confidence_score": 1.0,
            },
            ensure_ascii=False,
        )

    def __call__(self, messages):
        self.calls.append(messages)
        return self.reply(messages)


@pytest.fixture(scope="session")
def _controlled_session():
    """``service.api._load_controlled()`` once per session: the shipped vocabulary, the prompt
    llm_config.txt configures and the schema, with OpenRouter's chat function stubbed."""
    pytest.importorskip("fastapi")
    if not (_REPO_ROOT / "data_samples" / "vocab" / "union_nested.json").is_file():
        pytest.skip("no built vocabulary here (vocab_build.py)")
    import openrouter_client
    from service import api

    chat = StubChat()
    with pytest.MonkeyPatch.context() as mp:
        for name in ("LLM_CONTEXT_WINDOW", "LLM_CONFIG", "VOCAB_PATH", "OPENROUTER_APP_NAME"):
            mp.delenv(name, raising=False)
        mp.setenv("LLM_BACKEND", "openrouter")
        mp.setenv("OPENROUTER_API_KEY", "test")
        mp.setenv("OPENROUTER_MODEL", "test/model")
        mp.setattr(openrouter_client, "make_chat_fn", lambda *_a, **_kw: chat)
        engine = api._load_controlled()
    return engine, chat


@pytest.fixture
def controlled(monkeypatch, _controlled_session):
    """The service with a ready controlled kind; ``controlled.chat.reply`` sets the model's answer."""
    from types import SimpleNamespace

    from service import api

    engine, chat = _controlled_session
    chat.calls.clear()
    chat.reply = chat.default_reply
    monkeypatch.setattr(api, "_controlled", dict(engine))
    return SimpleNamespace(engine=api._controlled, chat=chat)


# ── remote-client end-to-end scaffolding (atrium-project#10, D1) ──────────────
#
# Came with llm-enrich's clients (atrium-digital-convert 31534d5, atrium-keyword-extract#1).
# openrouter_client.main() and ollama_client.main() were both untestable end-to-end: every
# path they read (config, vocabulary, paradata, output) is repo-relative, and the first
# thing they do is build an HTTP session. The fixtures below redirect all of it into
# tmp_path and stub the one network call, so the D1 regression — a `.teitok.xml` input
# whose doc_id forked and discarded every upstream block — can be pinned by running the
# real `main()` rather than a re-implementation of it.

#: The doc_id the whole pipeline uses for the fixture document. Deliberately a name whose
#: `Path.stem` is WRONG (`CTX000000001.teitok`), because that is the bug.
E2E_DOC_ID = "CTX000000001"

_TEITOK_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<teiCorpus>
    <text>
        <pb n="1"/>
        <s text="Výzkum odhalil základy gotického kostela."/>
        <lb/>
        <s text="Sonda I byla založena roku 1956."/>
    </text>
</teiCorpus>
"""

#: A two-term vocabulary in the built shape: a term with the records the dedup merged into it,
#: and a homonym the build qualified (issue #6, B2/B3).
TOY_VOCAB = {
    "Site Types": {
        "kostel": {
            "cs": "kostel",
            "en": "church",
            "source": "amcr",
            "source_id": "HES-000021",
            "discarded_ids": [{"source": "teater", "id": "1333", "cs": "kostel", "en": "church"}],
        },
        "zámek (sídlo elity)": {
            "cs": "zámek (sídlo elity)",
            "en": "châteaux",
            "sub": "sídlo elity",
            "source": "teater",
            "source_id": "1439",
            "discarded_ids": [],
            "bare_cs": "zámek",
        },
    }
}


@pytest.fixture
def remote_client_env(tmp_path):
    """A self-contained working tree for a one-document openrouter/ollama ``main()`` run.

    The config carries the shipped prompt flags' one decision that matters here: the relaxed
    geographic guardrail the reinstated vocabulary needs (the clients refuse a contradiction).
    """
    import json

    vocab = tmp_path / "vocab.json"
    vocab.write_text(json.dumps(TOY_VOCAB, ensure_ascii=False), encoding="utf-8")

    config = tmp_path / "llm_config.txt"
    config.write_text(
        "\n".join(
            [
                f"VOCAB_PATH={vocab}",
                f"PARADATA_DIR={tmp_path / 'paradata'}",
                f"OUTPUT_DIR={tmp_path / 'out'}",
                "INCLUDE_NON_TEXT=true",
                "PROMPT_GEO_GUARDRAIL=preference",
                "",
            ]
        ),
        encoding="utf-8",
    )

    teitok = tmp_path / f"{E2E_DOC_ID}.teitok.xml"
    teitok.write_text(_TEITOK_FIXTURE, encoding="utf-8")

    record_dir = tmp_path / "doc_json"
    record_dir.mkdir()

    from types import SimpleNamespace

    return SimpleNamespace(
        root=tmp_path,
        doc_id=E2E_DOC_ID,
        config=config,
        teitok=teitok,
        output_dir=tmp_path / "out",
        record_dir=record_dir,
        # Where an upstream tool writes it, and the only place this stage may write it.
        baseline=record_dir / f"{E2E_DOC_ID}.document.json",
        # Where the pre-fix `Path.stem` derivation looked instead — nothing may appear here.
        forked_record=record_dir / f"{E2E_DOC_ID}.teitok.document.json",
    )


@pytest.fixture
def seeded_baseline(remote_client_env):
    """Pre-seed ``--document-json-dir`` with the record the upstream stages leave behind.

    Written by the real tools' writer (the OCR stage originates pages/lines under an
    `ABBYY-ALTO` origin, nlp-enrich adds entities) rather than hand-rolled, so the blocks
    this stage must preserve carry genuine ownership stamps. Asserted schema-valid here on
    purpose: an invalid baseline would demote the Layer D gate to a warning (D4) and quietly
    change what the tests using this fixture are measuring.
    """
    from atrium_document import DocumentRecord, load_document, validate_document

    env = remote_client_env
    with DocumentRecord(
        env.doc_id, "ocr-postprocess", run_id="R-OCR", out_dir=str(env.record_dir)
    ) as ocr:
        ocr.set_source(
            sha256="a" * 64,
            filename=f"{env.doc_id}.alto.xml",
            media_type="application/alto+xml",
            origin="ABBYY-ALTO",
            page_count=1,
        )
        ocr.merge_block("pages", [{"page": "1", "page_index": 1, "quality_score": 0.91}])
        ocr.merge_block(
            "lines",
            [
                {
                    "page": "1",
                    "line": 1,
                    "text": "Výzkum odhalil základy gotického kostela.",
                    "categ": "Clear",
                    "quality_score": 0.91,
                }
            ],
        )

    with DocumentRecord.open(
        env.doc_id, "nlp-enrich", baseline=str(env.baseline), out_dir=str(env.record_dir)
    ) as nlp:
        nlp.merge_block(
            "entities",
            [
                {
                    "page": "1",
                    "line": 1,
                    "char_span": [24, 41],
                    "surface": "gotického kostela",
                    "type_onto": "FAC",
                }
            ],
        )

    validate_document(load_document(str(env.baseline)))
    return env.baseline


@pytest.fixture
def stub_llm(monkeypatch):
    """Make a client module's inference offline. Call it with the module under test.

    Only ``make_chat_fn`` is replaced -- with a canned, schema-valid reply, so no HTTP happens
    and no API key or Ollama daemon is needed. Everything else is the real code: row reading,
    the line filter, the prompt, the ids, the record write, the accretion. The messages each
    call was sent are collected in the returned list.
    """
    sent: list = []

    def _install(client_module, category="kostel"):
        import json

        def fake_make_chat_fn(*_args, **_kwargs):
            def chat_fn(messages):
                sent.append(messages)
                return json.dumps(
                    {
                        "extracted_keywords_cs": ["kostel"],
                        "extracted_keywords_en": ["church"],
                        "teater_category": category,
                        "confidence_score": 0.9,
                    },
                    ensure_ascii=False,
                )

            return chat_fn

        monkeypatch.setattr(client_module, "make_chat_fn", fake_make_chat_fn)
        return sent

    return _install
