"""Tests for CourseSearchTool.execute (backend/search_tools.py).

Two layers:
  * Unit tests with a mocked VectorStore exercise the tool's own logic (formatting,
    source tracking, error/empty handling, filter forwarding). These PASS regardless
    of the MAX_RESULTS bug — they prove the tool logic is sound.
  * Integration tests build a REAL VectorStore and run the search end-to-end. The
    pair (max_results=0 vs >0) isolates the defect to the configured result cap.
"""
from unittest.mock import MagicMock

from search_tools import CourseSearchTool, ToolManager
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


# --------------------------------------------------------------------------- #
# ToolManager — source accumulation across calls (multi-round queries)
# --------------------------------------------------------------------------- #

def _search_results(*lessons, course="MCP"):
    """Build a SearchResults with one chunk per given lesson number."""
    return SearchResults(
        documents=[f"chunk {n}" for n in lessons],
        metadata=[{"course_title": course, "lesson_number": n} for n in lessons],
        distances=[0.1 * (i + 1) for i in range(len(lessons))],
    )


def test_tool_manager_accumulates_sources_across_calls():
    """Two searches in one query -> get_last_sources returns BOTH searches' sources."""
    store = MagicMock()
    store.get_lesson_link.side_effect = lambda course, lesson: f"https://example.com/{lesson}"
    manager = ToolManager()
    manager.register_tool(CourseSearchTool(store))

    store.search.side_effect = [_search_results(0), _search_results(1)]
    manager.execute_tool("search_course_content", query="first")
    manager.execute_tool("search_course_content", query="second")

    titles = [s["title"] for s in manager.get_last_sources()]
    assert titles == ["MCP - Lesson 0", "MCP - Lesson 1"]


def test_tool_manager_dedupes_sources():
    """An overlapping source across rounds appears once, in first-seen order."""
    store = MagicMock()
    store.get_lesson_link.side_effect = lambda course, lesson: f"https://example.com/{lesson}"
    manager = ToolManager()
    manager.register_tool(CourseSearchTool(store))

    # Round 2 repeats lesson 0 (duplicate) and adds lesson 1 (new).
    store.search.side_effect = [_search_results(0), _search_results(0, 1)]
    manager.execute_tool("search_course_content", query="x")
    manager.execute_tool("search_course_content", query="y")

    titles = [s["title"] for s in manager.get_last_sources()]
    assert titles == ["MCP - Lesson 0", "MCP - Lesson 1"]


def test_tool_manager_keeps_sources_when_later_search_empty():
    """A later empty search must not drop earlier sources.

    On an empty result the tool returns early without calling _format_results, so
    its last_sources keeps the prior (stale) value; the dedup makes re-appending a
    no-op rather than a loss.
    """
    store = MagicMock()
    store.get_lesson_link.side_effect = lambda course, lesson: f"https://example.com/{lesson}"
    manager = ToolManager()
    manager.register_tool(CourseSearchTool(store))

    store.search.side_effect = [
        _search_results(0),                                  # round 1: finds lesson 0
        SearchResults(documents=[], metadata=[], distances=[]),  # round 2: empty
    ]
    manager.execute_tool("search_course_content", query="hit")
    manager.execute_tool("search_course_content", query="miss")

    titles = [s["title"] for s in manager.get_last_sources()]
    assert titles == ["MCP - Lesson 0"]


def test_reset_sources_clears_accumulated():
    """reset_sources empties both the accumulator and the tool's last_sources."""
    store = MagicMock()
    store.get_lesson_link.return_value = "https://example.com/lesson"
    manager = ToolManager()
    tool = CourseSearchTool(store)
    manager.register_tool(tool)

    store.search.return_value = _search_results(0)
    manager.execute_tool("search_course_content", query="x")
    assert manager.get_last_sources()  # populated

    manager.reset_sources()
    assert manager.get_last_sources() == []
    assert tool.last_sources == []
