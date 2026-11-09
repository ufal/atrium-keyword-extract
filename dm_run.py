#!/usr/bin/env python3
"""dm_run.py — decision models over the controlled vocabulary (#3, Option 4 of #2; ufal/atrium-project#83).

A decision model cannot read the whole vocabulary at once (4,711 terms; at most 255 options per
``choice``), so it walks down it: is the line content at all (L0), which facet (L1), the geographic
gate where the guardrail covers the branch (L1g), which group (L2), then down the terms' own tree
(L3…), with ``<this term>`` where a node is itself a term and ``none_of_these`` at every step. An
answer is therefore always a vocabulary term or "unresolved" (#2's ruling D2).

This file builds that tree. ``--dump-tree OUT`` writes it as JSON with its digest. The digest goes
into every run's paradata, so a vocabulary change shows in the runs. Line mode (the descent's
requests) is not written yet.

**Content only.** This repository reads text and never an image, so its decision models decide what
a document is *about*: a term of the content vocabulary, or meta-text. What a document *is* (its
form: a report, a photograph, a plan, a map) is decided from page images, by atrium-digital-convert
and atrium-page-classification (ufal/atrium-project#83, "Form and content"). AMČR's form lists
(``dokument_typ``, ``dokument_material``, ``dokument_format`` …) are already withheld from the
vocabulary (``taxonomy_config.json``). A few TEATER terms inside content facets still name a kind
of record (photographs, drawings, maps, the documentation, the site report), and a line naming one
is mostly a caption or a reference to the archive's own documentation: those terms and their
subtrees are withheld from the tree (``FORM_TERMS``), never from the vocabulary or the generative
prompt. The tree records them under ``withheld_form``.

How the tree is made, from files the vocabulary build already writes:

* **Terms, facets, groups:** ``prompt_template.vocabulary_terms()`` over ``data_samples/vocab/
  union_nested.json``, without the themes ``llm_client_shared.excluded_prompt_themes()`` withholds:
  the same terms the generative prompt offers. Facets and groups are routing levels only (P2), never
  an answer.
* **A term's parent** is its nearest ancestor that the union offers in the same facet. For TEATER
  terms it comes from ``data_samples/vocab/specificity_pairs.csv`` (``nearest_ancestor_id``, rows
  with ``same_facet``). For AMČR terms it is the first ``broader`` id of ``amcr_flat.json`` that
  the union offers in that facet, which links a ``*_druh`` term to its ``*_kat`` category. A term
  with no offered ancestor hangs from its group. An ancestor in another group of the facet pulls the
  term into that group's subtree. A group left with no terms of its own is dropped.
* **Form terms** (``FORM_TERMS``, TEATER ids) are withheld with everything below them, after the
  parents are found. A group left with none of its terms is not offered.
* **The geographic gate** marks the branches ``taxonomy_config.json`` ``_settings.geo_guardrail.covers``
  names (``heslar:<scheme>`` — the groups built from that AMČR heslář; ``teater:<id>`` — that term).
* **Chunks:** a node with more options than a ``choice`` takes is split, in Czech alphabetical order,
  into balanced chunks. Each chunk is asked with ``none_of_these``, then one ``choice`` is asked among
  the chunk winners. Chunks are plumbing and are never emitted (P1).

Run it from the repository root::

    python3 dm_run.py --dump-tree /tmp/dm_tree.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent
VOCAB = REPO_ROOT / "data_samples" / "vocab"
DEFAULT_INPUTS = {
    "vocabulary": VOCAB / "union_nested.json",
    "vocabulary_meta": VOCAB / "union_nested.meta.json",
    "specificity_pairs": VOCAB / "specificity_pairs.csv",
    "amcr_flat": VOCAB / "amcr_flat.json",
    "taxonomy_config": REPO_ROOT / "data_samples" / "taxonomy_config.json",
    "llm_config": REPO_ROOT / "llm_config.txt",
    "prompt_blocks": REPO_ROOT / "prompts" / "system_prompt.txt",
}

TREE_FORMAT = "atrium-dm-tree/1"
MAX_OPTIONS = 255  # a Jev/SystemOne choice
THIS_TERM = "<this term>"
NONE_OF_THESE = "none_of_these"
RESERVED = (THIS_TERM, NONE_OF_THESE)

#: TEATER terms that name a kind of record rather than what a document is about: withheld, with
#: their subtrees, from the tree a text-only model descends (ufal/atrium-project#83). Form is read
#: from images; the document types themselves are AMČR's ``dokument_typ``, asked by
#: atrium-digital-convert. Kept as content on purpose: 3567 ``písmo`` (scripts studied as finds),
#: 2181 ``písemnost`` (written artefacts and historical sources), 229 ``muzejní dokumentace``,
#: 462 ``grafická technika``, 4158 ``mentální mapa``, and the methods 122 ``letecká fotogrammetrie``
#: and 126 ``letecké snímkování`` (activities, not records).
FORM_TERMS: Dict[str, str] = {
    "195": "dokumentace",  # fieldwork documentation and its 8 kinds (photo, drawn, map, video …)
    "252": "nálezová správa",  # the site report, AMČR's nálezová zpráva
    "461": "fotografie",
    "465": "kresba",
    "917": "geologická mapa",
    "1011": "hydrologická mapa",
    "1030": "dějepisná mapa",
    "1031": "stará mapa",
    "1033": "katastrální mapa",
    "1042": "vlastivědná mapa",
    "3564": "distribuční mapa",
    "124": "digitální model terénu",  # remote-sensing products, beside AMČR's data types
    "125": "ortofotomapa",
    "131": "satelitní snímek",
}

#: Czech alphabetical order (ČSN 97 6030, primary level): č, ř, š, ž and "ch" are letters of their
#: own; the acute, the ring and ď/ť/ň's caron only break ties.
_CZ_LETTERS = "a b c č d e f g h ch i j k l m n o p q r ř s š t u v w x y z ž".split()
_CZ_RANK = {letter: rank for rank, letter in enumerate(_CZ_LETTERS)}
_CZ_SECONDARY = {
    "á": "a",
    "é": "e",
    "ě": "e",
    "í": "i",
    "ó": "o",
    "ú": "u",
    "ů": "u",
    "ý": "y",
    "ď": "d",
    "ť": "t",
    "ň": "n",
}


def czech_key(text: str) -> Tuple:
    """A sort key in Czech alphabetical order (case-insensitive; digits and others after letters)."""
    s = text.lower()
    primary: List[Tuple[int, str]] = []
    secondary: List[int] = []
    i = 0
    while i < len(s):
        if s.startswith("ch", i):
            primary.append((0, f"{_CZ_RANK['ch']:03d}"))
            secondary.append(0)
            i += 2
            continue
        ch = s[i]
        base = _CZ_SECONDARY.get(ch, ch)
        if base in _CZ_RANK:
            primary.append((0, f"{_CZ_RANK[base]:03d}"))
            secondary.append(0 if base == ch else 1)
        else:
            folded = unicodedata.normalize("NFKD", ch)[0]
            primary.append((1, folded))
            secondary.append(0)
        i += 1
    return (primary, secondary, text)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(tree: Mapping[str, Any]) -> str:
    """SHA-256 of the canonical JSON of the tree, without its digest and timestamp."""
    body = {k: v for k, v in tree.items() if k not in ("digest", "generated_utc")}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


# ── building ──────────────────────────────────────────────────────────────────────────────────


def _load_inputs(paths: Mapping[str, Path]) -> Dict[str, Any]:
    sys.path.insert(0, str(REPO_ROOT))
    import llm_client_shared  # noqa: PLC0415
    import prompt_template  # noqa: PLC0415
    from vocab_manager import VocabularyManager  # noqa: PLC0415

    vocab = json.loads(paths["vocabulary"].read_text(encoding="utf-8"))
    manager = VocabularyManager(
        vocab_path=str(paths["vocabulary"]), config_path=str(paths["taxonomy_config"])
    )
    excluded = sorted(llm_client_shared.excluded_prompt_themes(manager))
    terms = prompt_template.vocabulary_terms(vocab, excluded)
    config = llm_client_shared.load_config(str(paths["llm_config"]))
    blocks = prompt_template.load_blocks(paths["prompt_blocks"])
    taxonomy = json.loads(paths["taxonomy_config"].read_text(encoding="utf-8"))
    flat = json.loads(paths["amcr_flat"].read_text(encoding="utf-8"))["terms"]
    flat = list(flat.values()) if isinstance(flat, dict) else flat
    with paths["specificity_pairs"].open(newline="", encoding="utf-8") as handle:
        pairs = [row for row in csv.DictReader(handle)]
    meta = (
        json.loads(paths["vocabulary_meta"].read_text(encoding="utf-8"))
        if paths["vocabulary_meta"].is_file()
        else {}
    )
    return {
        "terms": terms,
        "excluded": excluded,
        "geo_mode": prompt_template.resolve_geo_guardrail(config),
        "blocks": blocks,
        "geo_covers": list(
            (taxonomy.get("_settings", {}).get("geo_guardrail") or {}).get("covers") or []
        ),
        "amcr": {str(rec["source_id"]): rec for rec in flat},
        "pairs": pairs,
        "meta": meta,
        "sentinel": prompt_template.META_TEXT_TERM,
    }


def build_tree(paths: Optional[Mapping[str, Path]] = None) -> Dict[str, Any]:
    """The descent tree, as a JSON-ready dict (see the module docstring for the rules)."""
    paths = {**DEFAULT_INPUTS, **(paths or {})}
    data = _load_inputs(paths)
    sentinel = data["sentinel"]
    terms = [t for t in data["terms"] if t["cs"] != sentinel["cs"]]

    # Node ids: "t:<facet>/<cs>", made unique within the facet if a label repeats.
    term_ids: List[str] = []
    seen_ids: Counter = Counter()
    for t in terms:
        base = f"t:{t['theme']}/{t['cs']}"
        seen_ids[base] += 1
        term_ids.append(base if seen_ids[base] == 1 else f"{base}#{seen_ids[base]}")
    clashes = [t["cs"] for t in terms if t["cs"] in RESERVED]
    if clashes:
        raise SystemExit(f"vocabulary terms named like a reserved option: {clashes}")

    by_source_id: Dict[Tuple[str, str], set] = defaultdict(set)
    for index, t in enumerate(terms):
        for ident in t.get("ids", []):
            by_source_id[(t["theme"], str(ident["id"]))].add(index)
    pairs = {
        (row["facet"], str(row["source_id"])): row
        for row in data["pairs"]
        if row.get("same_facet") == "True"
    }

    parent: Dict[int, int] = {}
    found_by: Dict[int, Tuple[Optional[int], Optional[int]]] = {}
    for index, t in enumerate(terms):
        teater_parent = amcr_parent = None
        for ident in t.get("ids", []):
            key = (t["theme"], str(ident["id"]))
            if ident["source"] == "teater" and key in pairs:
                found = by_source_id.get(
                    (t["theme"], str(pairs[key]["nearest_ancestor_id"])), set()
                ) - {index}
                if found and teater_parent is None:
                    teater_parent = min(found)
            if (
                ident["source"] == "amcr"
                and str(ident["id"]) in data["amcr"]
                and amcr_parent is None
            ):
                for broader in data["amcr"][str(ident["id"])].get("broader") or []:
                    found = by_source_id.get((t["theme"], str(broader)), set()) - {index}
                    if found:
                        amcr_parent = min(found)
                        break
        chosen = teater_parent if teater_parent is not None else amcr_parent
        if chosen is None:
            continue
        parent[index] = chosen
        found_by[index] = (teater_parent, amcr_parent)

    # A cycle would make the descent endless; break it at the edge that closes it (none today).
    cycles_broken = 0
    for start in list(parent):
        path, node = [], start
        while node in parent:
            if node in path:
                del parent[node]
                cycles_broken += 1
                break
            path.append(node)
            node = parent[node]

    def group_of(index: int) -> str:
        node = index
        while node in parent:
            node = parent[node]
        return terms[node]["sub"]

    # Form terms and everything below them leave the tree (FORM_TERMS); the rest keep their parents.
    form_roots = {
        index
        for index, t in enumerate(terms)
        if any(i["source"] == "teater" and str(i["id"]) in FORM_TERMS for i in t.get("ids", []))
    }
    withheld = set()
    for index in range(len(terms)):
        node = index
        while True:
            if node in form_roots:
                withheld.add(index)
                break
            if node not in parent:
                break
            node = parent[node]
    kept = [index for index in range(len(terms)) if index not in withheld]

    edges = Counter()
    for index in kept:
        if index not in parent:
            continue
        teater_parent, amcr_parent = found_by[index]
        if teater_parent is not None and amcr_parent is not None and teater_parent != amcr_parent:
            edges["teater_amcr_conflicts"] += 1
        edges["from_teater" if teater_parent is not None else "from_amcr"] += 1
        if terms[parent[index]]["sub"] != terms[index]["sub"]:
            edges["cross_group"] += 1
    edges["cycles_broken"] += cycles_broken
    if not edges["cycles_broken"]:
        del edges["cycles_broken"]

    nodes: Dict[str, Dict[str, Any]] = {}
    facets: List[str] = []
    groups_of: Dict[str, List[str]] = defaultdict(list)
    for index in kept:
        t = terms[index]
        if t["theme"] not in facets:
            facets.append(t["theme"])
        if t["sub"] not in groups_of[t["theme"]]:
            groups_of[t["theme"]].append(t["sub"])

    children: Dict[int, List[int]] = defaultdict(list)
    roots: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for index in kept:
        t = terms[index]
        if index in parent:
            children[parent[index]].append(index)
        else:
            roots[(t["theme"], t["sub"])].append(index)

    geo = _geo_targets(data["geo_covers"], terms, data["amcr"])

    def sorted_terms(indices: Sequence[int]) -> List[str]:
        return [term_ids[i] for i in sorted(indices, key=lambda i: czech_key(terms[i]["cs"]))]

    dropped_groups = []
    for facet in facets:
        group_nodes = []
        for group in groups_of[facet]:
            members = roots.get((facet, group), [])
            if not members:
                dropped_groups.append(f"{facet}/{group}")
                continue
            gid = f"g:{facet}/{group}"
            nodes[gid] = {
                "kind": "group",
                "label": group,
                "facet": facet,
                "children": sorted_terms(members),
                "geo_gated": (facet, group) in geo["groups"],
            }
            group_nodes.append(gid)
        nodes[f"f:{facet}"] = {
            "kind": "facet",
            "label": facet,
            "children": sorted(group_nodes, key=lambda g: czech_key(nodes[g]["label"])),
        }
    for index in kept:
        t = terms[index]
        node = {
            "kind": "term",
            "cs": t["cs"],
            "en": t.get("en", t["cs"]),
            "facet": t["theme"],
            "group": group_of(index),
            "ids": t.get("ids", []),
            "children": sorted_terms(children.get(index, [])),
            "geo_gated": index in geo["terms"],
        }
        if t.get("bare_cs"):
            node["bare_cs"] = t["bare_cs"]
        nodes[term_ids[index]] = node
    nodes["root"] = {"kind": "root", "children": [f"f:{facet}" for facet in facets]}

    for node in nodes.values():
        extras = 1 + (
            1 if node["kind"] == "term" else 0
        )  # none_of_these, and <this term> for a term
        if len(node["children"]) + extras > MAX_OPTIONS:
            node["chunks"] = _chunks(node["children"], MAX_OPTIONS - 1)

    tree = {
        "format": TREE_FORMAT,
        "generated_by": "dm_run.py --dump-tree",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": {
            name: {
                "path": str(path.relative_to(REPO_ROOT))
                if path.is_relative_to(REPO_ROOT)
                else str(path),
                "sha256": _sha256(path),
            }
            for name, path in paths.items()
            if path.is_file()
        },
        "vocabulary_meta": {
            k: data["meta"].get(k) for k in ("generated_utc", "generator", "schema_version")
        }
        | {"total": (data["meta"].get("counts") or {}).get("total")},
        "excluded_themes": data["excluded"],
        "geo_guardrail": {"mode": data["geo_mode"], "covers": data["geo_covers"]},
        "withheld_form": {
            "reason": (
                "TEATER terms naming a kind of record (form), withheld with their subtrees: a text-only "
                "model decides content; form is read from images (ufal/atrium-project#83)"
            ),
            "teater_ids": dict(FORM_TERMS),
            "absent": sorted(
                set(FORM_TERMS)
                - {
                    str(i["id"])
                    for index in form_roots
                    for i in terms[index].get("ids", [])
                    if i["source"] == "teater"
                },
                key=int,
            ),
            "terms": sorted(term_ids[index] for index in withheld),
        },
        "questions": _question_wording(data["blocks"], sentinel),
        "sentinel": {"cs": sentinel["cs"], "en": sentinel["en"]},
        "reserved_options": list(RESERVED),
        "nodes": nodes,
        "stats": {},
    }
    tree["stats"] = tree_stats(tree, edges, dropped_groups)
    tree["digest"] = tree_digest(tree)
    return tree


def _geo_targets(
    covers: Sequence[str], terms: Sequence[Mapping[str, Any]], amcr: Mapping[str, Any]
) -> Dict[str, set]:
    """The groups (``heslar:<scheme>``) and terms (``teater:<id>``) the geographic gate covers."""
    schemes = {c.split(":", 1)[1] for c in covers if c.startswith("heslar:")}
    teater = {c.split(":", 1)[1] for c in covers if c.startswith("teater:")}
    groups, gated = set(), set()
    for index, t in enumerate(terms):
        for ident in t.get("ids", []):
            if (
                ident["source"] == "amcr"
                and (amcr.get(str(ident["id"])) or {}).get("scheme") in schemes
            ):
                groups.add((t["theme"], t["sub"]))
            if ident["source"] == "teater" and str(ident["id"]) in teater:
                gated.add(index)
    return {"groups": groups, "terms": gated}


def _chunks(children: Sequence[str], size: int) -> List[List[str]]:
    count = -(-len(children) // size)
    step = -(-len(children) // count)
    return [list(children[i : i + step]) for i in range(0, len(children), step)]


def _question_wording(blocks: Mapping[str, str], sentinel: Mapping[str, str]) -> Dict[str, Any]:
    """The texts of the decision questions, taken from the generative prompt's own blocks."""
    return {
        "L0_content": {
            "instructions": "Is the marked line archaeological content?",
            "criteria": {
                "false": blocks.get("rule.metatext", "").strip(),
                "true": "The line carries archaeological content.",
            },
            "no_gives": sentinel["cs"],
        },
        "L1g_geographic": {
            "instructions": "Is the marked line genuinely about a place, a people or a dynasty?",
            "criteria": {"true": blocks.get("guardrail.geographic.preference", "").strip()},
        },
        "L1_facet": "Which part of the vocabulary does the marked line belong to?",
        "L2_group": "Which group of terms fits the marked line?",
        "L3_term": "Which term fits the marked line best? Choose the most specific one the line supports.",
        "chunk_final": "Which of these terms fits the marked line best?",
    }


# ── the questions a descent asks ──────────────────────────────────────────────────────────────


def node_options(
    tree: Mapping[str, Any],
    node_id: str,
    chunk: Optional[int] = None,
    among: Optional[Sequence[str]] = None,
) -> Tuple[str, List[Tuple[str, str, str]]]:
    """``(instructions, [(option id, node id or reserved option, description)])`` asked at *node_id*.

    Over the node's children, one *chunk* of them, or the chunk winners given as *among*. Option ids
    are the labels a model reads (a term's Czech form); a label that repeats among the options gets
    its English form, then its node id, so no option is ever lost to a collision."""
    nodes = tree["nodes"]
    node = nodes[node_id]
    wording = tree["questions"]
    if among is not None:
        offered, instructions = list(among), wording["chunk_final"]
    elif chunk is not None:
        offered, instructions = node["chunks"][chunk], wording["L3_term"]
    else:
        offered = node["children"]
        instructions = {"root": wording["L1_facet"], "facet": wording["L2_group"]}.get(
            node["kind"], wording["L3_term"]
        )
    options: List[Tuple[str, str, str]] = []
    used = set(RESERVED)
    for child_id in offered:
        child = nodes[child_id]
        if child["kind"] == "facet":
            label = child["label"]
            description = "groups: " + "; ".join(nodes[g]["label"] for g in child["children"])
        elif child["kind"] == "group":
            label = child["label"]
            description = "for example: " + ", ".join(nodes[t]["cs"] for t in child["children"][:6])
        else:
            label, description = child["cs"], child["en"]
            if label in used:
                label = f"{child['cs']} [{child['en']}]"
        if label in used:
            label = f"{label} <{child_id}>"
        used.add(label)
        options.append((label, child_id, description))
    if node["kind"] == "term" and chunk is None:
        options.append((THIS_TERM, THIS_TERM, f"{node['cs']} itself; nothing narrower fits"))
    options.append((NONE_OF_THESE, NONE_OF_THESE, "none of the options fits the marked line"))
    return instructions, options


def node_choice(
    tree: Mapping[str, Any],
    node_id: str,
    chunk: Optional[int] = None,
    among: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """The ``choice`` asked at *node_id*, in the ``/v1/systemone`` wire format (see ``node_options``)."""
    instructions, options = node_options(tree, node_id, chunk, among)
    return {
        "type": "choice",
        "instructions": instructions,
        "criteria": {o: d for o, _, d in options},
    }


def every_choice(tree: Mapping[str, Any]) -> List[Tuple[str, Optional[int], Dict[str, Any]]]:
    """``(node, chunk, choice)`` for every choice the tree can ask (chunk finals at their widest)."""
    out = []
    for node_id, node in tree["nodes"].items():
        if not node["children"]:
            continue
        if "chunks" in node:
            for index in range(len(node["chunks"])):
                out.append((node_id, index, node_choice(tree, node_id, chunk=index)))
            winners = [chunk[0] for chunk in node["chunks"]]  # one winner per chunk, at most
            out.append((node_id, None, node_choice(tree, node_id, among=winners)))
        else:
            out.append((node_id, None, node_choice(tree, node_id)))
    return out


def tree_stats(
    tree: Mapping[str, Any], edges: Mapping[str, int], dropped_groups: Sequence[str]
) -> Dict[str, Any]:
    """The tree's shape, kept in the tree as ``stats``: its counts, how deep and how wide it gets, the
    parent edges by how they were found (*edges*), the chunked and geo-gated nodes, how many choices
    it can ask and the most options in one, and the hand count of 11-05 beside them."""
    nodes = tree["nodes"]
    term_nodes = [n for n in nodes.values() if n["kind"] == "term"]

    def depth(node_id: str) -> int:  # term levels below the group, the group's own terms being 1
        best = 0
        stack = [(node_id, 1)]
        while stack:
            current, level = stack.pop()
            best = max(best, level)
            stack += [(child, level + 1) for child in nodes[current]["children"]]
        return best

    deepest = max(depth(t) for g in nodes.values() if g["kind"] == "group" for t in g["children"])
    widest = sorted(((len(n["children"]), node_id) for node_id, n in nodes.items()), reverse=True)
    choices = every_choice(tree)
    return {
        "terms": len(term_nodes),
        "withheld_form_terms": len((tree.get("withheld_form") or {}).get("terms", [])),
        "facets": sum(1 for n in nodes.values() if n["kind"] == "facet"),
        "groups": sum(1 for n in nodes.values() if n["kind"] == "group"),
        "groups_dropped": list(dropped_groups),
        "single_group_facets": sorted(
            n["label"] for n in nodes.values() if n["kind"] == "facet" and len(n["children"]) == 1
        ),
        "inner_term_nodes": sum(1 for n in term_nodes if n["children"]),
        "deepest_term_level": deepest,
        "longest_parent_chain": deepest - 1,
        "parent_edges": dict(sorted(edges.items())),
        "chunked_nodes": [node_id for node_id, n in nodes.items() if "chunks" in n],
        "nodes_over_64_children": [f"{node_id} ({size})" for size, node_id in widest if size > 64],
        "geo_gated": sorted(node_id for node_id, n in nodes.items() if n.get("geo_gated")),
        "choices": len(choices),
        "max_options_per_choice": max(len(c["criteria"]) for _, _, c in choices),
        "11-05_figures": {
            "inner_term_nodes": 797,
            "levels_below_a_group": 11,
            "note": (
                "measured by hand on 11-05; the generated tree is authoritative. The difference in inner "
                "nodes comes from how a term's parent is chosen (same facet, crossing groups, AMČR broader)"
            ),
        },
    }


# ── CLI ───────────────────────────────────────────────────────────────────────────────────────


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Decision models over the controlled vocabulary (#3): the descent tree."
    )
    parser.add_argument(
        "--dump-tree", type=Path, metavar="OUT", help="write the descent tree (JSON) and exit"
    )
    parser.add_argument(
        "--lines", action="store_true", help="line mode, the vocabulary descent (not yet)"
    )
    args = parser.parse_args(argv)
    if args.lines:
        print(
            "line mode (the vocabulary descent over the tree) is not written yet (#3, Phase C)",
            file=sys.stderr,
        )
        return 2
    if not args.dump_tree:
        parser.error("nothing to do: pass --dump-tree OUT")
    tree = build_tree()
    args.dump_tree.parent.mkdir(parents=True, exist_ok=True)
    args.dump_tree.write_text(
        json.dumps(tree, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    stats = {
        k: v for k, v in tree["stats"].items() if k not in ("geo_gated", "nodes_over_64_children")
    }
    print(json.dumps({"digest": tree["digest"], **stats}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
