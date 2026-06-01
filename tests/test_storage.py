from fastapi.testclient import TestClient

from assetscope.api.main import app
from assetscope.models import Asset, Landscape
from assetscope.storage import InMemoryLandscapeStore, get_landscape_store

client = TestClient(app)


def test_inmemory_store_save_list_get():
    s = InMemoryLandscapeStore()
    ls = Landscape(query="oral GLP-1 in obesity", assets=[Asset(asset_name="Tirzepatide")], tool_calls=5)
    id_ = s.save(ls, backend="local", model="qwen2.5:3b")
    got = s.get(id_)
    assert got is not None and got["query"] == "oral GLP-1 in obesity"
    rows = s.list()
    assert rows[0]["id"] == id_
    assert rows[0]["n_assets"] == 1 and rows[0]["tool_calls"] == 5
    assert s.get("nonexistent") is None


def test_landscape_endpoints_save_list_get_404():
    # The API and this test share the process-wide store (in-memory without a DB).
    store = get_landscape_store()
    sid = store.save(Landscape(query="BTK inhibitors in CLL", tool_calls=2), backend="local", model="m")

    r = client.get("/landscapes")
    assert r.status_code == 200
    assert any(item["id"] == sid for item in r.json())

    r2 = client.get(f"/landscapes/{sid}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["id"] == sid
    assert body["landscape"]["query"] == "BTK inhibitors in CLL"

    assert client.get("/landscapes/does-not-exist").status_code == 404
