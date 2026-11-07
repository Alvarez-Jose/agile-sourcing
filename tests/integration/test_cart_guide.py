"""Cart extraction inputs remain untrusted; form checks need verified source scope."""
import pytest
from pydantic import ValidationError

from backend.api import cart_routes
from backend.api.cart_routes import CartRequest, guide
from tests.integration.test_auth import server, IDENTITY, HEADERS


def payload(amount="33.24", **changes):
    body = {"items": [{"description": "Demo item", "supplier": "Demo supplier", "quantity": "1",
                       "unit_price": amount, "line_total": amount}], "currency": "USD", "subtotal": amount,
            "tax": "0.00", "shipping": "0.00", "handling": "0.00", "total": amount,
            "funding": "non_federal", "reviewed": True, "single_purchase": True}
    return {**body, **changes}


@pytest.mark.parametrize("funding,amount,required", [
    ("non_federal", "99999.99", False), ("non_federal", "100000.00", True),
    ("federal_contract", "14999.99", False), ("federal_contract", "15000.00", True),
    ("federal_grant", "49999.99", False), ("federal_grant", "50000.00", True),
])
def test_source_threshold_boundaries(funding, amount, required):
    result = guide(CartRequest(**payload(amount, funding=funding)), [])
    assert result["status"] == "checked"
    assert result["sspr_required_by_threshold"] is required
    assert bool(result["forms"]) is required
    assert result["llm_called"] is False


def test_non_federal_excludes_tax_and_federal_includes_tax():
    body = payload("14900.00", tax="100.00", total="15000.00")
    assert guide(CartRequest(**body), [])["assessed_amount"] == "14900.00"
    body["funding"] = "federal_contract"
    result = guide(CartRequest(**body), [])
    assert result["assessed_amount"] == "15000.00"
    assert result["sspr_required_by_threshold"] is True


@pytest.mark.parametrize("changes", [
    {"funding": "unknown"}, {"funding": "mixed"}, {"reviewed": False},
    {"single_purchase": False}, {"shipping": None}, {"handling": None},
    {"tax": None, "funding": "federal_contract"},
])
def test_missing_context_never_produces_a_form_decision(changes):
    result = guide(CartRequest(**payload(**changes)), [])
    assert result["status"] == "needs_details"
    assert result["questions"] and result["forms"] == []
    assert "sspr_required_by_threshold" not in result


@pytest.mark.parametrize("changes", [
    {"subtotal": "44.00"}, {"total": "44.00"}, {"currency": "EUR"},
    {"tax": "NaN"}, {"subtotal": "-1"}, {"reviewed": "true"},
    {"clearance": "admin"}, {"subtotal": "33.241"},
])
def test_bad_amounts_and_permission_overrides_are_rejected(changes):
    with pytest.raises(ValidationError):
        CartRequest(**payload(**changes))


def test_multiple_suppliers_are_not_combined_into_one_threshold_decision():
    body = payload("66.48")
    item = payload()["items"][0]
    body["items"] = [item, {**item, "supplier": "Another supplier"}]
    result = guide(CartRequest(**body), [])
    assert result["status"] == "needs_details"


def test_public_request_cannot_read_sources_or_run_models(server, monkeypatch):
    read = lambda: pytest.fail("Unauthenticated request reached policy sources")
    monkeypatch.setattr(cart_routes, "reviewed_sources", read)
    response = server.client.post("/api/cart/guide", json=payload())
    assert response.status_code == 401
    response = server.client.post("/api/cart/guide", headers=HEADERS, json=payload())
    assert response.status_code == 403
    server.pipeline.assert_not_called()


def test_approved_cart_uses_separate_source_backed_route(server, monkeypatch):
    server.records[IDENTITY["uid"]] = {"is_approved": True}
    monkeypatch.setattr(cart_routes, "reviewed_sources", lambda: [{"citation_id": 1}])
    response = server.client.post("/api/cart/guide", headers=HEADERS, json=payload())
    assert response.status_code == 200
    assert response.json()["sspr_required_by_threshold"] is False
    assert response.json()["sources"] == [{"citation_id": 1}]
    server.pipeline.assert_not_called()


def test_unavailable_reviewed_sources_fail_closed(server, monkeypatch):
    server.records[IDENTITY["uid"]] = {"is_approved": True}
    def changed():
        raise ValueError("Changed bytes")
    monkeypatch.setattr(cart_routes, "reviewed_sources", changed)
    response = server.client.post("/api/cart/guide", headers=HEADERS, json=payload())
    assert response.status_code == 503
    server.pipeline.assert_not_called()


def test_local_reviewed_sources_are_only_the_two_pinned_pdfs():
    if not (cart_routes.ROOT / "data/raw_policies/SSPR_Official_UCSC_2025-12.pdf").exists():
        pytest.skip("Reviewed source PDFs not installed")
    sources = cart_routes.reviewed_sources()
    assert len(sources) == 2
    assert [s["page"] for s in sources] == ["1", "9"]
    assert "including tax and shipping" in sources[0]["evidence"][0]["quote"]
