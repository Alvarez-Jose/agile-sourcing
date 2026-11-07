"""Only adapt the API transport; leave the team's RAG output untouched."""

from copy import deepcopy

from backend.api.citations import frontend_sources


def test_original_citation_numbers_and_text_are_preserved_without_invented_offsets():
    sources = [
        {
            "ref": 4,
            "policy": "Policy",
            "section": "Section",
            "page": "2",
            "text": "Original supporting text.",
            "cited": True,
        }
    ]
    original = deepcopy(sources)
    result = frontend_sources(sources)
    assert result[0]["citation_id"] == 4
    assert result[0]["evidence"] == [{"quote": "Original supporting text."}]
    assert result[0]["source_url"] is None
    assert sources == original
    assert all(result[0][key] == value for key, value in original[0].items())


def test_existing_evidence_and_source_url_are_preserved():
    source = {
        "ref": 1,
        "source_url": "https://official.example/policy.pdf",
        "evidence": [{"quote": "Original", "start": 4, "end": 12}],
    }
    result = frontend_sources([source])[0]
    assert result["evidence"] == source["evidence"]
    assert result["source_url"] == source["source_url"]
