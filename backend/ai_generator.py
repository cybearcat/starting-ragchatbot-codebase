import anthropic
from typing import List, Optional, Dict, Any

class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""

    # Maximum number of sequential tool-calling rounds per user query. After this
    # many tool-capable calls, a final synthesis call is made without tools so the
    # loop is guaranteed to terminate.
    MAX_TOOL_ROUNDS = 2

    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to two tools: one for course outlines and one for searching course content.

Tool Selection:
- **get_course_outline**: Use when the user asks for a course outline, syllabus, lesson list, table of contents, what lessons a course has, or what topics a course covers at a high level
- **search_course_content**: Use when the user asks about specific concepts, explanations, or details *within* course material

Sequential Tool Use:
- You may use tools across **up to 2 rounds**. After seeing a tool's results you may call another tool — including the same one with different arguments — to gather more information, then synthesize a final answer.
- Use a second round when one result feeds the next, for example:
 - Get a course outline, then search a specific lesson it reveals
 - Compare a concept across two courses by searching each
 - Answer a multi-part question that needs information from different courses or lessons
- Prefer a single tool call when it fully answers the question; do not search again if the first result is sufficient.

Course Outline Responses:
- When presenting an outline, include: course title as a heading, course link, and a numbered list of lesson titles

Search Responses:
- Synthesize search results into accurate, fact-based responses
- If a search yields no results, state this clearly without offering alternatives

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without using any tool
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, search explanations, or question-type analysis
 - Do not mention "based on the search results"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""
    
    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        
        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 800
        }
    
    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None,
                         forced_tool: Optional[str] = None) -> str:
        """
        Generate AI response with optional tool usage and conversation context.

        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools
            forced_tool: If set, force the model to call this specific tool

        Returns:
            Generated response as string
        """

        # Build system content efficiently - avoid string ops when possible
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history
            else self.SYSTEM_PROMPT
        )

        # Prepare API call parameters efficiently
        api_params = {
            **self.base_params,
            "messages": [{"role": "user", "content": query}],
            "system": system_content
        }

        # Add tools if available
        if tools:
            api_params["tools"] = tools
            if forced_tool:
                api_params["tool_choice"] = {"type": "tool", "name": forced_tool}
            else:
                api_params["tool_choice"] = {"type": "auto"}
        
        # With tools available, run the bounded sequential tool-calling loop.
        if tools and tool_manager:
            return self._run_tool_rounds(api_params, tool_manager, forced_tool)

        # No tools: a single call answers directly (general knowledge).
        response = self.client.messages.create(**api_params)
        return self._extract_text(response)

    def _run_tool_rounds(self, api_params: Dict[str, Any], tool_manager, forced_tool: Optional[str]) -> str:
        """
        Run up to MAX_TOOL_ROUNDS tool-calling rounds, then a final synthesis call
        without tools. Each round is a separate API request in which Claude can
        reason over the previous round's tool results and decide whether to call
        another tool.

        Terminates when: (a) MAX_TOOL_ROUNDS rounds are completed, (b) a response
        has no tool_use blocks, or (c) a tool execution raises.

        Args:
            api_params: Base parameters from generate_response (carries the initial
                messages, system prompt, and tool definitions)
            tool_manager: Manager to execute tools
            forced_tool: If set, force this tool on the FIRST round only

        Returns:
            Final response text after the tool rounds
        """
        messages = list(api_params["messages"])
        system = api_params["system"]
        tools = api_params["tools"]

        for round_index in range(self.MAX_TOOL_ROUNDS):
            # Force the specific tool only on the first round; let the model choose
            # freely afterward so it can follow up (e.g. outline -> content search).
            tool_choice = (
                {"type": "tool", "name": forced_tool}
                if forced_tool and round_index == 0
                else {"type": "auto"}
            )
            response = self.client.messages.create(
                **self.base_params,
                messages=messages,
                system=system,
                tools=tools,
                tool_choice=tool_choice,
            )

            # No tool requested: this response is the final answer.
            if response.stop_reason != "tool_use":
                return self._extract_text(response)

            # Record the assistant's tool-use turn, execute the tools, and append
            # the results so the next round (or synthesis) can reason over them.
            messages.append({"role": "assistant", "content": response.content})
            tool_results, failed = self._execute_tools(response.content, tool_manager)
            messages.append({"role": "user", "content": tool_results})

            # A tool raised: stop looping and synthesize from what we have.
            if failed:
                break

        # Rounds exhausted (or a tool failed): make a final call WITHOUT tools so
        # the model must answer from the gathered results rather than search again.
        final_response = self.client.messages.create(
            **self.base_params,
            messages=messages,
            system=system,
        )
        return self._extract_text(final_response)

    def _execute_tools(self, content, tool_manager):
        """
        Execute every tool_use block in a response.

        The Anthropic API requires that every tool_use block has a matching
        tool_result (paired by id) in the following turn, so even a tool that
        raises gets a result block (flagged is_error). A raised exception is the
        only thing that counts as a tool "failure" — error strings returned by a
        tool are valid results the model should reason about.

        Returns:
            (tool_results, failed): the list of tool_result dicts, and whether any
            tool execution raised.
        """
        tool_results = []
        failed = False
        for block in content:
            if block.type != "tool_use":
                continue
            try:
                result = tool_manager.execute_tool(block.name, **block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
            except Exception as exc:
                failed = True
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Tool execution failed: {exc}",
                    "is_error": True,
                })
        return tool_results, failed

    def _extract_text(self, response) -> str:
        """
        Return the first text block's text, or a safe fallback.

        Newer models can return empty content on a no-tools synthesis turn;
        indexing response.content[0] directly would raise IndexError.
        """
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text
        return "I wasn't able to generate a response. Please try rephrasing your question."