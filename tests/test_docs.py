"""
tests/test_docs.py — the documentation's checkable claims (issue #6).

Prose goes stale silently. Most of it can only be kept honest by reading it, but a
useful slice is mechanical: a link either resolves or it does not, a file either exists
or it does not, and a count either matches the code or it does not. Those are here.

The provoking case: `README.md`, `CONTRIBUTING.md` and `data_samples/vocab/RUNBOOK.md`
all linked to `prompts/RUNBOOK.md` — in a table of contents, in a config comment, and in
a "which document is for whom" table — while the file did not exist. Three documents
promised a fourth into being and nothing noticed, because no test reads a link.

Deliberately narrow. This module asserts what a reader can verify without judgement;
whether the prose is *right* is a review question, not a test.
"""

import re
from pathlib import Path

import pytest

import prompt_template as pt

REPO_ROOT = Path(__file__).resolve().parent.parent

# The documents a reviewer or contributor is pointed at. Not every .md in the tree:
# agent_dev_logs/ is a working record that cites moved and deleted files on purpose.
DOCS = [
    "README.md",
    "CONTRIBUTING.md",
    "prompts/RUNBOOK.md",
    "data_samples/vocab/RUNBOOK.md",
    "data_samples/vocab/6.O3O4.decision-package.md",
    "data_samples/vocab/6.D-eval.decision-package.md",
    "service/README.md",
]

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


# ── links ────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("doc", DOCS)
def test_every_referenced_document_exists(doc):
    """The documents this project points contributors at must be present. A missing one
    is not a broken link in the ordinary sense — it is a promise in a table of contents
    that nobody can follow."""
    assert (REPO_ROOT / doc).exists(), f"{doc} is referenced by the doc set but missing"


@pytest.mark.parametrize("doc", DOCS)
def test_relative_links_resolve(doc):
    path = REPO_ROOT / doc
    if not path.exists():
        pytest.skip(f"{doc} absent")
    broken = []
    for target in LINK_RE.findall(path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        resolved = (path.parent / target.split("#")[0]).resolve()
        if not resolved.exists():
            broken.append(target)
    assert not broken, f"{doc} links to files that do not exist: {sorted(set(broken))}"


def test_the_two_runbooks_point_at_each_other():
    """They split one workflow — the term list and the prompt it goes into — so each has
    to say where the other half is documented, or a reader lands in the wrong one."""
    vocab = (REPO_ROOT / "data_samples" / "vocab" / "RUNBOOK.md").read_text(encoding="utf-8")
    prompts = (REPO_ROOT / "prompts" / "RUNBOOK.md").read_text(encoding="utf-8")
    assert "prompts/RUNBOOK.md" in vocab
    assert "data_samples/vocab/RUNBOOK.md" in prompts


# ── counts the docs assert about the code ────────────────────────────────────────


def _prompt_runbook():
    return (REPO_ROOT / "prompts" / "RUNBOOK.md").read_text(encoding="utf-8")


def _markdown_table(doc: str, first_header: str):
    """Rows of the first table whose header column starts with ``first_header``, as lists
    of stripped cells. Written out rather than regexed per-row because the runbook's
    tables are hand-aligned and their padding is not uniform."""
    lines = doc.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("|") and line.split("|")[1].strip() == first_header:
            rows = []
            for row in lines[i + 2 :]:
                if not row.startswith("|"):
                    break
                rows.append([c.strip() for c in row.strip("|").split("|")])
            return rows
    raise AssertionError(f"no table with a {first_header!r} column")


def test_the_prompt_runbook_names_every_block_and_no_others():
    """A block added to the template without a runbook row is undocumented; a row for a
    block that no longer exists sends a reviewer looking for wording that is gone."""
    rows = _markdown_table(_prompt_runbook(), "Block")
    documented = {cells[0].strip("`") for cells in rows}
    blocks = set(pt.load_blocks())
    assert documented == blocks, (
        f"undocumented: {sorted(blocks - documented)}; "
        f"documented but absent from the template: {sorted(documented - blocks)}"
    )


def test_the_prompt_runbook_gates_each_block_by_its_real_flag():
    """The row must name the flag that actually controls the block, not a plausible one —
    the table is what a reviewer edits `llm_config.txt` from."""
    rows = _markdown_table(_prompt_runbook(), "Block")
    for cells in rows:
        block, flag = cells[0].strip("`"), cells[1].strip("`*")
        if block in pt.REQUIRED_BLOCKS:
            assert flag == "always", f"{block} always renders; the table says {flag!r}"
        elif block in pt.GEO_GUARDRAIL_BLOCKS.values():
            assert flag == pt.GEO_GUARDRAIL_FLAG
        else:
            assert flag == pt.BLOCK_FLAGS[block], f"{block} is gated by {pt.BLOCK_FLAGS[block]}"


def test_the_prompt_runbook_names_every_prompt_flag():
    doc = _prompt_runbook()
    flags = {pt.TEMPLATE_PATH_FLAG, pt.GEO_GUARDRAIL_FLAG, pt.GROUPING_FLAG} | set(
        pt.BLOCK_FLAGS.values()
    )
    missing = sorted(f for f in flags if f not in doc)
    assert not missing, f"prompts/RUNBOOK.md does not mention {missing}"


def test_the_documented_flag_count_matches_the_flags_that_exist():
    """The runbook and README both say "nine". If a tenth is added, both sentences become
    wrong in a way no reader can catch."""
    flags = {pt.TEMPLATE_PATH_FLAG, pt.GEO_GUARDRAIL_FLAG, pt.GROUPING_FLAG} | set(
        pt.BLOCK_FLAGS.values()
    )
    assert len(flags) == 9, (
        f"{len(flags)} PROMPT_* flags now exist — update the count in prompts/RUNBOOK.md "
        "and README.md, which both say nine"
    )
    assert "The nine flags" in _prompt_runbook()


def test_the_documented_grouping_modes_are_the_modes_that_exist():
    doc = _prompt_runbook()
    for mode in pt.GROUPING_MODES:
        assert f"`{mode}`" in doc, f"grouping mode {mode} is undocumented"


def test_the_shipped_config_states_every_flag_the_docs_describe():
    """A flag documented but absent from `llm_config.txt` runs on its code default, which
    is how `PROMPT_GEO_GUARDRAIL` could silently revert to `strict` after M11 relaxed it."""
    config = pt.load_run_config(REPO_ROOT / "llm_config.txt")
    flags = {pt.TEMPLATE_PATH_FLAG, pt.GEO_GUARDRAIL_FLAG, pt.GROUPING_FLAG} | set(
        pt.BLOCK_FLAGS.values()
    )
    missing = sorted(f for f in flags if f not in config)
    assert not missing, f"llm_config.txt does not state {missing}"


def test_the_vocabulary_runbook_counts_its_own_directory_correctly():
    """ "25 files" was right for one build and wrong for the next. The claim is cheap to
    keep true and misleading when it is not."""
    doc = (REPO_ROOT / "data_samples" / "vocab" / "RUNBOOK.md").read_text(encoding="utf-8")
    claim = re.search(r"^(\d+) files, three kinds", doc, re.MULTILINE)
    if claim is None:
        pytest.skip("the file-count sentence has been reworded")
    actual = len([p for p in (REPO_ROOT / "data_samples" / "vocab").iterdir() if p.is_file()])
    assert int(claim.group(1)) == actual, (
        f"RUNBOOK.md says {claim.group(1)} files, the directory holds {actual}"
    )


def test_the_vocabulary_runbook_lists_every_review_sheet_flag():
    """Each `vocab_review.py` sheet must appear in the runbook's command block, or a
    reviewer never learns the sheet exists."""
    import vocab_review as vr

    doc = (REPO_ROOT / "data_samples" / "vocab" / "RUNBOOK.md").read_text(encoding="utf-8")
    parser = vr.build_parser()
    # --all and the three path options are plumbing, not sheets.
    plumbing = {"--help", "--all", "--vocab-dir", "--config", "--overrides"}
    sheet_flags = [
        option
        for action in parser._actions
        for option in action.option_strings
        if option.startswith("--") and option not in plumbing
    ]
    assert len(sheet_flags) == 8, f"{len(sheet_flags)} sheets now — the runbook says eight"
    missing = sorted(f for f in sheet_flags if f not in doc)
    assert not missing, f"data_samples/vocab/RUNBOOK.md does not document {missing}"
