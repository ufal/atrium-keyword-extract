"""tests/test_dm_tree.py — the descent tree of #3 (decision models over the vocabulary, Option 4 of #2).

Built from the vocabulary files the repository ships, so it checks the real tree: every term
reachable exactly once, every question within the interface's 255 options, the chunking, the
geographic gate, the form terms withheld (atrium-project#83: a text-only model decides content, never
form), and a stable digest.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import dm_run  # noqa: E402
import prompt_template  # noqa: E402


@pytest.fixture(scope="module")
def tree():
    return dm_run.build_tree()


def _reachable_terms(tree):
    nodes, seen, stack = tree["nodes"], [], ["root"]
    while stack:
        node_id = stack.pop()
        if nodes[node_id]["kind"] == "term":
            seen.append(node_id)
        stack += nodes[node_id]["children"]
    return seen


def test_every_offered_term_is_reachable_exactly_once(tree):
    reached = _reachable_terms(tree)
    assert len(reached) == len(set(reached))
    term_nodes = [n for n, v in tree["nodes"].items() if v["kind"] == "term"]
    assert sorted(reached) == sorted(term_nodes)
    vocab = json.loads(dm_run.DEFAULT_INPUTS["vocabulary"].read_text(encoding="utf-8"))
    offered = prompt_template.vocabulary_terms(vocab, tree["excluded_themes"])
    withheld = tree["withheld_form"]["terms"]
    # all but the meta-text sentinel, which L0 answers, and the form terms
    assert len(term_nodes) == len(offered) - 1 - len(withheld)
    assert tree["sentinel"]["cs"] == prompt_template.META_TEXT_TERM["cs"]


def test_facets_and_groups_are_routing_levels_only(tree):
    nodes = tree["nodes"]
    for node in nodes.values():
        if node["kind"] in ("root", "facet"):
            assert all(nodes[c]["kind"] in ("facet", "group") for c in node["children"])
        if node["kind"] in ("group", "term"):
            assert all(nodes[c]["kind"] == "term" for c in node["children"])
    assert "Finds Context" in tree["stats"]["single_group_facets"]


def test_every_choice_fits_the_interface_and_loses_no_option(tree):
    nodes = tree["nodes"]
    for node_id, chunk, choice in dm_run.every_choice(tree):
        criteria = choice["criteria"]
        assert 2 <= len(criteria) <= dm_run.MAX_OPTIONS, (node_id, chunk, len(criteria))
        assert criteria and list(criteria)[-1] == dm_run.NONE_OF_THESE
        _, options = dm_run.node_options(tree, node_id, chunk)
        if chunk is None and "chunks" not in nodes[node_id]:
            extras = 2 if nodes[node_id]["kind"] == "term" else 1
            assert len(options) == len(nodes[node_id]["children"]) + extras
            assert len({o for o, _, _ in options}) == len(options)
        if nodes[node_id]["kind"] == "term" and chunk is None:
            assert dm_run.THIS_TERM in criteria


def test_only_the_node_over_the_limit_is_chunked_and_its_chunks_partition_it(tree):
    chunked = tree["stats"]["chunked_nodes"]
    assert chunked == ["t:Cultural & Geographic Context/historické oblasti a státní útvary"]
    node = tree["nodes"][chunked[0]]
    flat = [child for chunk in node["chunks"] for child in chunk]
    assert flat == node["children"]
    assert all(len(chunk) + 1 <= dm_run.MAX_OPTIONS for chunk in node["chunks"])
    sizes = [len(chunk) for chunk in node["chunks"]]
    assert max(sizes) - min(sizes) <= 1  # balanced


def test_the_geographic_gate_covers_what_the_config_names(tree):
    covers = tree["geo_guardrail"]["covers"]
    gated = tree["stats"]["geo_gated"]
    nodes = tree["nodes"]
    if "heslar:zeme" in covers:
        assert any(nodes[g]["kind"] == "group" for g in gated)
    for cover in (c for c in covers if c.startswith("teater:")):
        teater_id = cover.split(":", 1)[1]
        holders = [
            n
            for n, v in nodes.items()
            if v["kind"] == "term"
            and any(i["source"] == "teater" and str(i["id"]) == teater_id for i in v["ids"])
        ]
        assert all(n in gated for n in holders)
    assert tree["geo_guardrail"]["mode"] in prompt_template.GEO_GUARDRAIL_BLOCKS


def test_the_form_terms_and_their_subtrees_are_withheld(tree):
    withheld = tree["withheld_form"]
    assert withheld["teater_ids"] == dm_run.FORM_TERMS and withheld["absent"] == []
    teater = json.loads(
        (REPO_ROOT / "data_samples" / "vocab" / "teater_flat.json").read_text(encoding="utf-8")
    )["terms"]
    teater = list(teater.values()) if isinstance(teater, dict) else teater
    label = {str(t["source_id"]): t["cs"] for t in teater}
    broader = {str(t["source_id"]): [str(b) for b in t.get("broader") or []] for t in teater}
    for teater_id, cs in dm_run.FORM_TERMS.items():
        assert label[teater_id] == cs, teater_id  # the id still names the term it was chosen for
    nodes = tree["nodes"]
    for node in nodes.values():
        for ident in node.get("ids", []):
            if ident["source"] == "teater":
                lineage = {str(ident["id"]), *broader.get(str(ident["id"]), [])}
                assert not lineage & set(dm_run.FORM_TERMS), node["cs"]
    assert all(term not in nodes for term in withheld["terms"])
    assert {"t:Methods/fotografická dokumentace", "t:Methods/nálezová správa"} <= set(
        withheld["terms"]
    )
    # scripts studied as finds, written artefacts and aerial methods stay content
    assert "g:Related Disciplines & Society/písmo" in nodes and "g:Artefact/písemnost" in nodes
    assert "t:Methods/letecké snímkování" in nodes
    assert tree["stats"]["withheld_form_terms"] == len(withheld["terms"]) == 22


def test_question_wording_comes_from_the_prompt_blocks(tree):
    blocks = prompt_template.load_blocks()
    assert tree["questions"]["L0_content"]["criteria"]["false"] == blocks["rule.metatext"].strip()
    assert (
        tree["questions"]["L1g_geographic"]["criteria"]["true"]
        == blocks["guardrail.geographic.preference"].strip()
    )


def test_the_digest_is_stable_and_covers_the_tree(tree):
    again = dm_run.build_tree()
    assert again["digest"] == tree["digest"] == dm_run.tree_digest(tree)
    changed = json.loads(json.dumps(tree))
    changed["nodes"]["root"]["children"] = changed["nodes"]["root"]["children"][::-1]
    assert dm_run.tree_digest(changed) != tree["digest"]
    assert set(tree["inputs"]) >= {
        "vocabulary",
        "specificity_pairs",
        "amcr_flat",
        "taxonomy_config",
    }


def test_the_stats_describe_the_tree(tree):
    stats = tree["stats"]
    assert stats["terms"] == sum(1 for v in tree["nodes"].values() if v["kind"] == "term")
    assert stats["longest_parent_chain"] == stats["deepest_term_level"] - 1
    assert stats["max_options_per_choice"] <= dm_run.MAX_OPTIONS
    assert stats["parent_edges"].get("cycles_broken", 0) == 0


def test_czech_alphabetical_order():
    words = ["žába", "chata", "rak", "cihla", "řeka", "hrad", "čáp", "zámek", "áčko", "azyl"]
    assert sorted(words, key=dm_run.czech_key) == [
        "áčko",
        "azyl",
        "cihla",
        "čáp",
        "hrad",
        "chata",
        "rak",
        "řeka",
        "zámek",
        "žába",
    ]


def test_cli(tmp_path, capsys):
    out = tmp_path / "tree.json"
    assert dm_run.main(["--dump-tree", str(out)]) == 0
    dumped = json.loads(out.read_text(encoding="utf-8"))
    assert dumped["format"] == dm_run.TREE_FORMAT and dumped["digest"] == dm_run.tree_digest(dumped)
    assert dm_run.main(["--lines"]) == 2
