"""Tests for AIGenerator (backend/ai_generator.py) — does it correctly drive the
tools across up to 2 sequential rounds?

The Anthropic client is patched, so no API key or network is needed. We assert on
EXTERNAL behavior only:
  * the tools / tool_choice passed into each API call,
  * which tools are executed (and with which args) via the ToolManager,
  * how many API calls are made and whether the final synthesis call drops `tools`,
  * the text returned.

Multi-call sequences are driven with
`client.messages.create.side_effect = [resp1, resp2, ...]`. Mock content blocks set
`.type` explicitly (a bare MagicMock().type is a Mock, so `== "tool_use"` is False
and the tool would silently never run).
"""
from unittest.mock import MagicMock, call, patch

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


def test_single_round_then_answer(text_response, tool_use_response):
    """One tool round, then the model answers: 2 calls total.

    Under sequential calling the SECOND call is itself a tool-capable round (it
    still carries `tools`) — the model simply chose to answer instead of calling
    another tool.
    """
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.side_effect = [
            tool_use_response("search_course_content", {"query": "mcp"}, tool_id="t1"),
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
    tool_manager.execute_tool.assert_called_once_with("search_course_content", query="mcp")
    assert client.messages.create.call_count == 2
    # The second call is a tool-capable round (tools still offered).
    assert "tools" in client.messages.create.call_args_list[1].kwargs
    assert result == "Final synthesized answer."


def test_two_round_happy_path(text_response, tool_use_response):
    """The headline flow: outline lookup -> content search -> synthesized answer.

    Round 1 is forced to the outline tool; round 2 is auto and still tool-capable;
    the 3rd (synthesis) call drops `tools`.
    """
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.side_effect = [
            tool_use_response("get_course_outline", {"course_title": "MCP"}, tool_id="t1"),
            tool_use_response("search_course_content", {"query": "servers"}, tool_id="t2"),
            text_response("Final synthesized answer."),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.side_effect = ["outline text", "search text"]
        gen = AIGenerator(api_key="k", model="m")

        result = gen.generate_response(
            query="what other course covers the topic of lesson 1?",
            tools=[{"name": "get_course_outline"}, {"name": "search_course_content"}],
            tool_manager=tool_manager,
            forced_tool="get_course_outline",
        )

    assert client.messages.create.call_count == 3
    calls = client.messages.create.call_args_list
    # Round 1: forced to the outline tool.
    assert calls[0].kwargs["tool_choice"] == {"type": "tool", "name": "get_course_outline"}
    # Round 2: auto, and tools are still available so a second search can happen.
    assert calls[1].kwargs["tool_choice"] == {"type": "auto"}
    assert "tools" in calls[1].kwargs
    # Synthesis: no tools offered, so the model cannot start a 3rd round.
    assert "tools" not in calls[2].kwargs
    # Both tools executed, in order, with the model-supplied arguments.
    assert tool_manager.execute_tool.call_args_list == [
        call("get_course_outline", course_title="MCP"),
        call("search_course_content", query="servers"),
    ]
    assert result == "Final synthesized answer."


def test_forced_tool_only_on_first_round(text_response, tool_use_response):
    """A forced tool pins round 1 only; round 2 reverts to auto."""
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.side_effect = [
            tool_use_response("get_course_outline", {"course_title": "MCP"}, tool_id="t1"),
            tool_use_response("search_course_content", {"query": "x"}, tool_id="t2"),
            text_response("done"),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.side_effect = ["a", "b"]
        gen = AIGenerator(api_key="k", model="m")

        gen.generate_response(
            query="q",
            tools=[{"name": "get_course_outline"}, {"name": "search_course_content"}],
            tool_manager=tool_manager,
            forced_tool="get_course_outline",
        )

    calls = client.messages.create.call_args_list
    assert calls[0].kwargs["tool_choice"] == {"type": "tool", "name": "get_course_outline"}
    assert calls[1].kwargs["tool_choice"] == {"type": "auto"}


def test_caps_at_two_rounds(text_response, tool_use_response):
    """If the model wants tools in both rounds, it is capped at 2 executions and
    a final no-tools synthesis call produces the answer."""
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.side_effect = [
            tool_use_response("search_course_content", {"query": "a"}, tool_id="t1"),
            tool_use_response("search_course_content", {"query": "b"}, tool_id="t2"),
            text_response("final"),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.side_effect = ["r1", "r2"]
        gen = AIGenerator(api_key="k", model="m")

        result = gen.generate_response(
            query="q",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

    assert tool_manager.execute_tool.call_count == 2
    assert client.messages.create.call_count == 3
    assert "tools" not in client.messages.create.call_args_list[2].kwargs
    assert result == "final"


def test_tool_error_terminates_gracefully(text_response, tool_use_response):
    """A raised tool error stops the loop, sends an is_error result, and lets the
    model synthesize a graceful answer — without crashing or retrying the tool."""
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.side_effect = [
            tool_use_response("search_course_content", {"query": "a"}, tool_id="t1"),
            text_response("graceful answer"),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.side_effect = Exception("boom")
        gen = AIGenerator(api_key="k", model="m")

        result = gen.generate_response(
            query="q",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

    # round 1 + synthesis = 2 calls; the failed tool is not retried.
    assert client.messages.create.call_count == 2
    assert tool_manager.execute_tool.call_count == 1
    # Synthesis call drops tools.
    synth_kwargs = client.messages.create.call_args_list[1].kwargs
    assert "tools" not in synth_kwargs
    # The failed tool_use still got a paired tool_result flagged is_error (so the
    # API would not 400 on an unpaired tool_use).
    tool_result_blocks = [
        block
        for message in synth_kwargs["messages"]
        if isinstance(message["content"], list)
        for block in message["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    assert any(block.get("is_error") for block in tool_result_blocks)
    assert result == "graceful answer"


def test_empty_final_content_safe(empty_content_response, tool_use_response):
    """An empty content array on the synthesis turn returns a safe fallback string
    rather than raising IndexError."""
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.side_effect = [
            tool_use_response("search_course_content", {"query": "a"}, tool_id="t1"),
            tool_use_response("search_course_content", {"query": "b"}, tool_id="t2"),
            empty_content_response(),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.side_effect = ["r1", "r2"]
        gen = AIGenerator(api_key="k", model="m")

        result = gen.generate_response(
            query="q",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

    assert isinstance(result, str)
    assert result  # non-empty fallback, no crash


def test_no_tool_manager_returns_direct_text(text_response):
    """A general-knowledge query (no tools) returns the model's text directly."""
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.return_value = text_response("Paris.")
        gen = AIGenerator(api_key="k", model="m")

        result = gen.generate_response(query="capital of France?")

    assert result == "Paris."
    assert client.messages.create.call_count == 1
