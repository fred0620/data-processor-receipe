"""本機服務的安全檢查。新增 API 時，至少確認它也受到這些保護。"""
from urllib.parse import quote

import dataprocessor.server as server


def test_rejects_foreign_host_and_origin():
    """擋 DNS rebinding 和其他網站對本機服務發出的請求。"""
    client = server.app.test_client()
    assert client.get("/api/status").status_code == 200
    assert client.get("/api/status", headers={"Host": "evil.example:8765"}).status_code == 403
    assert client.post("/api/heartbeat?client=a", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/heartbeat?client=a", headers={"Origin": "null"}).status_code == 403
    assert client.get("/api/status", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    ok = client.post("/api/heartbeat?client=a", headers={"Origin": "http://localhost", "Sec-Fetch-Site": "same-origin"})
    assert ok.status_code == 200
    server._clients.pop("a", None)


def test_security_headers_and_ping():
    client = server.app.test_client()
    page = client.get("/")
    assert "default-src 'self'" in page.headers["Content-Security-Policy"]
    assert page.headers["X-Frame-Options"] == "DENY"
    ping = client.get("/api/ping")
    assert ping.headers["Cache-Control"] == "no-store"
    assert str(server.paths.HOME) not in ping.get_data(as_text=True)  # 不外洩本機路徑


def test_errors_do_not_leak_details():
    client = server.app.test_client()
    response = client.post("/api/runs", data="not json", content_type="application/json")
    assert response.status_code == 400
    assert "Traceback" not in response.get_data(as_text=True)


def test_only_known_guides_are_served():
    client = server.app.test_client()
    assert client.get("/manual").status_code == 302
    for name in sorted(server.paths.GUIDES):
        assert client.get(f"/docs/{quote(name)}").status_code == 200, name
    assert client.get("/docs/pyproject.toml").status_code == 404
    assert client.get("/docs/..%2Fpyproject.toml").status_code == 404
