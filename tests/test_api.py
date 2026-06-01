from fastapi.testclient import TestClient

from assetscope.api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert body["anthropic_configured"] is False  # no key in tests


def test_tools_listing():
    r = client.get("/tools")
    assert r.status_code == 200
    tools = r.json()
    names = {t["name"] for t in tools}
    assert names == {
        "search_clinical_trials", "search_open_targets", "search_chembl",
        "search_literature", "retrieve",
    }
    for t in tools:
        assert t["input_schema"]["type"] == "object"
