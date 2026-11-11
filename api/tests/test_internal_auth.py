"""INTERNAL_TOKEN 开启后拒绝无令牌；/health 仍公开。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_open_without_token(monkeypatch):
    monkeypatch.delenv("INTERNAL_TOKEN", raising=False)
    monkeypatch.delenv("DATA_INTERNAL_TOKEN", raising=False)
    from main import app

    client = TestClient(app)
    assert client.get("/health").status_code == 200


def test_dashboard_requires_token_when_configured(monkeypatch):
    monkeypatch.setenv("INTERNAL_TOKEN", "secret-test-token")
    # 重新导入中间件读环境；TestClient 用已加载 app，直接改 env 后中间件每次请求读 env
    from main import app

    client = TestClient(app)
    denied = client.get("/api/dashboard")
    assert denied.status_code == 401
    ok_health = client.get("/health")
    assert ok_health.status_code == 200
    allowed = client.get("/api/dashboard", headers={"X-Internal-Token": "secret-test-token"})
    # 无库时可能 500，但不应再是 401
    assert allowed.status_code != 401
