import json

import pytest
from fastapi.testclient import TestClient

from helicon.db import init_db


TOKEN = "test-remote-mcp-token-with-32-characters"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "helicon.db")
    init_db(db_path).close()

    monkeypatch.setenv("HELICON_MCP_TOKEN", TOKEN)
    monkeypatch.delenv("HELICON_PASSWORD", raising=False)

    import helicon.api.app as app_module
    monkeypatch.setattr(app_module, "load_config", lambda: {"db_path": db_path})
    with TestClient(app_module.create_app()) as test_client:
        yield test_client


def _post(client, payload, token=TOKEN):
    return client.post(
        "/mcp",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


def test_remote_mcp_is_disabled_without_dedicated_token(tmp_path, monkeypatch):
    db_path = str(tmp_path / "helicon.db")
    init_db(db_path).close()
    monkeypatch.delenv("HELICON_MCP_TOKEN", raising=False)

    import helicon.api.app as app_module
    monkeypatch.setattr(app_module, "load_config", lambda: {"db_path": db_path})
    with TestClient(app_module.create_app()) as test_client:
        response = test_client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})

    assert response.status_code == 503
    assert "disabled" in response.json()["error"]


def test_remote_mcp_rejects_short_token_configuration(tmp_path, monkeypatch):
    db_path = str(tmp_path / "helicon.db")
    init_db(db_path).close()
    monkeypatch.setenv("HELICON_MCP_TOKEN", "too-short")

    import helicon.api.app as app_module
    monkeypatch.setattr(app_module, "load_config", lambda: {"db_path": db_path})
    with TestClient(app_module.create_app()) as test_client:
        response = test_client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})

    assert response.status_code == 503
    assert "at least 32 characters" in response.json()["error"]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
def test_remote_mcp_requires_exact_bearer_token(client, headers):
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        headers=headers,
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"error": "unauthorized"}


def test_remote_mcp_initialize_and_safe_tool_list(client):
    initialized = _post(client, {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
    })
    assert initialized.status_code == 200
    assert initialized.json()["result"]["serverInfo"]["name"] == "helicon"

    listed = _post(client, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert "helicon_context" in names
    assert "helicon_guard" in names
    assert "helicon_flag" in names
    assert names.isdisjoint({"helicon_compile", "helicon_triage", "helicon_consolidate"})


def test_remote_mcp_calls_existing_tool_implementation(client):
    response = _post(client, {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "helicon_health", "arguments": {}},
    })

    assert response.status_code == 200
    rpc = response.json()
    assert rpc["result"]["isError"] is False
    health = json.loads(rpc["result"]["content"][0]["text"])
    assert health["total"] == 0


def test_remote_mcp_rejects_local_maintenance_tools(client, tmp_path):
    output = tmp_path / "remote-write"
    response = _post(client, {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "helicon_compile",
            "arguments": {"output_dir": str(output)},
        },
    })

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32602
    assert not output.exists()


def test_remote_mcp_accepts_notifications_without_response_body(client):
    response = _post(client, {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    })

    assert response.status_code == 202
    assert response.content == b""


def test_remote_mcp_returns_json_rpc_parse_error(client):
    response = client.post(
        "/mcp",
        content=b"{not-json",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == -32700


def test_remote_mcp_rejects_oversized_request_before_reading_it(client):
    response = client.post(
        "/mcp",
        content=b"{}",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "Content-Length": str(1024 * 1024 + 1),
        },
    )

    assert response.status_code == 413
