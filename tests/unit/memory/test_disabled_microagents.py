"""Tests for the disabled_microagents feature in Memory.

Verifies that:
1. Disabled repo microagents are excluded from workspace context recalls
2. Disabled knowledge microagents are excluded from trigger matches
3. Disabled repo microagents with MCP tools are excluded from get_microagent_mcp_tools()
4. Non-disabled microagents are unaffected
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from openhands.core.config.mcp_config import MCPConfig, MCPStdioServerConfig
from openhands.events.action.agent import RecallAction
from openhands.events.action.message import MessageAction
from openhands.events.event import EventSource
from openhands.events.observation.agent import RecallObservation, RecallType
from openhands.events.stream import EventStream
from openhands.memory.memory import Memory
from openhands.microagent.microagent import KnowledgeMicroagent, RepoMicroagent
from openhands.microagent.types import MicroagentMetadata, MicroagentType
from openhands.storage.memory import InMemoryFileStore


@pytest.fixture
def file_store():
    return InMemoryFileStore({})


@pytest.fixture
def event_stream(file_store):
    return EventStream(sid='test_sid', file_store=file_store)


def _make_repo_microagent(
    name: str,
    content: str,
    mcp_tools: MCPConfig | None = None,
) -> RepoMicroagent:
    """Helper to create a RepoMicroagent for testing."""
    return RepoMicroagent(
        name=name,
        content=content,
        metadata=MicroagentMetadata(name=name, mcp_tools=mcp_tools),
        source=f'/test/{name}.md',
        type=MicroagentType.REPO_KNOWLEDGE,
    )


def _make_knowledge_microagent(
    name: str,
    content: str,
    triggers: list[str],
) -> KnowledgeMicroagent:
    """Helper to create a KnowledgeMicroagent for testing."""
    return KnowledgeMicroagent(
        name=name,
        content=content,
        metadata=MicroagentMetadata(
            name=name,
            triggers=triggers,
            type=MicroagentType.KNOWLEDGE,
        ),
        source=f'/test/{name}.md',
        type=MicroagentType.KNOWLEDGE,
    )


def test_disabled_repo_microagent_excluded_from_workspace_context(
    file_store, event_stream
):
    """Disabled repo microagents should NOT appear in repo_instructions."""
    # Patch global/user dirs to empty to avoid loading real agents
    with (
        patch('openhands.memory.memory.GLOBAL_MICROAGENTS_DIR', '/nonexistent'),
        patch('openhands.memory.memory.USER_MICROAGENTS_DIR', '/nonexistent'),
    ):
        memory = Memory(
            event_stream=event_stream,
            sid='test-session',
            disabled_microagents=['agent_to_disable'],
        )

    # Manually add repo microagents
    memory.repo_microagents = {
        'agent_to_disable': _make_repo_microagent(
            'agent_to_disable', 'DISABLED CONTENT'
        ),
        'active_agent': _make_repo_microagent('active_agent', 'ACTIVE CONTENT'),
    }

    # Set repository info so the observation is created
    memory.set_repository_info('owner/repo', '/workspace/repo')

    # Fire workspace context recall
    user_message = MessageAction(content='Test message')
    user_message._source = EventSource.USER
    event_stream.add_event(user_message, EventSource.USER)

    recall_action = RecallAction(
        query='Test message', recall_type=RecallType.WORKSPACE_CONTEXT
    )
    recall_action._source = EventSource.USER
    event_stream.add_event(recall_action, EventSource.USER)

    # Give synchronous event processing time to complete
    time.sleep(0.3)

    events = list(event_stream.get_events())
    observations = [e for e in events if isinstance(e, RecallObservation)]

    assert len(observations) == 1
    obs = observations[0]
    assert 'ACTIVE CONTENT' in obs.repo_instructions
    assert 'DISABLED CONTENT' not in obs.repo_instructions


def test_non_disabled_repo_microagents_included(file_store, event_stream):
    """When disabled_microagents is empty, all repo microagents appear."""
    with (
        patch('openhands.memory.memory.GLOBAL_MICROAGENTS_DIR', '/nonexistent'),
        patch('openhands.memory.memory.USER_MICROAGENTS_DIR', '/nonexistent'),
    ):
        memory = Memory(
            event_stream=event_stream,
            sid='test-session',
            disabled_microagents=[],
        )

    memory.repo_microagents = {
        'agent_a': _make_repo_microagent('agent_a', 'CONTENT A'),
        'agent_b': _make_repo_microagent('agent_b', 'CONTENT B'),
    }
    memory.set_repository_info('owner/repo', '/workspace/repo')

    recall_action = RecallAction(query='Test', recall_type=RecallType.WORKSPACE_CONTEXT)
    recall_action._source = EventSource.USER
    event_stream.add_event(recall_action, EventSource.USER)

    time.sleep(0.3)

    events = list(event_stream.get_events())
    observations = [e for e in events if isinstance(e, RecallObservation)]

    assert len(observations) == 1
    obs = observations[0]
    assert 'CONTENT A' in obs.repo_instructions
    assert 'CONTENT B' in obs.repo_instructions


def test_disabled_mcp_tools_excluded(file_store, event_stream):
    """Disabled repo microagents with MCP tools should be excluded from get_microagent_mcp_tools()."""
    mcp_config = MCPConfig(
        stdio_servers=[
            MCPStdioServerConfig(name='test-server', command='echo', args=['hello']),
        ],
    )

    with (
        patch('openhands.memory.memory.GLOBAL_MICROAGENTS_DIR', '/nonexistent'),
        patch('openhands.memory.memory.USER_MICROAGENTS_DIR', '/nonexistent'),
    ):
        memory = Memory(
            event_stream=event_stream,
            sid='test-session',
            disabled_microagents=['mcp_agent'],
        )

    memory.repo_microagents = {
        'mcp_agent': _make_repo_microagent(
            'mcp_agent', 'MCP Agent', mcp_tools=mcp_config
        ),
        'other_mcp_agent': _make_repo_microagent(
            'other_mcp_agent', 'Other Agent', mcp_tools=mcp_config
        ),
    }

    mcp_configs = memory.get_microagent_mcp_tools()

    # Only the non-disabled agent's MCP config should be returned
    assert len(mcp_configs) == 1


def test_non_disabled_mcp_tools_included(file_store, event_stream):
    """When no microagents are disabled, all MCP tools are returned."""
    mcp_config = MCPConfig(
        stdio_servers=[
            MCPStdioServerConfig(name='test-server', command='echo', args=['hello']),
        ],
    )

    with (
        patch('openhands.memory.memory.GLOBAL_MICROAGENTS_DIR', '/nonexistent'),
        patch('openhands.memory.memory.USER_MICROAGENTS_DIR', '/nonexistent'),
    ):
        memory = Memory(
            event_stream=event_stream,
            sid='test-session',
            disabled_microagents=[],
        )

    memory.repo_microagents = {
        'agent_a': _make_repo_microagent('agent_a', 'Agent A', mcp_tools=mcp_config),
        'agent_b': _make_repo_microagent('agent_b', 'Agent B', mcp_tools=mcp_config),
    }

    mcp_configs = memory.get_microagent_mcp_tools()
    assert len(mcp_configs) == 2


@pytest.mark.asyncio
async def test_disabled_knowledge_microagent_excluded_from_recall():
    """Disabled knowledge microagents should NOT trigger on keyword matches."""
    event_stream = MagicMock(spec=EventStream)

    with (
        patch('openhands.memory.memory.GLOBAL_MICROAGENTS_DIR', '/nonexistent'),
        patch('openhands.memory.memory.USER_MICROAGENTS_DIR', '/nonexistent'),
    ):
        memory = Memory(
            event_stream=event_stream,
            sid='test-session',
            disabled_microagents=['test_knowledge'],
        )

    # Manually add knowledge microagents — one disabled, one active
    memory.knowledge_microagents = {
        'test_knowledge': _make_knowledge_microagent(
            'test_knowledge',
            'Knowledge content about testing',
            triggers=['testword'],
        ),
        'active_knowledge': _make_knowledge_microagent(
            'active_knowledge',
            'Active knowledge content',
            triggers=['testword'],
        ),
    }

    results = memory._find_microagent_knowledge('hello testword')

    # Only the active (non-disabled) knowledge microagent should match
    assert len(results) == 1
    assert results[0].name == 'active_knowledge'


def test_disabled_microagents_defaults_to_empty(file_store, event_stream):
    """When disabled_microagents is not provided, it defaults to an empty list."""
    with (
        patch('openhands.memory.memory.GLOBAL_MICROAGENTS_DIR', '/nonexistent'),
        patch('openhands.memory.memory.USER_MICROAGENTS_DIR', '/nonexistent'),
    ):
        memory = Memory(
            event_stream=event_stream,
            sid='test-session',
        )

    assert memory.disabled_microagents == []


def test_disabled_microagents_none_treated_as_empty(file_store, event_stream):
    """When disabled_microagents is None, it is treated as an empty list."""
    with (
        patch('openhands.memory.memory.GLOBAL_MICROAGENTS_DIR', '/nonexistent'),
        patch('openhands.memory.memory.USER_MICROAGENTS_DIR', '/nonexistent'),
    ):
        memory = Memory(
            event_stream=event_stream,
            sid='test-session',
            disabled_microagents=None,
        )

    assert memory.disabled_microagents == []


def test_multiple_disabled_microagents(file_store, event_stream):
    """Multiple microagents can be disabled simultaneously."""
    with (
        patch('openhands.memory.memory.GLOBAL_MICROAGENTS_DIR', '/nonexistent'),
        patch('openhands.memory.memory.USER_MICROAGENTS_DIR', '/nonexistent'),
    ):
        memory = Memory(
            event_stream=event_stream,
            sid='test-session',
            disabled_microagents=['agent_a', 'agent_c'],
        )

    memory.repo_microagents = {
        'agent_a': _make_repo_microagent('agent_a', 'CONTENT A'),
        'agent_b': _make_repo_microagent('agent_b', 'CONTENT B'),
        'agent_c': _make_repo_microagent('agent_c', 'CONTENT C'),
    }
    memory.set_repository_info('owner/repo', '/workspace/repo')

    recall_action = RecallAction(query='Test', recall_type=RecallType.WORKSPACE_CONTEXT)
    recall_action._source = EventSource.USER
    event_stream.add_event(recall_action, EventSource.USER)

    time.sleep(0.3)

    events = list(event_stream.get_events())
    observations = [e for e in events if isinstance(e, RecallObservation)]

    assert len(observations) == 1
    obs = observations[0]
    assert 'CONTENT A' not in obs.repo_instructions
    assert 'CONTENT B' in obs.repo_instructions
    assert 'CONTENT C' not in obs.repo_instructions
