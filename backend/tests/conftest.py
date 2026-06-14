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
from unittest.mock import MagicMock

import pytest

# Backend modules use flat imports (`from vector_store import ...`). The pytest
# config already puts `backend` on sys.path; this is a belt-and-suspenders guard
# so the suite also runs if invoked without that config.
BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

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
