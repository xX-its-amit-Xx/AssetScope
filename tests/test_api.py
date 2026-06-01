import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from assetscope.api import main as apimain
from assetscope.api.main import app
from assetscope.config import Settings

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert body["backend"] in ("anthropic", "local")
    assert "model" in body and "llm_configured" in body
    assert body["anthropic_configured"] is False  # no key in tests


def test_api_key_auth(monkeypatch):
    # With keys configured, the dependency rejects a missing/wrong key and
    # accepts a correct one. (Disabled when no keys are set.)
    monkeypatch.setattr(apimain, "get_settings", lambda: Settings(api_keys="secret"))
    with pytest.raises(HTTPException):
        apimain.require_api_key(x_api_key=None)
    with pytest.raises(HTTPException):
        apimain.require_api_key(x_api_key="wrong")
    apimain.require_api_key(x_api_key="secret")  # no raise


def test_tools_listing():
    r = client.get("/tools")
    assert r.status_code == 200
    tools = r.json()
    names = {t["name"] for t in tools}
    assert names == {
        "search_clinical_trials", "search_open_targets", "search_chembl",
        "search_literature", "search_fda", "retrieve",
    }
    for t in tools:
        assert t["input_schema"]["type"] == "object"
