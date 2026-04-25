from agent_prompt import SYSTEM_PROMPT


def test_system_prompt_is_string():
    """SYSTEM_PROMPT must be a non-empty string."""
    assert isinstance(SYSTEM_PROMPT, str)
    assert len(SYSTEM_PROMPT) > 100


def test_system_prompt_mentions_all_tools():
    """SYSTEM_PROMPT must reference all three MCP tools by name."""
    assert "fetch_space_data" in SYSTEM_PROMPT
    assert "manage_space_journal" in SYSTEM_PROMPT
    assert "show_space_dashboard" in SYSTEM_PROMPT


def test_system_prompt_mentions_tool_order():
    """SYSTEM_PROMPT should instruct the recommended tool-calling order."""
    fetch_pos = SYSTEM_PROMPT.index("fetch_space_data")
    journal_pos = SYSTEM_PROMPT.index("manage_space_journal")
    dashboard_pos = SYSTEM_PROMPT.index("show_space_dashboard")

    assert fetch_pos < journal_pos < dashboard_pos


def test_system_prompt_mentions_explaining_actions():
    """SYSTEM_PROMPT should instruct the agent to explain its next action."""
    prompt_lower = SYSTEM_PROMPT.lower()

    assert "explain" in prompt_lower
    assert "before" in prompt_lower
