"""
tests/test_cli_service_parity.py
================================
``keywords.py`` and ``POST /extract_keywords`` read the same inputs and give the same keywords
(atrium-project#72, the service–CLI alignment of 2026-10-26).

Since v1.5.0-beta both read through ``kw_inputs.py``: the command line takes the record, a line
table and plain text besides CoNLL-U and TEITOK; the service takes CoNLL-U, TEITOK, a line table
and plain text as ``file`` besides the record. ``--per-page`` is ``per_page``, and
``--document-json-out-dir`` writes the record's ``keywords`` block through the service's writer.
YAKE runs for real; nothing here needs a model download.

Kept apart on purpose, and pinned: KER over an input without lemmas (the service refuses it,
the command line writes an empty row), and the paradata (a file on the command line, a
``CreateAction`` in the response; hub #71).
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("yake")

from fastapi.testclient import TestClient  # noqa: E402

import keywords  # noqa: E402
from service import api  # noqa: E402

client = TestClient(api.app)
REPO = Path(__file__).resolve().parent.parent
CONLLU = REPO / "data_samples" / "UDP" / "CTX000000001.conllu"

RECORD = {
    "schema_version": "1.0",
    "record_type": "atrium-document",
    "doc_id": "CTX000000009",
    "pages": [{"page": "1", "page_index": 1}, {"page": "iv", "page_index": 2}],
    "lines": [
        {
            "page": "1",
            "line": 1,
            "text": "Výzkum odhalil základy gotického kostela u hradiště.",
            "categ": "Clear",
        },
        {"page": "1", "line": 2, "text": "garbage ~~ ##", "categ": "Trash"},
        {
            "page": "iv",
            "line": 1,
            "text": "Zámek nad řekou, v příkopu nalezena středověká keramika.",
            "categ": "Clear",
        },
        {
            "page": "iv",
            "line": 2,
            "text": "Keramika z příkopu a základy kostela.",
            "categ": "Clear",
        },
    ],
}

TEITOK = """<?xml version="1.0" encoding="utf-8"?>
<TEI><teiHeader/><text>
<pb n="1"/><p><lb/><tok lemma="výzkum" upos="NOUN">Výzkum</tok> <tok lemma="hradiště" upos="NOUN">hradiště</tok>
<lb/><tok lemma="gotický" upos="ADJ">gotického</tok> <tok lemma="kostel" upos="NOUN">kostela</tok></p>
<pb n="2"/><p><lb/><tok lemma="středověký" upos="ADJ">Středověká</tok> <tok lemma="keramika" upos="NOUN">keramika</tok>
<lb/><tok lemma="keramika" upos="NOUN">keramika</tok> <tok lemma="příkop" upos="NOUN">příkopu</tok></p>
</text></TEI>
"""

TABLE = (
    "file,page_num,line_num,text,categ\n"
    "CTX8,1,1,Výzkum odhalil základy gotického kostela u hradiště.,Clear\n"
    "CTX8,1,2,x#@ ~~ %%,Trash\n"
    "CTX8,2,1,V příkopu nalezena středověká keramika.,Clear\n"
)

TEXT = "Výzkum odhalil základy gotického kostela.\fV příkopu nalezena středověká keramika a mazanice.\n"


def _inputs(tmp_path: Path) -> Path:
    folder = tmp_path / "in"
    folder.mkdir()
    shutil.copy(CONLLU, folder / CONLLU.name)
    (folder / "CTX000000009.document.json").write_text(
        json.dumps(RECORD, ensure_ascii=False), encoding="utf-8"
    )
    (folder / "CTX7.teitok.xml").write_text(TEITOK, encoding="utf-8")
    (folder / "CTX8.csv").write_text(TABLE, encoding="utf-8")
    (folder / "CTX6.txt").write_text(TEXT, encoding="utf-8")
    return folder


def _cli(tmp_path: Path, method: str = "yake", *extra: str) -> Path:
    out = tmp_path / "out"
    args = [
        "-i",
        str(_inputs(tmp_path)),
        "-o",
        str(out / "summary.csv"),
        "-d",
        str(out / "per_doc"),
        "-p",
        str(out / "per_page"),
        "--paradata-dir",
        str(out / "paradata"),
        "-m",
        method,
        "-n",
        "8",
        "--workers",
        "1",
        "--per-page",
        "--document-json-out-dir",
        str(out / "records"),
        *extra,
    ]
    out.mkdir(parents=True, exist_ok=True)
    keywords.main(args)
    return out


def _read(path: Path) -> list:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _service(name: str, data: bytes, method: str = "yake", **form) -> dict:
    files = {"file": (name, data, "application/octet-stream")}
    fields = {
        "kind": "statistical",
        "method": method,
        "num_keywords": "8",
        "per_page": "true",
        **form,
    }
    response = client.post("/extract_keywords", files=files, data=fields)
    assert response.status_code == 200, response.text
    return response.json()


def _pairs(entries) -> list:
    return [(e["keyword"], round(float(e["score"]), 6)) for e in entries]


@pytest.fixture(scope="module")
def cli_out(tmp_path_factory):
    return _cli(tmp_path_factory.mktemp("kw"))


@pytest.mark.parametrize(
    "name, doc_id",
    [
        ("CTX000000001.conllu", "CTX000000001"),
        ("CTX7.teitok.xml", "CTX7"),
        ("CTX8.csv", "CTX8"),
        ("CTX6.txt", "CTX6"),
    ],
)
def test_a_file_gives_the_same_keywords_on_both_sides(cli_out, name, doc_id):
    data = (cli_out.parent / "in" / name).read_bytes()
    body = _service(name, data)
    cli_doc = [
        (r["keyword"], round(float(r["score"]), 6))
        for r in _read(cli_out / "per_doc" / f"{doc_id}_keywords.csv")
    ]
    assert cli_doc == _pairs(body["keywords"])
    per_page = cli_out / "per_page" / f"{doc_id}_keywords.csv"
    cli_pages: dict = {}
    if per_page.exists():
        for r in _read(per_page):
            cli_pages.setdefault(r["page"], []).append((r["keyword"], round(float(r["score"]), 6)))
    assert cli_pages == {p["page"]: _pairs(p["keywords"]) for p in body["pages"] if p["keywords"]}


def test_pages_come_from_the_input(cli_out):
    assert _service("CTX7.teitok.xml", TEITOK.encode())["pages"][1]["page"] == "2"
    assert [p["page"] for p in _service("CTX8.csv", TABLE.encode())["pages"]] == ["1", "2"]
    assert [p["page"] for p in _service("CTX6.txt", TEXT.encode())["pages"]] == ["1", "2"]
    conllu = _service("CTX000000001.conllu", CONLLU.read_bytes())
    assert conllu["pages"] == [], "CoNLL-U carries no pages"


def test_the_record_gives_the_same_keywords_and_block_on_both_sides(cli_out):
    data = json.dumps(RECORD, ensure_ascii=False).encode("utf-8")
    response = client.post(
        "/extract_keywords",
        files={"document_json": ("r.document.json", data, "application/json")},
        data={"kind": "statistical", "method": "yake", "num_keywords": "8", "per_page": "true"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    cli_record = json.loads(
        (cli_out / "records" / "CTX000000009.document.json").read_text(encoding="utf-8")
    )
    service_block = body["document_json"]["keywords"]
    for key in ("document", "pages"):
        assert cli_record["keywords"][key] == service_block[key], key
    assert _pairs(service_block["document"]) == _pairs(body["keywords"])
    # every other block passes through on both sides
    assert cli_record["lines"] == body["document_json"]["lines"] == RECORD["lines"]


def test_a_file_and_a_record_together_write_the_files_keywords_into_the_record():
    record = {"schema_version": "1.0", "record_type": "atrium-document", "doc_id": "CTX7"}
    response = client.post(
        "/extract_keywords",
        files={
            "file": ("CTX7.teitok.xml", TEITOK.encode(), "application/xml"),
            "document_json": ("r.document.json", json.dumps(record).encode(), "application/json"),
        },
        data={"kind": "statistical", "method": "yake", "num_keywords": "5"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["doc_id"] == "CTX7"
    assert _pairs(body["document_json"]["keywords"]["document"]) == _pairs(body["keywords"])
    assert [e["name"] for e in body["paradata"]["object"]] == ["CTX7.teitok.xml", "r.document.json"]


def test_ker_reads_the_same_lemmas_on_both_sides(tmp_path):
    out = _cli(tmp_path, "legacy")
    for name, doc_id in (("CTX000000001.conllu", "CTX000000001"), ("CTX7.teitok.xml", "CTX7")):
        body = _service(name, (out.parent / "in" / name).read_bytes(), method="legacy")
        cli_doc = [
            (r["keyword"], round(float(r["score"]), 6))
            for r in _read(out / "per_doc" / f"{doc_id}_keywords.csv")
        ]
        assert cli_doc == _pairs(body["keywords"]) != []


def test_ker_without_lemmas_is_refused_by_the_service_and_empty_on_the_cli(tmp_path):
    """Kept apart on purpose: a batch run goes on with an empty row; a call is told why it got
    nothing (docs/usage.md, "The command line and the service")."""
    out = _cli(tmp_path, "legacy")
    summary = {r["document_id"]: r for r in _read(out / "summary.csv")}
    assert summary["CTX6"]["kw-1"] == ""
    response = client.post(
        "/extract_keywords",
        files={"file": ("CTX6.txt", TEXT.encode(), "text/plain")},
        data={"kind": "statistical", "method": "legacy"},
    )
    assert response.status_code == 422
    assert "lemmas" in response.json()["detail"]


def test_both_refuse_what_they_do_not_read(tmp_path):
    response = client.post(
        "/extract_keywords",
        files={"file": ("scan.pdf", b"%PDF-1.7", "application/pdf")},
        data={"kind": "statistical", "method": "yake"},
    )
    assert response.status_code == 415
    folder = tmp_path / "in"
    folder.mkdir()
    (folder / "scan.pdf").write_bytes(b"%PDF-1.7")
    (folder / "notes.md").write_text("# not read", encoding="utf-8")
    out = tmp_path / "out"
    keywords.main(
        [
            "-i",
            str(folder),
            "-o",
            str(out / "s.csv"),
            "-d",
            str(out / "d"),
            "--paradata-dir",
            str(out / "p"),
            "-m",
            "yake",
            "--workers",
            "1",
        ]
    )
    assert _read(out / "s.csv") == []


def test_nothing_sent_is_a_422():
    assert client.post("/extract_keywords", data={"kind": "statistical"}).status_code == 422


def test_paradata_is_keyword_extracts_own_file_on_the_cli(cli_out):
    (written,) = list((cli_out / "paradata").glob("*.json"))
    record = json.loads(written.read_text(encoding="utf-8"))
    assert record["program"] == "keyword-extract"
    assert written.name.endswith("_keyword-extract.json")
