import json

import pytest

from api_util import summarize_nt_udp
from api_util.summarize_nt_udp import get_ne_explanation
from atrium_paradata import ParadataLogger


class TestNameTagExplanationMapping:
    def test_native_onto_tags(self):
        """Test that native ONTO tags are correctly resolved to their descriptions."""
        assert get_ne_explanation("B-PERSON") == "People, including fictional"
        assert get_ne_explanation("I-ORG") == "Companies, agencies, institutions, etc."
        assert get_ne_explanation("B-GPE") == "Countries, cities, states"

    def test_legacy_cnec_mapped_to_onto(self):
        """Test that legacy CNEC tags are correctly bridged to ONTO descriptions."""
        # 'p' -> 'PERSON'
        assert get_ne_explanation("B-p") == "People, including fictional"
        # 'i' -> 'ORG'
        assert get_ne_explanation("I-i") == "Companies, agencies, institutions, etc."
        # 'g' -> 'GPE'
        assert get_ne_explanation("B-g") == "Countries, cities, states"

    def test_complex_tag_strings(self):
        """Test that compound tags separated by pipes correctly read the primary tag."""
        assert get_ne_explanation("B-PERSON|I-p") == "People, including fictional"
        assert get_ne_explanation("I-g|B-GPE") == "Countries, cities, states"

    def test_empty_and_o_tags(self):
        """Test that 'O', empty strings, and None return an empty string."""
        assert get_ne_explanation("O") == ""
        assert get_ne_explanation("_") == ""
        assert get_ne_explanation("") == ""
        assert get_ne_explanation(None) == ""

    def test_unknown_tags(self):
        """Test that completely unknown tags fall back gracefully."""
        explanation = get_ne_explanation("B-unknown_xyz")
        assert "Unknown Code" in explanation
        assert "unknown_xyz" in explanation


def test_the_record_is_stamped_with_the_stages_own_run(tmp_path, monkeypatch):
    """atrium-project#71: the stats step reads its run from the stage's state file
    (--para-state), not from whichever `.state_*.json` a shared paradata directory lists
    first, and hands its run_id, run_uuid, paradata file and licences to the record write."""
    para_dir = tmp_path / "paradata"
    para_dir.mkdir()
    other = ParadataLogger("udpipe", {}, paradata_dir=str(para_dir))
    (para_dir / ".state_0_aaa.json").write_text(
        json.dumps(other._to_state_dict()), encoding="utf-8"
    )
    stage = ParadataLogger("nlp-enrich", {}, paradata_dir=str(para_dir))
    state = para_dir / ".state_1_nlp-enrich.json"
    state.write_text(json.dumps(stage._to_state_dict()), encoding="utf-8")

    seen = {}
    monkeypatch.setattr(
        summarize_nt_udp, "process_single_document", lambda **kw: seen.update(kw) or True
    )
    with pytest.raises(SystemExit) as exit_:
        summarize_nt_udp.main(
            [
                "--conllu", "x.conllu", "--ne-dir", "ne", "--output-dir", "out",
                "--document-json-dir", str(tmp_path / "records"), "--para-state", str(state),
            ]
        )  # fmt: skip
    assert exit_.value.code == 0
    assert (seen["document_run_id"], seen["document_run_uuid"]) == (stage.run_id, stage.run_uuid)
    assert seen["document_paradata_ref"] == stage.paradata_ref
    assert seen["document_license_detail"] == stage.get_license_block()
