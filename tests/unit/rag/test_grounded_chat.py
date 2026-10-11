"""Grounded chat and access boundaries; synthetic policies are never real guidance."""

import hashlib
import json
from unittest.mock import Mock

from docx import Document
import pytest
from reportlab.pdfgen import canvas

from backend.auth.models import UserProfile
from backend.auth.policy_access import policy_scope
from backend.rag import pipeline
from rag_pipeline.documents.build import prepare_source_index
from rag_pipeline.documents.models import AccessScope, LOCAL_REVIEW_SCOPE
from rag_pipeline.documents.store import PolicyIndex, write_source_index
from rag_pipeline.retriever.section_retriever import SectionRetriever


@pytest.fixture
def corpus(tmp_path):
    source = tmp_path / "sources"
    source.mkdir()
    entries = []
    specs = [
        (
            "public-policy",
            "public",
            "active",
            "I. PURCHASING",
            "The departmental requester must document price reasonableness using comparable supplier quotations before approving the purchase. Refer to SUPPORT FORM for the supporting details.",
        ),
        (
            "support-form",
            "public",
            "active",
            "SUPPORT FORM",
            "Record the product description, supplier name and justification on this form. Include supporting quotations with the submission. This form records purchase documentation for auditing.",
        ),
        (
            "internal-policy",
            "internal",
            "active",
            "I. INTERNAL PRICING",
            "INTERNAL SECRET ONLY: the special internal pricing review requires confidential departmental approval before purchasing the restricted item from any approved vendor.",
        ),
        (
            "restricted-policy",
            "restricted",
            "active",
            "I. RESTRICTED PRICING",
            "RESTRICTED SECRET ONLY: the restricted supplier pricing agreement requires additional authorization before placing any purchase with this confidential contracted vendor.",
        ),
        (
            "draft-policy",
            "public",
            "review",
            "I. DRAFT",
            "DRAFT SECRET ONLY: this unreviewed supplier pricing guidance has not been released and must not be used for current procurement determinations.",
        ),
    ]
    for identifier, classification, status, heading, text in specs:
        path = source / f"{identifier}.docx"
        doc = Document()
        doc.add_heading(heading, 1)
        doc.add_paragraph(text)
        doc.save(path)
        entries.append(
            dict(
                id=identifier,
                filenames=[path.name],
                title=identifier,
                aliases=["SUPPORT FORM"] if identifier == "support-form" else [],
                kind="form" if identifier == "support-form" else "policy",
                access_classification=classification,
                review_status=status,
                reviewed_by="fixture",
                reviewed_at="2026-01-01T00:00:00Z",
                reviewed_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    pdf = source / "pdf-policy.pdf"
    c = canvas.Canvas(str(pdf))
    c.drawString(30, 780, "I. COMPETITIVE PROPOSALS")
    c.drawString(
        30,
        750,
        "For the synthetic fixture purchase, obtain quotations from three qualified suppliers.",
    )
    c.save()
    entries.append(
        dict(
            id="pdf-policy",
            filenames=[pdf.name],
            title="PDF fixture",
            access_classification="public",
            review_status="active",
            reviewed_by="fixture",
            reviewed_at="2026-01-01T00:00:00Z",
            reviewed_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
        )
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(dict(schema_version=1, documents=entries)))
    bundle = prepare_source_index(source, manifest, max_tokens=40, overlap_tokens=5)
    db = tmp_path / "sources.sqlite"
    write_source_index(bundle, db)
    return db, bundle, manifest, source


@pytest.mark.parametrize(
    "clearance,expected",
    [
        ("none", ("public",)),
        ("public", ("public",)),
        ("internal", ("public", "internal")),
        ("restricted", ("public", "internal", "restricted")),
        ("admin", ("public",)),
        ("department_buyer", ("public",)),
        ("INTERNAL", ("public",)),
    ],
)
def test_exact_server_clearance_mapping(clearance, expected):
    user = UserProfile(
        uid="u",
        email="u@ucsc.edu",
        is_approved=True,
        clearance=clearance,
        role="admin",
        department="IT",
    )
    scope = policy_scope(user)
    assert scope.classifications == expected
    assert not scope.include_review and not scope.include_archived


def test_pending_profile_does_not_grant_retrieval():
    with pytest.raises(PermissionError):
        policy_scope(UserProfile(uid="u", email="u@ucsc.edu", clearance="restricted"))


@pytest.mark.parametrize(
    "classes,allowed",
    [
        (("public",), {"public-policy", "support-form", "pdf-policy"}),
        (
            ("public", "internal"),
            {"public-policy", "support-form", "pdf-policy", "internal-policy"},
        ),
        (
            ("public", "internal", "restricted"),
            {
                "public-policy",
                "support-form",
                "pdf-policy",
                "internal-policy",
                "restricted-policy",
            },
        ),
    ],
)
def test_scope_filters_before_all_model_hooks_and_graph_expansion(
    corpus, classes, allowed
):
    db, _, _, _ = corpus
    seen = []

    def semantic(question, records):
        seen.extend(text for _, text in records)
        return [0.8] * len(records)

    def rerank(question, texts):
        seen.extend(texts)
        return list(range(len(texts), 0, -1))

    retriever = SectionRetriever(
        PolicyIndex(db, AccessScope(classifications=classes)), semantic, rerank
    )
    passages = retriever.retrieve("pricing purchase quotations")
    assert {doc.id for doc in retriever.corpus["documents"]} == allowed
    assert passages
    assert all(p.document.id in allowed for p in passages)
    text = " ".join(seen)
    assert "DRAFT SECRET ONLY" not in text
    if "internal" not in classes:
        assert "INTERNAL SECRET ONLY" not in text
    if "restricted" not in classes:
        assert "RESTRICTED SECRET ONLY" not in text
    allowed_versions = {doc.version_id for doc in retriever.corpus["documents"]}
    assert all(
        e.document_version_id in allowed_versions
        for edge in retriever.corpus["edges"]
        for e in edge.evidence
    )


def test_heading_match_returns_substantive_full_parent(corpus):
    db, _, _, _ = corpus
    hits = SectionRetriever(PolicyIndex(db)).retrieve("price reasonableness")
    assert hits
    assert "comparable supplier quotations" in hits[0].text
    assert len(hits[0].text) > 100
    assert hits[0].start == 0 and hits[0].end == len(hits[0].section.text)


def test_unknown_query_has_no_lexical_results_and_context_is_bounded(corpus):
    db, _, _, _ = corpus
    r = SectionRetriever(PolicyIndex(db))
    assert r.retrieve("astronauts nebula galaxies") == []
    hits = r.retrieve("quotations purchase", max_sources=2, max_characters=1000)
    assert len(hits) <= 2 and sum(len(p.text) for p in hits) <= 1000
    assert all(p.text == p.section.text[p.start : p.end] for p in hits)


def test_valid_quotes_generate_citations_with_real_pdf_page(corpus):
    db, _, _, _ = corpus
    passage = next(
        p
        for p in SectionRetriever(PolicyIndex(db)).retrieve("three qualified suppliers")
        if p.document.id == "pdf-policy"
    )
    answer = pipeline.GroundedAnswer(
        sufficient_evidence=True,
        claims=[
            pipeline.Claim(
                text="The fixture requires quotations from three qualified suppliers.",
                support=[
                    pipeline.Support(
                        source_id=1,
                        quote="obtain quotations from three qualified suppliers.",
                    )
                ],
            )
        ],
    )
    result = pipeline.grounded_response(answer, [passage])
    assert result["answer"].endswith("[1]")
    source = result["sources"][0]
    assert source["page"] == "1" and source["section"]
    assert source["document_version_id"] == passage.document.version_id
    evidence = source["evidence"][0]
    assert (
        evidence["quote"] == passage.section.text[evidence["start"] : evidence["end"]]
    )
    assert evidence["locations"][0]["page"] == 1


@pytest.mark.parametrize(
    "text,source_id,quote",
    [
        ("A valid claim.", 99, "obtain quotations from three qualified suppliers."),
        ("A valid claim.", 1, "Invented text that does not occur in the policy."),
        (
            "The threshold is $999,000.",
            1,
            "obtain quotations from three qualified suppliers.",
        ),
        (
            "A claim with forged citation [8].",
            1,
            "obtain quotations from three qualified suppliers.",
        ),
    ],
)
def test_fabricated_quotes_citations_and_amounts_rejected(
    corpus, text, source_id, quote
):
    db, _, _, _ = corpus
    passage = next(
        p
        for p in SectionRetriever(PolicyIndex(db)).retrieve("three qualified suppliers")
        if p.document.id == "pdf-policy"
    )
    answer = pipeline.GroundedAnswer(
        sufficient_evidence=True,
        claims=[
            pipeline.Claim(
                text=text, support=[pipeline.Support(source_id=source_id, quote=quote)]
            )
        ],
    )
    with pytest.raises(ValueError):
        pipeline.grounded_response(answer, [passage])


def test_invalid_model_output_abstains_after_one_repair(corpus, monkeypatch):
    db, _, _, _ = corpus
    monkeypatch.setattr(pipeline, "semantic_rank", None)
    monkeypatch.setattr(pipeline, "rerank", None)
    generate = Mock(side_effect=ValueError("Invalid quote"))
    monkeypatch.setattr(pipeline, "generate_answer", generate)
    result = pipeline.ask("price reasonableness", index_path=db)
    assert result["sources"] == [] and result["answer"] == pipeline.INSUFFICIENT
    assert generate.call_count == 2


def test_review_scope_never_allowed_in_chat(corpus):
    with pytest.raises(ValueError):
        pipeline.ask("pricing", scope=LOCAL_REVIEW_SCOPE, index_path=corpus[0])


def test_archive_hash_pins_current_version_and_blocks_unreviewed_replacement(corpus):
    _, _, manifest, source = corpus
    data = json.loads(manifest.read_text())
    e = next(e for e in data["documents"] if e["id"] == "public-policy")
    old = source / e["filenames"][0]
    e["archived_sha256"] = [e["reviewed_sha256"]]
    current = source / "public-current.docx"
    doc = Document()
    doc.add_paragraph("Current verified content only.")
    doc.save(current)
    e["filenames"].append(current.name)
    e["reviewed_sha256"] = hashlib.sha256(current.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(data))
    bundle = prepare_source_index(source, manifest)
    old_doc = next(d for d in bundle.documents if d.file == old.name)
    assert old_doc.review_status == "archived"
    assert (
        next(d for d in bundle.documents if d.file == current.name).review_status
        == "active"
    )
    current.write_bytes(current.read_bytes() + b"unreviewed")
    with pytest.raises(ValueError, match="changed after review"):
        prepare_source_index(source, manifest)


def test_explicit_form_reference_expands_once_with_exact_source_evidence(corpus):
    db, _, _, _ = corpus
    r = SectionRetriever(PolicyIndex(db))
    hits = r.retrieve("departmental requester price reasonableness")
    linked = [p for p in hits if p.document.id == "support-form" and p.via_reference]
    assert linked
    ref = linked[0].via_reference
    assert ref["relation"] == "references" and ref["quote"] == "SUPPORT FORM"
    original = r.sections[ref["from_section_id"]]
    assert ref["quote"] in original.text
    assert ref["locations"]
    assert len(hits) <= 6


def test_even_verified_conditional_override_is_not_followed(corpus):
    from rag_pipeline.graph.schema import PolicyEdge

    db, bundle, _, _ = corpus
    reference = next(
        edge
        for edge in bundle.edges
        if edge.relation == "references" and edge.evidence[0].quote == "SUPPORT FORM"
    )
    bundle.edges = [edge for edge in bundle.edges if edge.relation != "references"]
    bundle.edges.append(
        PolicyEdge(
            id="test-override",
            source_id=reference.source_id,
            target_id=reference.target_id,
            relation="overrides",
            evidence=reference.evidence,
            conditions={"test_only": True},
            verified_by="fixture-reviewer",
            verified_at="2026-01-01T00:00:00Z",
        )
    )
    write_source_index(bundle, db)
    hits = SectionRetriever(PolicyIndex(db)).retrieve(
        "departmental requester price reasonableness"
    )
    assert hits
    assert all(p.document.id != "support-form" for p in hits)


def test_named_unavailable_source_cannot_be_substituted_with_another_policy(
    corpus, monkeypatch
):
    from rag_pipeline.retriever.section_retriever import requested_sources_available

    db, _, manifest, _ = corpus
    docs = PolicyIndex(db).documents()
    assert requested_sources_available("Explain public-policy", docs, manifest)
    assert not requested_sources_available(
        "What does internal-policy say about pricing?", docs, manifest
    )
    assert not requested_sources_available("Explain draft-policy", docs, manifest)
    assert requested_sources_available(
        "Explain internal-policy",
        PolicyIndex(
            db, AccessScope(classifications=("public", "internal"))
        ).documents(),
        manifest,
    )
    assert not requested_sources_available(
        "What does the Federal Funds Checklist require?", docs
    )
    assert not requested_sources_available("Explain the SSPR FAQ", docs)
    monkeypatch.setattr(
        pipeline, "semantic_rank", Mock(side_effect=AssertionError("Must not rank"))
    )
    monkeypatch.setattr(
        pipeline,
        "generate_answer",
        Mock(side_effect=AssertionError("Must not generate")),
    )
    assert (
        pipeline.ask("What does the Federal Funds Checklist require?", index_path=db)[
            "sources"
        ]
        == []
    )


def test_real_api_returns_grounded_page_citation_from_scoped_source_index(
    corpus, monkeypatch
):
    import sys
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.auth.dependencies import require_approved_user

    db, _, _, _ = corpus
    monkeypatch.setattr(pipeline, "semantic_rank", None)
    monkeypatch.setattr(pipeline, "rerank", None)

    def generate(question, passages, *args, **kwargs):
        number = next(
            i for i, p in enumerate(passages, 1) if p.document.id == "pdf-policy"
        )
        return pipeline.GroundedAnswer(
            sufficient_evidence=True,
            claims=[
                pipeline.Claim(
                    text="The fixture requires quotations from three qualified suppliers.",
                    support=[
                        pipeline.Support(
                            source_id=number,
                            quote="obtain quotations from three qualified suppliers.",
                        )
                    ],
                )
            ],
        )

    monkeypatch.setattr(pipeline, "generate_answer", generate)
    actual_ask = pipeline.ask
    monkeypatch.setitem(
        sys.modules,
        "backend.rag.pipeline",
        SimpleNamespace(
            ask=lambda q, think, scope: actual_ask(
                q, think=think, scope=scope, index_path=db
            )
        ),
    )
    app.dependency_overrides[require_approved_user] = lambda: UserProfile(
        uid="fixture", email="fixture@ucsc.edu", is_approved=True, clearance="none"
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/ask", json={"question": "How many qualified supplier quotations?"}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["sources"][0]["document_id"] == "pdf-policy"
        assert data["sources"][0]["page"] == "1"
        assert f"[{data['sources'][0]['citation_id']}]" in data["answer"]
        assert data["sources"][0]["evidence"][0]["locations"][0]["format"] == "pdf"
    finally:
        app.dependency_overrides.pop(require_approved_user, None)


def test_typographic_quote_equivalence_preserves_original_offsets():
    text = "Source: Non‐Federal purchases must use the supplier’s documented price."
    quote = "Non-Federal purchases must use the supplier's documented price."
    start, end = pipeline._quote_span(quote, text)
    assert (
        text[start:end]
        == "Non‐Federal purchases must use the supplier’s documented price."
    )
    with pytest.raises(ValueError):
        pipeline._quote_span(
            "Non-Federal purchases may use the supplier's documented price.", text
        )


def test_policy_identifier_is_not_mistaken_for_a_fabricated_threshold():
    assert pipeline._numbers("BUS-43 requires $100,000 annually.") == {"100000"}


def test_discontinuous_pdf_clause_requires_separate_exact_support_spans(corpus):
    from rag_pipeline.retriever.section_retriever import Passage

    _, _, manifest, source = corpus
    path = source / "page-boundary.pdf"
    pdf = canvas.Canvas(str(path))
    first = "Awards up to $250,000 may go to"
    second = "certified firms without competitive bidding."
    pdf.drawString(30, 780, first)
    pdf.drawString(30, 30, "1 of 2")
    pdf.showPage()
    pdf.drawString(30, 790, "RUNNING POLICY HEADER")
    pdf.drawString(30, 750, second)
    pdf.save()
    data = json.loads(manifest.read_text())
    data["documents"].append(
        dict(
            id="page-boundary",
            filenames=[path.name],
            title="Boundary fixture",
            access_classification="public",
            review_status="active",
            reviewed_by="fixture",
            reviewed_at="2026-01-01T00:00:00Z",
            reviewed_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
    )
    manifest.write_text(json.dumps(data))
    bundle = prepare_source_index(source, manifest)
    doc = next(d for d in bundle.documents if d.id == "page-boundary")
    section = next(
        s
        for s in bundle.sections
        if s.document_version_id == doc.version_id
        and s.parent_section_id is None
        and s.kind == "body"
    )
    passage = Passage(doc, section, 0, len(section.text))
    text = first + " " + second
    joined = pipeline.GroundedAnswer(
        sufficient_evidence=True,
        claims=[
            pipeline.Claim(
                text=text, support=[pipeline.Support(source_id=1, quote=text)]
            )
        ],
    )
    with pytest.raises(ValueError, match="absent"):
        pipeline.grounded_response(joined, [passage])
    separate = pipeline.GroundedAnswer(
        sufficient_evidence=True,
        claims=[
            pipeline.Claim(
                text=text,
                support=[
                    pipeline.Support(source_id=1, quote=first),
                    pipeline.Support(source_id=1, quote=second),
                ],
            )
        ],
    )
    result = pipeline.grounded_response(separate, [passage])
    assert result["sources"][0]["page"] == "1-2"
    assert [e["quote"] for e in result["sources"][0]["evidence"]] == [first, second]
    assert result["sources"][0]["evidence"][0]["locations"][0]["page"] == 1
    assert result["sources"][0]["evidence"][1]["locations"][0]["page"] == 2


def test_numbered_spans_cover_the_context_and_cannot_fabricate_evidence(corpus):
    db, _, _, _ = corpus
    p = next(
        p
        for p in SectionRetriever(PolicyIndex(db)).retrieve("three qualified suppliers")
        if p.document.id == "pdf-policy"
    )
    options = pipeline.quote_options(p)
    assert "".join("".join(o["text"].split()) for o in options) == "".join(
        p.text.split()
    )
    option = next(o for o in options if "three qualified suppliers" in o["text"])
    generated = pipeline.GroundedAnswer(
        sufficient_evidence=True,
        claims=[
            pipeline.Claim(
                text="The fixture requires quotations from three qualified suppliers.",
                support=[pipeline.Support(source_id=1, quote_id=option["quote_id"])],
            )
        ],
    )
    result = pipeline.grounded_response(generated, [p])
    evidence = result["sources"][0]["evidence"][0]
    assert evidence["quote"] == p.section.text[evidence["start"] : evidence["end"]]
    assert evidence["quote"] == option["text"]
    assert result["sources"][0]["page"] == "1"
    generated.claims[0].support[0].quote_id = 9999
    with pytest.raises(ValueError, match="span identifier"):
        pipeline.grounded_response(generated, [p])
    with pytest.raises(ValueError):
        pipeline.Support(
            source_id=1, quote_id=1, quote="An ambiguous duplicate quote reference."
        )
