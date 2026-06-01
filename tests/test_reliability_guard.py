from assetscope.guards import CitationLedger, ReliabilityGuard
from assetscope.models import Asset, Citation, Claim, ClaimStatus, Landscape, SourceType


def _ledger():
    led = CitationLedger()
    led.register(Citation(id="NCT1", source_type=SourceType.CLINICAL_TRIALS, source_id="NCT1", url="u"))
    led.register(Citation(id="100", source_type=SourceType.PUBMED, source_id="100", url="u"))
    return led


def _landscape():
    return Landscape(
        query="q",
        assets=[
            Asset(asset_name="DrugA", source_ids=["NCT1"]),
            Asset(asset_name="DrugB", source_ids=["GHOST"]),
        ],
        claims=[
            Claim(id="c1", text="A works", source_ids=["NCT1", "100"]),
            Claim(id="c2", text="B works", source_ids=["GHOST"]),
            Claim(id="c3", text="C works", source_ids=["NCT1", "GHOST"]),
        ],
    )


def test_drops_unsupported_claims():
    cleaned, report = ReliabilityGuard(drop_unsupported=True).apply(_landscape(), _ledger())
    texts = {c.text for c in cleaned.claims}
    assert "A works" in texts and "C works" in texts  # both have >=1 valid source
    assert "B works" not in texts                       # only GHOST -> dropped
    assert report.dropped_claims == 1
    assert cleaned.dropped_claims == 1
    # c3 keeps only the resolvable source
    c3 = next(c for c in cleaned.claims if c.text == "C works")
    assert c3.source_ids == ["NCT1"]
    assert "GHOST" in c3.guard_note
    # coverage = supported / ALL submitted claims (dropped counts against it): 2 of 3
    assert round(report.citation_coverage, 3) == 0.667


def test_flags_unsupported_asset_rows():
    cleaned, report = ReliabilityGuard(drop_unsupported=True).apply(_landscape(), _ledger())
    a = {x.asset_name: x for x in cleaned.assets}
    assert a["DrugA"].verified is True and a["DrugA"].source_ids == ["NCT1"]
    assert a["DrugB"].verified is False
    assert a["DrugB"].unresolved_source_ids == ["GHOST"]
    assert report.flagged_assets == 1
    # final citations contain only used + resolvable sources
    ids = {c.id for c in cleaned.citations}
    assert "GHOST" not in ids and "NCT1" in ids


def test_flag_mode_keeps_unverified():
    cleaned, report = ReliabilityGuard(drop_unsupported=False).apply(_landscape(), _ledger())
    statuses = {c.text: c.status for c in cleaned.claims}
    assert statuses["B works"] == ClaimStatus.UNVERIFIED
    assert report.unverified_claims == 1
    assert "unverified" in cleaned.narrative.lower()
