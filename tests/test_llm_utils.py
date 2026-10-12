"""
tests/test_llm_utils.py
=======================
Tests for the pure helpers carved out of the llm_utils.py monolith.
"""

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("transformers")

from pydantic import BaseModel, Field  # noqa: E402

import llm_utils  # noqa: E402
from llm_utils import (  # noqa: E402
    MODEL_REGISTRY,
    _line_cache,
    _prompt_token_ids,
    _reset_format_enforcer,
    _rewind_prompt_cache,
    _row_quality,
    _should_process_line,
    get_context_window,
    prefill_prompt_cache,
    process_document,
    read_input_rows,
    validate_llm_output,
)


class DummyEnrichment(BaseModel):
    teater_category: str
    # Enforce a max of 1.0 so that 1.5 triggers the ValidationError fallback block
    confidence_score: float = Field(..., le=1.0)
    extracted_keywords_cs: list[str]

    def category_name(self):
        return self.teater_category


def test_validate_llm_output_success():
    """Test standard valid JSON parsing."""
    valid_json = (
        '{"teater_category": "Osoby", "confidence_score": 0.95, "extracted_keywords_cs": ["Jan"]}'
    )
    result = validate_llm_output(valid_json, DummyEnrichment, "doc1", 1, 1)
    assert result["teater_category"] == "Osoby"
    assert result["confidence_score"] == 0.95


def test_validate_llm_output_fallback_recovery():
    """Test recovery when strict JSON validation fails but fallback parsing works."""
    # Score is 1.5, which fails the strict Field(le=1.0) check.
    # The helper bounds it to 1.0 during the fallback sequence.
    recoverable_json = (
        '{"teater_category": "Místa", "confidence_score": 1.5, "extracted_keywords_cs": ["Praha"]}'
    )
    result = validate_llm_output(recoverable_json, DummyEnrichment, "doc1", 1, 1)
    assert result["confidence_score"] == 1.0


def test_validate_llm_output_meta_text_clearing():
    """Test that meta-text correctly strips out keywords."""
    meta_json = '{"teater_category": "Nerelevantní (meta-text)", "confidence_score": 0.9, "extracted_keywords_cs": ["fake"]}'
    result = validate_llm_output(meta_json, DummyEnrichment, "doc1", 1, 1)
    assert result["extracted_keywords_cs"] == []


def test_should_process_line_noise_rejection():
    """Test that the quality filter accurately drops low-quality and 'Trash' lines."""
    should_proc, _ = _should_process_line("Some text", "Empty", 0.30, True, 3, 8, 0.40)
    assert not should_proc

    should_proc, _ = _should_process_line("Good length text", "Trash", 0.80, True, 3, 8, 0.40)
    assert not should_proc


def test_a_row_without_a_quality_score_is_not_trash():
    """A TEITOK document (or a text table) has no line quality. Treating the missing score as
    0.0 turned every such row into "Trash", so a .teitok.xml input enriched nothing."""
    should_proc, _ = _should_process_line("A readable line", "", None, True, 3, 8, 0.40)
    assert should_proc
    should_proc, _ = _should_process_line("ab", "", None, True, 3, 8, 0.40)
    assert not should_proc  # the length rules still apply


def test_row_quality_reads_the_score_or_none():
    assert _row_quality({"quality_score": "0.91"}) == 0.91
    assert _row_quality({"quality_score": 0.2}) == 0.2
    assert _row_quality({"quality_score": ""}) is None
    assert _row_quality({"quality_score": None}) is None
    assert _row_quality({}) is None
    assert _row_quality({"quality_score": "n/a"}) is None


def test_teitok_rows_reach_the_model(tmp_path):
    teitok = tmp_path / "doc.teitok.xml"
    teitok.write_text(
        '<TEI><text><body><pb n="1"/><div><s id="s-1" text="Výzkum proběhl v Praze.">'
        "<tok>Výzkum</tok></s></div></body></text></TEI>",
        encoding="utf-8",
    )
    rows = read_input_rows(teitok)
    assert rows and rows[0]["quality_score"] is None
    should_proc, reason = _should_process_line(
        rows[0]["text"], rows[0]["categ"], _row_quality(rows[0]), True, 3, 8, 0.40
    )
    assert should_proc, reason


def test_get_context_window_formatting():
    """Verify that context windows correctly wrap the target line with <target_line>."""
    rows = [
        {"text": "Line 1", "page_num": 1, "line_num": 1, "categ": ""},
        {"text": "Line 2", "page_num": 1, "line_num": 2, "categ": ""},
        {"text": "Line 3", "page_num": 1, "line_num": 3, "categ": ""},
    ]

    context = get_context_window(rows, center_idx=1, window=1)
    assert "<target_line> >>> [P1 L2] Line 2 </target_line>" in context
    assert "[P1 L1] Line 1" in context
    assert "[P1 L3] Line 3" in context


class _Tok:
    """encode() as a tokenizer that adds ``bos`` in front of every text, or none."""

    def __init__(self, bos=None, adds_bos=False):
        self.bos_token_id, self.adds_bos = bos, adds_bos

    def encode(self, text):
        ids = [ord(c) for c in text.replace("<bos>", "\x01")]
        return ([self.bos_token_id] if self.adds_bos else []) + ids


def test_a_bos_written_by_the_chat_template_is_not_doubled():
    """Gemma's, Llama's and Mistral's templates write the BOS into the text and their
    tokenizers add another: the model saw two. Only an actual duplicate is dropped."""
    assert _prompt_token_ids("<bos>hi", _Tok(bos=1, adds_bos=True)) == [1, ord("h"), ord("i")]
    assert _prompt_token_ids("hi", _Tok(bos=1, adds_bos=True)) == [1, ord("h"), ord("i")]
    assert _prompt_token_ids("<bos>hi", _Tok(bos=1)) == [1, ord("h"), ord("i")]
    assert _prompt_token_ids("hi", _Tok()) == [ord("h"), ord("i")]  # Qwen: no BOS at all


def test_format_enforcer_states_are_dropped_after_a_line():
    """lm-format-enforcer keys a state by the whole sequence, prompt included, and never
    evicts: ~117 MB per line with the full prompt, until the job's memory runs out."""

    class Enforcer:
        prefix_states = {(1, 2, 3): "state"}

    class PrefixFn:
        token_enforcer = Enforcer()

    fn = PrefixFn()
    _reset_format_enforcer(fn)
    assert fn.token_enforcer.prefix_states == {}
    _reset_format_enforcer(None)  # the GGUF path has no prefix function


def _tiny(kind):
    import transformers as tf

    torch.manual_seed(0)
    common = dict(
        vocab_size=128,
        hidden_size=32,
        intermediate_size=64,
        num_attention_heads=4,
        num_key_value_heads=2,
        head_dim=8,
        max_position_embeddings=1024,
        pad_token_id=0,
    )
    if kind == "dense":
        return tf.Qwen3ForCausalLM(tf.Qwen3Config(num_hidden_layers=2, **common))
    if kind == "sliding":
        cfg = tf.Gemma3TextConfig(num_hidden_layers=6, sliding_window=16, **common)
        return tf.Gemma3ForCausalLM(cfg)
    cfg = tf.Qwen3_5TextConfig(
        num_hidden_layers=4,
        linear_conv_kernel_dim=4,
        linear_key_head_dim=8,
        linear_value_head_dim=8,
        linear_num_key_heads=2,
        linear_num_value_heads=4,
        **common,
    )
    model = tf.Qwen3_5ForCausalLM(cfg)
    # Random weights forget a linear-attention state within a token or two, which would let
    # a line run from the wrong state pass. A slow decay and a louder output make it count.
    for layer in model.model.layers:
        if getattr(layer, "linear_attn", None) is not None:
            layer.linear_attn.A_log.data.fill_(-4.0)
            layer.linear_attn.dt_bias.data.fill_(-1.0)
            layer.linear_attn.out_proj.weight.data *= 8.0
    return model


@pytest.mark.parametrize("kind", ["dense", "sliding", "hybrid"])
def test_lines_started_from_the_prompt_cache_match_a_full_prefill(kind):
    """Qwen3 / Llama (full attention: shared, rewound), Gemma (sliding window: copied) and
    Qwen3.5/3.6 (linear attention: copied). Every line must generate what a full prefill
    generates, and the shared prefix must come back intact after each one."""
    model = _tiny(kind).eval()
    model.generation_config.eos_token_id = None
    prefix = torch.randint(3, 128, (60,)).tolist()
    lines = [prefix + torch.randint(3, 128, (n,)).tolist() for n in (9, 21)]

    def generate(ids, **kw):
        ids = torch.tensor([ids])
        with torch.no_grad():
            out = model.generate(
                input_ids=ids,
                attention_mask=torch.ones_like(ids),
                max_new_tokens=6,
                do_sample=False,
                pad_token_id=0,
                **kw,
            )
        return out[0, ids.shape[1] :].tolist()

    expected = [generate(ids) for ids in lines]
    cache = prefill_prompt_cache(model, prefix, prefill_chunk_size=16)
    assert cache is not None and len(cache["ids"]) == 60
    for ids, want in zip(lines + lines, expected + expected, strict=True):
        try:
            got = generate(ids, past_key_values=_line_cache(cache), cache_implementation=None)
        finally:
            _rewind_prompt_cache(cache)
        assert got == want
        assert cache["cache"].get_seq_length() == 60


def _tensors(value):
    if isinstance(value, torch.Tensor):
        yield value
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _tensors(v)
    elif isinstance(value, dict):
        for v in value.values():
            yield from _tensors(v)


def test_the_prompt_cache_holds_no_prefill_buffers():
    """A sliding-window layer keeps its window as a view into the last prefill chunk. Kept
    in the cache and copied for every line, those buffers ran Gemma-4-31B out of memory on
    every line (2x A30, 2026-10-12)."""
    model = _tiny("sliding").eval()
    cache = prefill_prompt_cache(model, torch.randint(3, 128, (300,)).tolist(), 64)
    line = _line_cache(cache)
    for layer in cache["cache"].layers + line.layers:
        for t in _tensors(vars(layer)):
            assert t.untyped_storage().nbytes() == t.numel() * t.element_size()


class _OutOfMemoryWithCache:
    """generate() that runs out of memory whenever it is given a cache."""

    device = "cpu"

    def __init__(self):
        self.calls = []

    def generate(self, input_ids=None, **kw):
        self.calls.append("cached" if "past_key_values" in kw else "full")
        if "past_key_values" in kw:
            raise torch.cuda.OutOfMemoryError("CUDA out of memory.")
        return torch.cat([input_ids, torch.tensor([[7]])], dim=1)


class _CharTokenizer:
    pad_token_id = eos_token_id = 0

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True, **kw):
        return "".join(m["content"] for m in messages)

    def encode(self, text):
        return [ord(c) % 1000 + 1 for c in text]

    def decode(self, ids, skip_special_tokens=True):
        return '{"teater_category": "kostel", "confidence_score": 0.9, "extracted_keywords_cs": []}'


def test_out_of_memory_with_the_prompt_cache_falls_back_to_the_full_prefill(tmp_path):
    """The run must not stop where it ran before REUSE_PROMPT_CACHE: the cache is dropped
    and the line retried, and so is every line after it."""
    doc = tmp_path / "CTX000000001.csv"
    doc.write_text(
        "page_num,line_num,text,categ,quality_score\n"
        "1,1,Nalezená keramika z raného středověku.,Clear,0.9\n"
        "1,2,Kostel sv. Petra a Pavla na návsi.,Clear,0.9\n",
        encoding="utf-8",
    )
    tokenizer, model = _CharTokenizer(), _OutOfMemoryWithCache()
    system_prompt = "SYSTEM " * 40
    cache = {
        "ids": tokenizer.encode(system_prompt),
        "cache": type("C", (), {"layers": []})(),
        "shared": [],
    }
    lines, stats = process_document(
        input_path=doc,
        model=model,
        tokenizer=tokenizer,
        parser=None,
        prefix_function=None,
        system_prompt=system_prompt,
        EnrichmentModel=DummyEnrichment,
        max_input_tokens=4000,
        is_gguf=False,
        model_key="gemma-4-31b-it",
        prompt_cache=cache,
    )
    assert model.calls == ["cached", "full", "full"]
    assert stats["processed"] == 2 and stats["skipped_error"] == 0
    assert stats["cached_prefix_lines"] == 0 and cache == {}


def test_the_enum_index_answers_as_lm_format_enforcer_does(monkeypatch):
    """The index replaces a scan of all 4,712 labels per call (~7.5 s of every line); the
    characters it allows after every prefix must be the ones the scan allows."""
    jsp = pytest.importorskip("lmformatenforcer.jsonschemaparser")
    state = jsp.StringParsingState
    original = getattr(state.get_allowed_characters, "__wrapped__", state.get_allowed_characters)
    monkeypatch.setattr(state, "get_allowed_characters", original)
    labels = ["kost", "kostel", "kostelík", "malta", "Malta (stát)", "zámek", "zámek (sídlo elity)"]
    schema = {
        "type": "object",
        "properties": {"c": {"type": "string", "enum": labels}},
        "required": ["c"],
    }

    def allowed_after_each_character(text):
        parser = jsp.JsonSchemaParser(schema)
        allowed = [set(parser.get_allowed_characters())]
        for character in text:
            parser = parser.add_character(character)
            allowed.append(set(parser.get_allowed_characters()))
        return allowed

    texts = ['{"c": "' + label + '"}' for label in labels] + ['{"c":  "zám', '{ "c" : "ko']
    expected = [allowed_after_each_character(t) for t in texts]
    assert llm_utils._patch_lmfe_enum_index()
    assert state.get_allowed_characters is not original
    assert [allowed_after_each_character(t) for t in texts] == expected


def test_rope_scaling_keeps_the_models_own_theta(monkeypatch):
    """transformers 5 keeps rope_theta inside rope_parameters, and its rope_scaling setter
    replaces the whole dict: YaRN has to be merged in, not set over it."""
    import transformers as tf

    base = tf.Qwen3Config(rope_theta=1_000_000.0)
    monkeypatch.setattr(tf.AutoConfig, "from_pretrained", lambda *a, **k: base)
    spec = MODEL_REGISTRY["qwen3-8b"]
    config = llm_utils._rope_scaled_config(spec)
    assert config.rope_parameters == {"rope_theta": 1_000_000.0, **spec["rope_scaling"]}
    # vLLM takes the served window from here, and does not scale it by the YaRN factor
    assert config.max_position_embeddings == spec["context_window"]
    assert llm_utils._rope_scaled_config(MODEL_REGISTRY["qwen-3.6-27b-it"]) is None


def test_rope_scaled_entries_reach_their_context_window():
    """An entry's context_window is reached only through its rope_scaling."""
    scaled = {k: v for k, v in MODEL_REGISTRY.items() if v.get("rope_scaling")}
    assert {"qwen3-8b", "qwen3-14b", "qwen2.5-14b-awq"} <= set(scaled)
    for key, spec in scaled.items():
        rope = spec["rope_scaling"]
        assert (
            rope["original_max_position_embeddings"] * rope["factor"] == spec["context_window"]
        ), key
