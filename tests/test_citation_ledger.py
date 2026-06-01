from assetscope.guards import CitationLedger
from assetscope.models import Citation, EvidenceItem, SourceType, ToolResult


def _cit(cid, st=SourceType.CLINICAL_TRIALS):
    return Citation(id=cid, source_type=st, source_id=cid, url=f"http://x/{cid}", title=cid)


def test_register_and_resolve():
    ledger = CitationLedger()
    ledger.register(_cit("NCT1"))
    ledger.register(_cit("100", SourceType.PUBMED))
    ok, missing = ledger.resolve(["NCT1", "100", "GHOST"])
    assert ok == ["NCT1", "100"]
    assert missing == ["GHOST"]
    assert ledger.has("NCT1") and not ledger.has("GHOST")
    assert len(ledger) == 2


def test_register_result_dedup_and_used():
    ledger = CitationLedger()
    result = ToolResult(
        tool="search_clinical_trials",
        items=[EvidenceItem(citation=_cit("NCT1"), content="trial")],
    )
    added = ledger.register_result(result)
    assert added == 1
    # registering same id again does not grow the ledger
    ledger.register_result(result)
    assert len(ledger) == 1
    # used() only reflects cited sources
    assert ledger.used() == []
    ledger.note_reference("NCT1", "c1")
    assert [c.id for c in ledger.used()] == ["NCT1"]
