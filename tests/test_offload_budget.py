"""
tests/test_offload_budget.py
============================
Unit tests for the CPU-offload auto-sizing added for issue
ufal/atrium-project#26 (``CPU_OFFLOAD_GB=auto``): config coercion in
``get_inference_defaults``, the pure budget math in
``resolve_auto_cpu_offload``, and weight-footprint estimation from a (fake)
local HF cache.

Importing ``llm_utils`` needs torch + transformers — both absent from the
fast test lane (``requirements-test.txt``) — so the whole module skips there
and runs in the GPU CI lane (``requirements_llm.txt``). No GPU is required.
"""

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("transformers")

import llm_utils  # noqa: E402
from llm_utils import (  # noqa: E402
    estimate_weight_footprint_gb,
    get_inference_defaults,
    resolve_auto_cpu_offload,
)

# ── CPU_OFFLOAD_GB coercion in get_inference_defaults ────────────────────────


class TestAutoCoercion:
    def test_auto_sentinel_passes_through_for_vllm_model(self):
        resolved, sources = get_inference_defaults(
            "qwen3-235b-a22b-fp8", {"CPU_OFFLOAD_GB": "auto"}
        )
        assert resolved["CPU_OFFLOAD_GB"] == "auto"
        assert sources["CPU_OFFLOAD_GB"] == "config"

    def test_auto_is_case_insensitive(self):
        resolved, _ = get_inference_defaults("qwen3-235b-a22b-fp8", {"CPU_OFFLOAD_GB": "AUTO"})
        assert resolved["CPU_OFFLOAD_GB"] == "auto"

    def test_explicit_int_still_coerced(self):
        resolved, _ = get_inference_defaults("qwen3-235b-a22b-fp8", {"CPU_OFFLOAD_GB": "70"})
        assert resolved["CPU_OFFLOAD_GB"] == 70

    def test_garbage_value_rejected_with_clear_message(self):
        with pytest.raises(ValueError, match="CPU_OFFLOAD_GB"):
            get_inference_defaults("qwen3-235b-a22b-fp8", {"CPU_OFFLOAD_GB": "banana"})

    def test_auto_downgrades_to_zero_on_transformers_backend(self, capsys):
        resolved, sources = get_inference_defaults("qwen3-8b", {"CPU_OFFLOAD_GB": "auto"})
        assert resolved["BACKEND"] == "transformers"
        assert resolved["CPU_OFFLOAD_GB"] == 0
        assert sources["CPU_OFFLOAD_GB"] == "forced"
        assert "vLLM backend only" in capsys.readouterr().out

    def test_large_models_default_to_auto(self):
        resolved, sources = get_inference_defaults("qwen3-235b-a22b-fp8", {})
        assert resolved["CPU_OFFLOAD_GB"] == "auto"
        assert sources["CPU_OFFLOAD_GB"] == "model"

    def test_other_models_still_default_to_zero(self):
        resolved, _ = get_inference_defaults("qwen-3.6-35b-moe", {})
        assert resolved["CPU_OFFLOAD_GB"] == 0


# ── Pure budget math ─────────────────────────────────────────────────────────


class TestResolveAutoCpuOffload:
    def test_model_that_fits_returns_zero(self):
        assert (
            resolve_auto_cpu_offload(
                footprint_gb=20.0,
                tensor_parallel_size=1,
                gpu_memory_utilization=0.90,
                per_gpu_vram_gb=48.0,
                ram_available_gb=200.0,
            )
            == 0
        )

    def test_deficit_is_ceiled_with_margin(self):
        # budget = (48 × 0.90 − 4) × 1 = 39.2 → deficit 10.8 → ceil(10.8 + 2) = 13
        assert (
            resolve_auto_cpu_offload(
                footprint_gb=50.0,
                tensor_parallel_size=1,
                gpu_memory_utilization=0.90,
                per_gpu_vram_gb=48.0,
                ram_available_gb=200.0,
            )
            == 13
        )

    def test_validated_dll4gpu3_recipe_magnitude(self):
        # qwen3-235b-a22b-fp8 on 4× L40 48 GB (dll-4gpu3, 503 GB RAM), gmu 0.88:
        # budget = (48 × 0.88 − 4) × 4 = 152.96 → deficit 82.04 → 85.
        # Same magnitude as the hand-tuned CPU_OFFLOAD_GB=70 recipe, with more
        # KV headroom.
        offload = resolve_auto_cpu_offload(
            footprint_gb=235.0,
            tensor_parallel_size=4,
            gpu_memory_utilization=0.88,
            per_gpu_vram_gb=48.0,
            ram_available_gb=503.0,
        )
        assert 70 <= offload <= 90

    def test_ram_cap_raises_with_slurm_hint(self):
        with pytest.raises(ValueError, match="--mem"):
            resolve_auto_cpu_offload(
                footprint_gb=100.0,
                tensor_parallel_size=1,
                gpu_memory_utilization=0.90,
                per_gpu_vram_gb=48.0,
                ram_available_gb=30.0,
            )

    def test_unknown_ram_skips_the_cap(self):
        # deficit = 100 − 39.2 = 60.8 → ceil(60.8 + 2) = 63; no RAM info → no cap
        assert (
            resolve_auto_cpu_offload(
                footprint_gb=100.0,
                tensor_parallel_size=1,
                gpu_memory_utilization=0.90,
                per_gpu_vram_gb=48.0,
                ram_available_gb=None,
            )
            == 63
        )


# ── Weight-footprint estimation ──────────────────────────────────────────────


def _make_fake_cache(root, hf_id, files):
    """Create an HF-cache-shaped tree: hub/models--Org--Name/snapshots/<rev>/."""
    snap = root / "hub" / ("models--" + hf_id.replace("/", "--")) / "snapshots" / "abc123"
    snap.mkdir(parents=True)
    for name, size in files.items():
        (snap / name).write_bytes(b"\0" * size)
    return root


class TestEstimateWeightFootprint:
    def test_sums_weight_files_from_hf_home(self, tmp_path, monkeypatch):
        hf_id = llm_utils.MODEL_REGISTRY["qwen3-8b"]["hf_id"]
        _make_fake_cache(
            tmp_path,
            hf_id,
            {
                "model-00001-of-00002.safetensors": 3 * 1024**2,
                "model-00002-of-00002.safetensors": 2 * 1024**2,
                "tokenizer.json": 10 * 1024**2,  # not a weight file — ignored
            },
        )
        monkeypatch.setenv("HF_HOME", str(tmp_path))
        monkeypatch.delenv("HF_HUB_CACHE", raising=False)
        gb = estimate_weight_footprint_gb("qwen3-8b")
        assert gb == pytest.approx(5 * 1024**2 / 1024**3)

    def test_gguf_filename_pattern_filters_other_quantizations(self, tmp_path, monkeypatch):
        hf_id = llm_utils.MODEL_REGISTRY["gemma-4-26b-moe-gguf"]["hf_id"]
        _make_fake_cache(
            tmp_path,
            hf_id,
            {
                "model.Q4_K_M.gguf": 4 * 1024**2,
                "model.Q8_0.gguf": 8 * 1024**2,  # different quant — must not count
            },
        )
        monkeypatch.setenv("HF_HOME", str(tmp_path))
        monkeypatch.delenv("HF_HUB_CACHE", raising=False)
        gb = estimate_weight_footprint_gb("gemma-4-26b-moe-gguf")
        assert gb == pytest.approx(4 * 1024**2 / 1024**3)

    def test_falls_back_to_registry_estimate(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HF_HOME", str(tmp_path))  # empty cache
        monkeypatch.delenv("HF_HUB_CACHE", raising=False)
        monkeypatch.setattr(llm_utils, "_hub_weight_bytes", lambda *a, **k: 0)
        gb = estimate_weight_footprint_gb("qwen3-235b-a22b-fp8")
        assert gb == 235.0
        assert "registry estimate" in capsys.readouterr().out

    def test_returns_none_when_no_source_knows(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HF_HOME", str(tmp_path))
        monkeypatch.delenv("HF_HUB_CACHE", raising=False)
        monkeypatch.setattr(llm_utils, "_hub_weight_bytes", lambda *a, **k: 0)
        monkeypatch.setitem(llm_utils.MODEL_REGISTRY, "fake-model", {"hf_id": "fake/none"})
        assert estimate_weight_footprint_gb("fake-model") is None
        assert "Cannot estimate" in capsys.readouterr().out

    def test_unknown_model_key_returns_none(self):
        assert estimate_weight_footprint_gb("no-such-model") is None
