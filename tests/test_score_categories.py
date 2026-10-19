"""
tests/test_score_categories.py — score_categories.py, the issue #2 scorer.

Small fixture runs for the arithmetic, and the committed runs for the numbers the
2026-10-16 comment reported by hand (missing lines, the forced capital labels).
"""

import csv
import json
from pathlib import Path

import pytest

import llm_client_shared as lcs
import score_categories as sc

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES = REPO_ROOT / "data_samples"
CONFIG = {"INCLUDE_NON_TEXT": "true", "MIN_CHAR_COUNT": "3", "MIN_CHAR_NON_TEXT": "8"}

_WORKBOOK_COLUMNS = [
    "file_id",
    "page",
    "line",
    "original_text",
    "categ",
    "quality_score",
    "gold_category",
]


def _workbook(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_WORKBOOK_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in _WORKBOOK_COLUMNS})
    return path


def _record(line, category, text="Hrob s nádobou.", keywords=(), confidence=0.9):
    return {
        "file_id": "CTX1",
        "page": 1,
        "line": line,
        "original_text": text,
        "enrichment": {
            "extracted_keywords_cs": list(keywords),
            "extracted_keywords_en": [],
            "teater_category": category,
            "confidence_score": confidence,
        },
    }


def _run(root, name, records):
    folder = root / name
    folder.mkdir()
    (folder / "CTX1_enriched.json").write_text(
        json.dumps(records, ensure_ascii=False), encoding="utf-8"
    )
    return folder


@pytest.fixture
def toy(tmp_path):
    workbook = _workbook(
        tmp_path / "gold_workbook.csv",
        [
            {
                "file_id": "CTX1",
                "page": "1",
                "line": "1",
                "original_text": "Hrob s nádobou.",
                "categ": "Clear",
                "quality_score": "0.9",
            },
            {
                "file_id": "CTX1",
                "page": "1",
                "line": "2",
                "original_text": "Artefakt z bronzu.",
                "categ": "Clear",
                "quality_score": "0.9",
                "gold_category": "artefakt",
            },
            {
                "file_id": "CTX1",
                "page": "1",
                "line": "3",
                "original_text": "Zpráva z roku 1956.",
                "categ": "Clear",
                "quality_score": "0.9",
            },
            # The quality filter drops it, so no run owes it.
            {
                "file_id": "CTX1",
                "page": "1",
                "line": "4",
                "original_text": "#~%",
                "categ": "Trash",
                "quality_score": "0.1",
            },
        ],
    )
    before = _run(
        tmp_path,
        "KW_PER_DOC_LLM_m",
        [
            _record(1, "hrob", keywords=["hrob"], confidence=0.95),
            _record(
                2, "Artemísion", text="Artefakt z bronzu.", keywords=["artefakt"], confidence=0.95
            ),
            _record(3, lcs.META_TERM, text="Zpráva z roku 1956.", confidence=1.0),
        ],
    )
    after = _run(
        tmp_path,
        "KW_PER_DOC_LLM_R3_m",
        [
            _record(1, "hrob", keywords=["hrob"], confidence=0.85),
            _record(
                2, "artefakt", text="Artefakt z bronzu.", keywords=["artefakt"], confidence=0.6
            ),
        ],
    )
    return workbook, before, after


def test_coverage_is_counted_from_the_expected_lines(toy):
    workbook, before, after = toy
    result = sc.score([before, after], workbook, CONFIG)
    rows = {row["run"]: row for row in result["runs"]}
    assert rows["KW_PER_DOC_LLM_m"]["expected"] == 3
    assert rows["KW_PER_DOC_LLM_m"]["missing"] == 0
    # A failed line is absent from the output: counted from the workbook, not the output.
    assert rows["KW_PER_DOC_LLM_R3_m"]["missing"] == 1
    assert rows["KW_PER_DOC_LLM_m"]["meta"] == 1


def test_a_capitalised_label_with_no_word_of_its_line_is_forced(toy):
    workbook, before, after = toy
    result = sc.score([before, after], workbook, CONFIG)
    rows = {row["run"]: row for row in result["runs"]}
    assert rows["KW_PER_DOC_LLM_m"]["forced_capital"] == 1
    assert rows["KW_PER_DOC_LLM_m"]["forced_capital_top"] == "Artemísion 1"
    assert rows["KW_PER_DOC_LLM_m"]["watch_hits"] == 1
    assert rows["KW_PER_DOC_LLM_R3_m"]["forced_capital"] == 0
    assert [(r["run"], r["line"], r["reason"]) for r in result["forced"]] == [
        ("KW_PER_DOC_LLM_m", 2, "capital")
    ]


def test_the_report_never_carries_a_lines_text(toy):
    workbook, before, after = toy
    result = sc.score([before, after], workbook, CONFIG)
    flat = (
        json.dumps({k: v for k, v in result.items() if k != "report"}, ensure_ascii=False)
        + result["report"]
    )
    for text in ("Hrob s nádobou", "Artefakt z bronzu", "Zpráva z roku"):
        assert text not in flat


def test_a_rerun_is_set_against_its_baseline(toy):
    workbook, before, after = toy
    assert sc.baseline_name("KW_PER_DOC_LLM_R3_qwen_38_27b_it") == "KW_PER_DOC_LLM_qwen_38_27b_it"
    assert sc.baseline_name("KW_PER_DOC_LLM_qwen_38_27b_it") is None
    result = sc.score([before, after], workbook, CONFIG)
    (row,) = result["before_after"]
    assert (row["run"], row["baseline"]) == ("KW_PER_DOC_LLM_R3_m", "KW_PER_DOC_LLM_m")
    assert (row["forced_capital_before"], row["forced_capital_after"]) == (1, 0)
    assert row["lines_changed"] == 1
    assert row["content_agreement"] == 0.5


def test_gold_accuracy_only_where_gold_is_filled(toy):
    workbook, before, after = toy
    result = sc.score([before, after], workbook, CONFIG)
    rows = {row["run"]: row for row in result["runs"]}
    assert (rows["KW_PER_DOC_LLM_m"]["gold_lines"], rows["KW_PER_DOC_LLM_m"]["gold_accuracy"]) == (
        1,
        0.0,
    )
    assert rows["KW_PER_DOC_LLM_R3_m"]["gold_accuracy"] == 1.0
    assert "1 lines carry a `gold_category`" in result["report"]


def test_agreement_counts_lines_both_call_content(toy):
    workbook, before, after = toy
    (row,) = sc.score([before, after], workbook, CONFIG)["agreement"]
    assert (row["both_content"], row["same"]) == (2, 1)


def test_the_cli_refuses_what_it_cannot_score(tmp_path, capsys):
    code = sc.main(
        [
            "--runs",
            str(tmp_path / "nope"),
            "--workbook",
            str(tmp_path / "missing.csv"),
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert code == sc.EXIT_USAGE
    err = capsys.readouterr().err
    assert "does not exist" in err and "corpus_review.py --gold-workbook" in err


def test_the_cli_writes_the_report(toy, tmp_path):
    workbook, before, after = toy
    out = tmp_path / "out"
    config = tmp_path / "llm_config.txt"
    config.write_text("MIN_CHAR_COUNT=3\n", encoding="utf-8")
    code = sc.main(
        [
            "--runs",
            str(before),
            str(after),
            "--workbook",
            str(workbook),
            "--config",
            str(config),
            "--out",
            str(out),
        ]
    )
    assert code == 0
    assert {p.name for p in out.iterdir()} == {
        "report.md",
        "runs.csv",
        "agreement.csv",
        "forced_labels.csv",
        "before_after.csv",
    }


# ── the committed runs: the 2026-10-16 numbers ───────────────────────────────────


@pytest.fixture(scope="module")
def committed():
    # The 17 runs of 12–13 October; a later re-run (`KW_PER_DOC_LLM_R3_*`) has its own numbers.
    runs = sorted(
        p
        for p in SAMPLES.glob("KW_PER_DOC_LLM_*")
        if p.is_dir() and sc.baseline_name(p.name) is None
    )
    if not runs or not (SAMPLES / "vocab" / "gold_workbook.csv").is_file():
        pytest.skip("the committed runs or gold_workbook.csv are not in this checkout")
    import prompt_template

    config = prompt_template.load_run_config(REPO_ROOT / "llm_config.txt")
    result = sc.score(runs, SAMPLES / "vocab" / "gold_workbook.csv", config)
    return {row["run"]: row for row in result["runs"]}


def test_the_committed_runs_owe_1029_lines_and_miss_what_the_review_found(committed):
    assert {row["expected"] for row in committed.values()} == {1029}
    missing = {name: row["missing"] for name, row in committed.items() if row["missing"]}
    assert missing == {
        "KW_PER_DOC_LLM_granite_41_8b": 71,
        "KW_PER_DOC_LLM_granite_41_30b": 15,
        "KW_PER_DOC_LLM_qwen_35_9b_it": 3,
    }


@pytest.mark.parametrize(
    "run,forced",
    [
        ("gemma_3_12b_it", 94),
        ("qwen_35_9b_it", 90),
        ("gemma_4_31b_it", 64),
        ("qwen3_8b", 49),
        ("qwen_35_35b_moe_gptq", 27),
        ("gemma_4_12b_it", 13),
        ("gemma_4_12b_it_qat", 13),
        ("gemma_4_31b_it_qat", 13),
        ("granite_41_30b", 4),
        ("qwen3_14b", 4),
    ],
)
def test_the_committed_runs_reproduce_the_forced_capital_table(committed, run, forced):
    assert committed[f"KW_PER_DOC_LLM_{run}"]["forced_capital"] == forced
