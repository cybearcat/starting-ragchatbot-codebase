"""Shared fixtures for the backend test suite.

Two kinds of fixtures live here:

1. Sample domain objects (Course / CourseChunk) used to seed real vector stores.
2. A `seeded_store_factory` that builds a *real* VectorStore in a throwaway temp
   ChromaDB directory. This never touches the app's persistent ./chroma_db, so the
   tests are safe to run while the app is live.
3. Factories that build mock Anthropic API responses (text turns and tool-use turns)
   so the AI loop can be exercised without a network call or API key.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Backend modules use flat imports (`from vector_store import ...`). The pytest
# config already puts `backend` on sys.path; this is a belt-and-suspenders guard
# so the suite also runs if invoked without that config.
BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient

from models import Course, Lesson, CourseChunk
from vector_store import VectorStore
from config import config


@pytest.fixture
def sample_course():
    """A small course with two lessons, mirroring the real document format."""
    return Course(
        title="Test Course: MCP Basics",
        course_link="https://example.com/mcp",
        instructor="Ada Lovelace",
        lessons=[
            Lesson(lesson_number=0, title="Introduction",
                   lesson_link="https://example.com/mcp/0"),
            Lesson(lesson_number=1, title="Servers and Clients",
                   lesson_link="https://example.com/mcp/1"),
        ],
    )


@pytest.fixture
def sample_chunks():
    """Content chunks whose text clearly answers a 'what is MCP?' query."""
    title = "Test Course: MCP Basics"
    return [
        CourseChunk(
            content="MCP is the Model Context Protocol, a standard for connecting "
                    "external tools to language models.",
            course_title=title, lesson_number=0, chunk_index=0,
        ),
        CourseChunk(
            content="An MCP server exposes tools and resources that an MCP client "
                    "can call during a conversation.",
            course_title=title, lesson_number=1, chunk_index=1,
        ),
    ]


@pytest.fixture
def seeded_store_factory(tmp_path_factory, sample_course, sample_chunks):
    """Return `make(max_results) -> VectorStore`, seeded with the sample course.

    Each call gets a fresh temp ChromaDB directory, so nothing collides with the
    app's live ./chroma_db. `max_results` is the knob under test — the real bug is
    that the app passes 0 here via config.MAX_RESULTS.
    """
    def _make(max_results):
        path = tmp_path_factory.mktemp("chroma")
        store = VectorStore(str(path), config.EMBEDDING_MODEL, max_results=max_results)
        store.add_course_metadata(sample_course)
        store.add_course_content(sample_chunks)
        return store

    return _make


@pytest.fixture
def text_response():
    """Factory for a mock Anthropic response that is a plain text answer."""
    def _make(text):
        block = MagicMock()
        block.type = "text"
        block.text = text
        resp = MagicMock()
        resp.stop_reason = "end_turn"
        resp.content = [block]
        return resp

    return _make


@pytest.fixture
def tool_use_response():
    """Factory for a mock Anthropic response that requests a tool call.

    The `.type` attribute is set explicitly: a bare MagicMock().type is itself a
    Mock, so `content_block.type == "tool_use"` would be False and the tool would
    silently never run.
    """
    def _make(name, tool_input, tool_id="toolu_test_1"):
        block = MagicMock()
        block.type = "tool_use"
        block.name = name
        block.input = tool_input
        block.id = tool_id
        resp = MagicMock()
        resp.stop_reason = "tool_use"
        resp.content = [block]
        return resp

    return _make


@pytest.fixture
def empty_content_response():
    """Factory for a mock response with no content blocks.

    Newer models can return an empty content array on a no-tools synthesis turn;
    this exercises the safe text extraction path (no IndexError).
    """
    def _make():
        resp = MagicMock()
        resp.stop_reason = "end_turn"
        resp.content = []
        return resp

    return _make


# ── API endpoint test helpers ──────────────────────────────────────────────


class _StubStaticFiles:
    """Minimal ASGI stub replacing StaticFiles for tests.

    A real class (not a MagicMock) is required because app.py defines
    `class DevStaticFiles(StaticFiles)` — subclassing a MagicMock instance
    raises TypeError. The stub also implements the ASGI interface so that
    GET "/" returns 200 rather than hanging.
    """

    def __init__(self, *args, **kwargs):
        pass

    async def __call__(self, scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})


@pytest.fixture(scope="session")
def app_module():
    """Return the app.py module with module-level side effects patched out.

    app.py executes two things at import time that break in the test
    environment:
    1. `rag_system = RAGSystem(config)` — needs ChromaDB + Anthropic key.
    2. `app.mount("/", StaticFiles(directory="../frontend", ...))` — the
       directory doesn't exist and DevStaticFiles subclasses StaticFiles.

    Both patches are released immediately after import; the mock instance
    already stored on app.rag_system is what the route handlers close over.
    """
    with patch("rag_system.RAGSystem") as mock_rag_cls, \
         patch("fastapi.staticfiles.StaticFiles", _StubStaticFiles):
        mock_instance = MagicMock()
        mock_instance.add_course_folder.return_value = (0, 0)
        mock_rag_cls.return_value = mock_instance
        sys.modules.pop("app", None)
        import app as _app
    yield _app
    sys.modules.pop("app", None)


@pytest.fixture
def mock_rag(app_module):
    """Yield the module-level rag_system mock, fully reset between tests.

    `add_course_folder` is re-configured after the reset so the startup
    event (which calls it if ../docs exists) never tries to unpack a bare
    MagicMock as a (courses, chunks) tuple.
    """
    mock = app_module.rag_system
    mock.reset_mock(return_value=True, side_effect=True)
    mock.add_course_folder.return_value = (0, 0)
    yield mock


@pytest.fixture
def api_client(mock_rag, app_module):
    """TestClient for the FastAPI app.

    mock_rag is listed first so it is set up (and add_course_folder
    configured) before the TestClient triggers the app's startup event.
    """
    with TestClient(app_module.app) as client:
        yield client
