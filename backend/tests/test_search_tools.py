"""Tests for CourseSearchTool.execute (backend/search_tools.py).

Two layers:
  * Unit tests with a mocked VectorStore exercise the tool's own logic (formatting,
    source tracking, error/empty handling, filter forwarding). These PASS regardless
    of the MAX_RESULTS bug — they prove the tool logic is sound.
  * Integration tests build a REAL VectorStore and run the search end-to-end. The
    pair (max_results=0 vs >0) isolates the defect to the configured result cap.
"""
from unittest.mock import MagicMock

from search_tools import CourseSearchTool
from vector_store import SearchResults
from config import config


# --------------------------------------------------------------------------- #
# Unit tests — mocked VectorStore (tool logic in isolation)
# --------------------------------------------------------------------------- #

def test_execute_formats_results_and_tracks_sources():
    store = MagicMock()
    store.search.return_value = SearchResults(
        documents=["MCP is a protocol.", "Servers expose tools."],
        metadata=[
            {"course_title": "MCP Basics", "lesson_number": 0},
            {"course_title": "MCP Basics", "lesson_number": 1},
        ],
        distances=[0.1, 0.2],
    )
    store.get_lesson_link.return_value = "https://example.com/lesson"
    tool = CourseSearchTool(store)

    out = tool.execute(query="what is mcp")

    # Each result carries a [Course - Lesson N] context header.
    assert "[MCP Basics - Lesson 0]" in out
    assert "MCP is a protocol." in out
    # Sources are tracked for the UI, deduplicated, with resolved lesson links.
    assert len(tool.last_sources) == 2
    assert tool.last_sources[0] == {
        "title": "MCP Basics - Lesson 0",
        "url": "https://example.com/lesson",
    }


def test_execute_returns_error_string_verbatim():
    store = MagicMock()
    store.search.return_value = SearchResults.empty("Search error: boom")
    tool = CourseSearchTool(store)

    assert tool.execute(query="x") == "Search error: boom"


def test_execute_empty_results_message_includes_filters():
    store = MagicMock()
    store.search.return_value = SearchResults(documents=[], metadata=[], distances=[])
    tool = CourseSearchTool(store)

    out = tool.execute(query="x", course_name="MCP", lesson_number=2)

    assert "No relevant content found" in out
    assert "course 'MCP'" in out
    assert "lesson 2" in out


def test_execute_forwards_filters_to_store():
    store = MagicMock()
    store.search.return_value = SearchResults(documents=[], metadata=[], distances=[])
    tool = CourseSearchTool(store)

    tool.execute(query="topic", course_name="MCP", lesson_number=1)

    store.search.assert_called_once_with(
        query="topic", course_name="MCP", lesson_number=1
    )


# --------------------------------------------------------------------------- #
# Integration tests — real VectorStore (the diagnostic pair)
# --------------------------------------------------------------------------- #

def test_execute_returns_content_with_positive_limit(seeded_store_factory):
    """With a sane result cap, a content query returns the seeded chunk + sources."""
    tool = CourseSearchTool(seeded_store_factory(max_results=5))

    out = tool.execute(query="What is the Model Context Protocol?")

    assert "No relevant content found" not in out
    assert "Search error" not in out
    assert "Model Context Protocol" in out
    assert tool.last_sources  # sources surfaced


def test_execute_broken_with_zero_limit(seeded_store_factory):
    """Reproduces the bug directly: a zero result cap can never return content."""
    tool = CourseSearchTool(seeded_store_factory(max_results=0))

    out = tool.execute(query="What is the Model Context Protocol?")

    assert "MCP is the Model Context Protocol" not in out
    assert ("No relevant content found" in out) or ("Search error" in out)


def test_execute_with_live_config_value(seeded_store_factory):
    """Build the store with the REAL configured MAX_RESULTS.

    This is the component-level diagnostic: it FAILS while config.MAX_RESULTS == 0
    and PASSES once it is set to a positive number.
    """
    tool = CourseSearchTool(seeded_store_factory(max_results=config.MAX_RESULTS))

    out = tool.execute(query="What is the Model Context Protocol?")

    assert "No relevant content found" not in out
    assert "Search error" not in out
    assert "Model Context Protocol" in out


def test_config_max_results_is_positive():
    """One-line pinpoint of the defect.

    Bind to a local first so pytest's assertion introspection reports the int,
    not the full Config repr (which would leak ANTHROPIC_API_KEY into the output).
    """
    max_results = config.MAX_RESULTS
    assert max_results > 0, (
        f"MAX_RESULTS={max_results} makes ChromaDB return zero search "
        "results; content search can never return anything."
    )
