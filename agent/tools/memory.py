"""
Agent Memory Tool Module.

This file is responsible for:
- Exposing narrow memory read and update operations to the Autonomous Brain.
- Enforcing sandbox security by ensuring all reads and writes are restricted
  strictly to sandbox/memory/.
- Preventing access to project source code, .env, .git, or system files.
"""

from typing import List, Optional, Set
from security.sandbox import Sandbox, default_sandbox
from storage.memory import AgentMemory
from utils.logger import get_logger

logger = get_logger("agent.tools.memory")


class MemoryTool:
    """
    Narrow tool allowing the Brain to inspect and update persistent memory state.
    """

    def __init__(self, sandbox: Optional[Sandbox] = None) -> None:
        self.sandbox = sandbox or default_sandbox
        self._memory: AgentMemory = AgentMemory.load(self.sandbox)

    @property
    def memory(self) -> AgentMemory:
        """Access the in-memory agent state."""
        return self._memory

    def get_searched_queries(self) -> List[str]:
        """Returns the list of previously executed search queries."""
        return list(self._memory.searched_queries)

    def get_seen_urls(self) -> Set[str]:
        """Returns the set of all job URLs discovered so far."""
        return set(self._memory.searched_urls)

    def get_accepted_urls(self) -> Set[str]:
        """Returns the set of accepted job URLs."""
        return set(self._memory.accepted_urls)

    def save(self) -> None:
        """Persists the memory state to sandbox/memory/agent_memory.json."""
        self._memory.save(self.sandbox)
        logger.info("[TOOL:memory] Saved agent memory state to sandbox.")

    def reload(self) -> AgentMemory:
        """Reloads the memory from disk."""
        self._memory = AgentMemory.load(self.sandbox)
        return self._memory
