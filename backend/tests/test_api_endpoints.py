"""Tests for FastAPI endpoints in backend/app.py.

The module-level RAGSystem init and StaticFiles mount are patched out via
conftest.py's app_module fixture, so tests run without ChromaDB, an
Anthropic API key, or a frontend build.
"""


# ── POST /api/query ───────────────────────────────────────────────────────


def test_query_returns_answer_and_sources(api_client, mock_rag):
    mock_rag.session_manager.create_session.return_value = "sess-1"
    mock_rag.query.return_value = (
        "MCP is the Model Context Protocol.",
        [{"title": "Test Course: MCP Basics - Lesson 0", "url": "https://example.com"}],
    )

    resp = api_client.post("/api/query", json={"query": "What is MCP?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "MCP is the Model Context Protocol."
    assert body["session_id"] == "sess-1"
    assert body["sources"][0]["title"] == "Test Course: MCP Basics - Lesson 0"


def test_query_creates_session_when_none_provided(api_client, mock_rag):
    mock_rag.session_manager.create_session.return_value = "new-sess"
    mock_rag.query.return_value = ("ok", [])

    resp = api_client.post("/api/query", json={"query": "hello"})

    assert resp.status_code == 200
    mock_rag.session_manager.create_session.assert_called_once()
    assert resp.json()["session_id"] == "new-sess"


def test_query_uses_provided_session_id(api_client, mock_rag):
    mock_rag.query.return_value = ("ok", [])

    resp = api_client.post("/api/query", json={"query": "hello", "session_id": "existing-sess"})

    assert resp.status_code == 200
    mock_rag.session_manager.create_session.assert_not_called()
    assert resp.json()["session_id"] == "existing-sess"


def test_query_returns_500_on_rag_error(api_client, mock_rag):
    mock_rag.session_manager.create_session.return_value = "sess"
    mock_rag.query.side_effect = RuntimeError("database error")

    resp = api_client.post("/api/query", json={"query": "What is MCP?"})

    assert resp.status_code == 500
    assert "database error" in resp.json()["detail"]


def test_query_missing_query_field_returns_422(api_client, mock_rag):
    resp = api_client.post("/api/query", json={})

    assert resp.status_code == 422


# ── GET /api/courses ──────────────────────────────────────────────────────


def test_courses_returns_stats(api_client, mock_rag):
    mock_rag.get_course_analytics.return_value = {
        "total_courses": 3,
        "course_titles": ["Course A", "Course B", "Course C"],
    }

    resp = api_client.get("/api/courses")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_courses"] == 3
    assert body["course_titles"] == ["Course A", "Course B", "Course C"]


def test_courses_returns_500_on_analytics_error(api_client, mock_rag):
    mock_rag.get_course_analytics.side_effect = RuntimeError("chroma error")

    resp = api_client.get("/api/courses")

    assert resp.status_code == 500
    assert "chroma error" in resp.json()["detail"]


# ── GET / (static file mount) ─────────────────────────────────────────────


def test_root_static_route_is_mounted(api_client):
    """The static file mount at '/' is registered.

    In tests StaticFiles is replaced by _StubStaticFiles (see conftest.py),
    so real frontend serving is not exercised here — only that the route is
    wired up and reachable (not 404).
    """
    resp = api_client.get("/")

    assert resp.status_code != 404


# ── DELETE /api/session/{session_id} ─────────────────────────────────────


def test_delete_session_returns_ok(api_client, mock_rag):
    resp = api_client.delete("/api/session/sess-abc")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    mock_rag.session_manager.delete_session.assert_called_once_with("sess-abc")
