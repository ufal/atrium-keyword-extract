"""
tests/test_llm_run_contract.py — llm_run.py's calls into llm_utils.py, checked without torch.

test_llm_run.py and test_llm_utils.py import the engine, so they skip wherever torch and
transformers are missing, and that is every CI lane: the fast lane has neither, and
gpu-inference.yml runs only `-m slow`. That is how llm_run.py came to call
``process_document(csv_path=...)`` against a signature that required ``input_path``, and
``process_document_vllm(input_path=...)`` against one that also required ``csv_path``: both
backends raised TypeError on every document, and the run still ended with "skipped (errors)"
and exit 0. These checks read the two files' syntax trees instead, so they run everywhere.
"""

import ast
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _tree(name: str) -> ast.Module:
    return ast.parse((ROOT_DIR / name).read_text(encoding="utf-8"))


def _calls(tree: ast.AST, names: set) -> list:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in names
    ]


def _binding_problems(call: ast.Call, fn: ast.FunctionDef) -> list:
    """What would make ``call`` raise TypeError against ``fn``'s signature."""
    args = fn.args
    positional = args.posonlyargs + args.args
    required = [a.arg for a in positional[: len(positional) - len(args.defaults)]]
    required += [
        a.arg
        for a, default in zip(args.kwonlyargs, args.kw_defaults, strict=True)
        if default is None
    ]
    given = {a.arg for a in positional[: len(call.args)]} | {k.arg for k in call.keywords}
    problems = [f"missing {name!r}" for name in required if name not in given]
    if args.kwarg is None:
        known = {a.arg for a in positional + args.kwonlyargs}
        problems += [f"unknown {k.arg!r}" for k in call.keywords if k.arg not in known]
    return problems


def test_every_call_into_llm_utils_binds_to_its_signature():
    run = _tree("llm_run.py")
    functions = {
        node.name: node for node in _tree("llm_utils.py").body if isinstance(node, ast.FunctionDef)
    }
    imported = {
        alias.name
        for node in run.body
        if isinstance(node, ast.ImportFrom) and node.module == "llm_utils"
        for alias in node.names
    } & set(functions)

    checked, problems = set(), []
    for call in _calls(run, imported):
        if any(isinstance(a, ast.Starred) for a in call.args) or any(
            k.arg is None for k in call.keywords
        ):
            continue  # *args / **kwargs cannot be bound statically
        checked.add(call.func.id)
        problems += [
            f"llm_run.py:{call.lineno} {call.func.id}(): {p}"
            for p in _binding_problems(call, functions[call.func.id])
        ]

    assert {"process_document", "process_document_vllm", "load_vllm_engine"} <= checked
    assert not problems, problems


def test_vllm_structured_outputs_take_the_schema_as_json():
    """Both of vLLM's spellings — StructuredOutputsParams (0.11+) and GuidedDecodingParams
    (before 0.12) — take the schema as ``json``; neither ever had ``json_schema``, which made
    every vLLM request fail before it reached the model."""
    calls = _calls(_tree("llm_utils.py"), {"StructuredOutputsParams", "GuidedDecodingParams"})
    assert {c.func.id for c in calls} == {"StructuredOutputsParams", "GuidedDecodingParams"}
    for call in calls:
        assert [k.arg for k in call.keywords] == ["json"], ast.unparse(call)


def test_each_sampling_params_spelling_gets_its_own_class():
    """``structured_outputs=`` takes a StructuredOutputsParams and ``guided_decoding=`` a
    GuidedDecodingParams; crossing the two pairs fails on every vLLM."""
    pairing = {
        "structured_outputs": "StructuredOutputsParams",
        "guided_decoding": "GuidedDecodingParams",
    }
    seen = set()
    for call in _calls(_tree("llm_utils.py"), {"SamplingParams"}):
        for kw in call.keywords:
            if kw.arg in pairing:
                seen.add(kw.arg)
                assert isinstance(kw.value, ast.Call) and kw.value.func.id == pairing[kw.arg]
    assert seen == set(pairing)
