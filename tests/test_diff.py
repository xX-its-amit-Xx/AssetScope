from fastapi.testclient import TestClient

from assetscope.api.main import app
from assetscope.diff import diff_landscapes
from assetscope.models import Asset, Landscape
from assetscope.storage import get_landscape_store

client = TestClient(app)


def test_diff_landscapes_added_removed_changed():
    old = Landscape(query="q", assets=[
        Asset(asset_name="Sotorasib", phase="Phase 2", company="Amgen", source_ids=["NCT1"]),
        Asset(asset_name="OldDrug", phase="Phase 1"),
    ])
    new = Landscape(query="q", assets=[
        Asset(asset_name="Sotorasib", phase="Approved", company="Amgen", source_ids=["NCT1", "NCT2"]),
        Asset(asset_name="Adagrasib", phase="Approved"),
    ])
    d = diff_landscapes(old, new)
    assert d["n_added"] == 1 and d["added"][0]["asset_name"] == "Adagrasib"
    assert d["n_removed"] == 1 and d["removed"][0]["asset_name"] == "OldDrug"
    assert d["n_changed"] == 1
    ch = d["changed"][0]
    assert ch["asset_name"] == "Sotorasib"
    assert ch["changes"]["phase"] == {"old": "Phase 2", "new": "Approved"}
    assert "NCT2" in ch["new_source_ids"]


def test_diff_matches_by_shared_source_when_name_changes():
    # Different display names but a shared source id -> matched (not add/remove).
    old = Landscape(query="q", assets=[Asset(asset_name="AMG 510", source_ids=["NCT1"])])
    new = Landscape(query="q", assets=[
        Asset(asset_name="Sotorasib (Lumakras)", phase="Approved", source_ids=["NCT1"])])
    d = diff_landscapes(old, new)
    assert d["n_added"] == 0 and d["n_removed"] == 0
    assert len(d["changed"]) == 1  # phase "" -> "Approved" on the source-matched asset


def test_diff_endpoint_autopicks_prior():
    store = get_landscape_store()
    oid = store.save(Landscape(query="diff-endpoint-query", assets=[Asset(asset_name="X", phase="Phase 1")]))
    nid = store.save(Landscape(query="diff-endpoint-query",
                               assets=[Asset(asset_name="X", phase="Phase 3"), Asset(asset_name="Y")]))
    r = client.get(f"/landscapes/{nid}/diff")
    assert r.status_code == 200
    body = r.json()
    assert body["old_id"] == oid and body["new_id"] == nid
    assert body["n_added"] == 1 and body["n_changed"] == 1
    assert client.get(f"/landscapes/{nid}/diff?against={oid}").status_code == 200
    # a query with no prior run -> 404
    solo = store.save(Landscape(query=f"unique-{nid}"))
    assert client.get(f"/landscapes/{solo}/diff").status_code == 404
