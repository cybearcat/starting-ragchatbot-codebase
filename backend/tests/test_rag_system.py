"""Tests for RAGSystem.query (backend/rag_system.py) handling content queries.

RAGSystem is built with a throwaway temp ChromaDB path and a patched Anthropic
client, so these run hermetically alongside the live app. The vector store, tool
manager, and search tools are REAL — only the LLM is mocked — so a simulated
tool-use turn flows through the actual `search_course_content` path and surfaces
real sources.
"""
from unittest.mock import patch

import pytest

from config import Config
from rag_system import RAGSystem


@pytest.fixture
def rag_factory(tmp_path_factory, sample_course, sample_chunks):
    """Return `make(max_results) -> (rag_system, mock_anthropic_client)`."""
    def _make(max_results):
        cfg = Config()
        cfg.CHROMA_PATH = str(tmp_path_factory.mktemp("rag_chroma"))
        cfg.MAX_RESULTS = max_results
        cfg.ANTHROPIC_API_KEY = "test-key"

        # Patch only during construction; the created client instance persists on
        # rag.ai_generator.client, so the test can set its side_effect afterward.
        with patch("ai_generator.anthropic.Anthropic") as mock_cls:
            rag = RAGSystem(cfg)
            client = mock_cls.return_value

        rag.vector_store.add_course_metadata(sample_course)
        rag.vector_store.add_course_content(sample_chunks)
        return rag, client

    return _make


def test_content_query_returns_answer_and_sources(rag_factory, text_response, tool_use_response):
    rag, client = rag_factory(max_results=5)
    client.messages.create.side_effect = [
        tool_use_response("search_course_content", {"query": "model context protocol"}),
        text_response("MCP is the Model Context Protocol."),
    ]

    answer, sources = rag.query("What is MCP?")

    assert answer == "MCP is the Model Context Protocol."
    assert sources, "content search should surface sources"
    assert sources[0]["title"].startswith("Test Course: MCP Basics")
    assert client.messages.create.call_count == 2


def test_query_passes_tool_definitions_and_auto_choice(rag_factory, text_response):
    rag, client = rag_factory(max_results=5)
    client.messages.create.return_value = text_response("hello")

    rag.query("just a general question")

    kwargs = client.messages.create.call_args.kwargs
    tool_names = {t["name"] for t in kwargs["tools"]}
    assert {"search_course_content", "get_course_outline"} <= tool_names
    assert kwargs["tool_choice"] == {"type": "auto"}


def test_outline_query_forces_outline_tool(rag_factory, text_response, tool_use_response):
    """RAGSystem detects outline intent and forces get_course_outline."""
    rag, client = rag_factory(max_results=5)
    client.messages.create.side_effect = [
        tool_use_response("get_course_outline", {"course_title": "MCP"}),
        text_response("Here is the outline."),
    ]

    rag.query("show me the course outline for MCP")

    first_kwargs = client.messages.create.call_args_list[0].kwargs
    assert first_kwargs["tool_choice"] == {"type": "tool", "name": "get_course_outline"}


def test_content_query_with_zero_max_results_yields_no_sources(
    rag_factory, text_response, tool_use_response
):
    """End-to-end reproduction of the bug: MAX_RESULTS=0 -> content search returns
    nothing usable -> no sources, despite a populated index."""
    rag, client = rag_factory(max_results=0)
    client.messages.create.side_effect = [
        tool_use_response("search_course_content", {"query": "model context protocol"}),
        text_response("I could not find relevant content."),
    ]

    answer, sources = rag.query("What is MCP?")

    assert sources == []
