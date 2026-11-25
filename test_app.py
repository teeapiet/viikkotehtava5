import json

import pytest
import requests

import app as app_module
import db


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self):
        yield json.dumps({"message": {"content": "Hei!"}, "done": True}).encode()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DB_NAME", raising=False)
    db._memory.clear()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_index_and_prefix(client):
    response = client.get("/", headers={"X-Forwarded-Prefix": "/viikko5"})
    assert response.status_code == 200
    assert b'id="chat-form"' in response.data
    assert b"/viikko5/static/app.js" in response.data
    assert b'data-base="/viikko5"' in response.data


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.data.strip()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"session_id": "../etc", "message": "Moi"},
        {"session_id": "test-session", "message": ""},
        {"session_id": "test-session", "message": "x" * 2001},
    ],
)
def test_invalid_input(client, payload):
    assert client.post("/api/chat", json=payload).status_code == 400


def test_chat_and_history(client, monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(app_module.requests, "post", fake_post)
    db.save_message("test-session", "user", "Nimeni on Aino")
    db.save_message("test-session", "assistant", "Hei Aino")

    response = client.post(
        "/api/chat",
        json={"session_id": "test-session", "message": "Moi"},
    )
    events = [json.loads(line) for line in response.get_data(as_text=True).splitlines()]

    assert response.status_code == 200
    assert events == [{"token": "Hei!"}, {"done": True}]
    assert [item["role"] for item in captured["json"]["messages"]] == [
        "system", "user", "assistant", "user"
    ]
    history = client.get("/api/history/test-session").get_json()
    assert history[-1] == {"role": "assistant", "content": "Hei!"}


def test_ollama_failure(client, monkeypatch):
    def fail(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(app_module.requests, "post", fail)
    response = client.post(
        "/api/chat",
        json={"session_id": "test-session", "message": "Moi"},
    )
    assert '"error"' in response.get_data(as_text=True)
    assert db.get_history("test-session") == [{"role": "user", "content": "Moi"}]


def test_database_failure(client, monkeypatch):
    def fail(*args, **kwargs):
        raise db.DatabaseError("database offline")

    monkeypatch.setattr(db, "save_message", fail)
    response = client.post(
        "/api/chat",
        json={"session_id": "test-session", "message": "Moi"},
    )
    assert response.status_code == 503


def test_delete_only_selected_history(client):
    db.save_message("test-session", "user", "Moi")
    db.save_message("other-session", "user", "Säilytä tämä")
    response = client.delete("/api/history/test-session")
    assert response.status_code == 200
    assert db.get_history("test-session") == []
    assert len(db.get_history("other-session")) == 1


def test_detailed_health_failure(client, monkeypatch):
    def fail(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(app_module.requests, "get", fail)
    response = client.get("/health?details=1")
    assert response.status_code == 503
    assert response.get_json()["ollama"] is False
