"""Tests for AIGenerator (backend/ai_generator.py) — does it correctly drive the
CourseSearchTool?

The Anthropic client is patched, so no API key or network is needed. We assert on:
  * the tools / tool_choice passed into the first API call,
  * that a tool_use stop_reason triggers tool execution via the ToolManager,
  * that a second API call is made WITHOUT tools to synthesize the final answer.

These pass independently of the MAX_RESULTS config bug — they prove the generator's
tool-calling wiring is correct.
"""
from unittest.mock import MagicMock, patch

from ai_generator import AIGenerator


def test_tools_and_auto_tool_choice_passed(text_response):
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.return_value = text_response("hi")
        gen = AIGenerator(api_key="k", model="m")

        tools = [{"name": "search_course_content"}]
        gen.generate_response(query="hello", tools=tools, tool_manager=MagicMock())

    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["tools"] == tools
    assert kwargs["tool_choice"] == {"type": "auto"}


def test_forced_tool_sets_specific_tool_choice(text_response):
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.return_value = text_response("hi")
        gen = AIGenerator(api_key="k", model="m")

        gen.generate_response(
            query="give me the outline",
            tools=[{"name": "get_course_outline"}],
            tool_manager=MagicMock(),
            forced_tool="get_course_outline",
        )

    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": "get_course_outline"}


def test_tool_use_triggers_execution_and_second_call(text_response, tool_use_response):
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        # First call -> model asks for the search tool; second call -> final answer.
        client.messages.create.side_effect = [
            tool_use_response("search_course_content", {"query": "mcp"}),
            text_response("Final synthesized answer."),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "[MCP - Lesson 0]\nMCP is a protocol."
        gen = AIGenerator(api_key="k", model="m")

        result = gen.generate_response(
            query="what is mcp",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

    # The tool was executed with exactly the arguments the model supplied.
    tool_manager.execute_tool.assert_called_once_with(
        "search_course_content", query="mcp"
    )
    # Two API calls total, and the second one drops `tools` (synthesis turn).
    assert client.messages.create.call_count == 2
    second_kwargs = client.messages.create.call_args_list[1].kwargs
    assert "tools" not in second_kwargs
    assert result == "Final synthesized answer."


def test_no_tool_manager_returns_direct_text(text_response):
    """A general-knowledge query (no tools) returns the model's text directly."""
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.return_value = text_response("Paris.")
        gen = AIGenerator(api_key="k", model="m")

        result = gen.generate_response(query="capital of France?")

    assert result == "Paris."
    assert client.messages.create.call_count == 1
