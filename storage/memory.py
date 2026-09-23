"""
Agent Memory Storage Module.

This file is responsible for:
- Providing persistent memory state across search iterations.
- Tracking searched queries, discovered URLs, accepted job URLs, rejected URLs,
  failed queries, iteration counts, and diagnostic history.
- Persisting state strictly to sandbox/memory/agent_memory.json via the Sandbox abstraction.
- Preventing repetitive searches, redundant evaluations, and loops.
"""

from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

from security.sandbox import Sandbox, default_sandbox
from utils.logger import get_logger

logger = get_logger("storage.memory")


class AgentMemory(BaseModel):
    """
    Persistent memory structure tracking past actions, results, and diagnostic notes.
    """
    searched_queries: List[str] = Field(
        default_factory=list,
        description="Historical queries executed by the agent"
    )
    searched_urls: List[str] = Field(
        default_factory=list,
        description="All URLs discovered and processed so far"
    )
    accepted_urls: List[str] = Field(
        default_factory=list,
        description="URLs of jobs successfully evaluated and accepted"
    )
    rejected_urls: List[str] = Field(
        default_factory=list,
        description="URLs of jobs rejected by filters or semantic evaluation"
    )
    failed_queries: List[str] = Field(
        default_factory=list,
        description="Queries that returned zero results or encountered errors"
    )
    iteration: int = Field(
        default=0,
        description="Current feedback loop iteration index"
    )
    search_statistics: Dict[str, Any] = Field(
        default_factory=lambda: {
            "total_discovered": 0,
            "total_unique": 0,
            "total_evaluated": 0,
            "total_accepted": 0,
            "total_rejected": 0,
            "rejections_by_reason": {}
        },
        description="Cumulative search metrics across all iterations"
    )
    strategy_history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Audit log of observe -> diagnose -> decide cycles"
    )

    def is_query_searched(self, query: str) -> bool:
        """Checks whether a query has already been executed."""
        clean_q = query.strip().lower()
        return any(q.strip().lower() == clean_q for q in self.searched_queries)

    def is_url_seen(self, url: str) -> bool:
        """Checks whether a job URL has already been processed."""
        clean_u = url.strip().lower()
        return any(u.strip().lower() == clean_u for u in self.searched_urls)

    def record_query(self, query: str, success: bool = True) -> None:
        """Records a search query in memory."""
        if not self.is_query_searched(query):
            self.searched_queries.append(query)
        if not success and query not in self.failed_queries:
            self.failed_queries.append(query)

    def record_job_outcome(self, url: str, accepted: bool, reason: Optional[str] = None) -> None:
        """Records the acceptance or rejection of a job URL and updates statistics."""
        if not self.is_url_seen(url):
            self.searched_urls.append(url)

        if accepted:
            if url not in self.accepted_urls:
                self.accepted_urls.append(url)
            self.search_statistics["total_accepted"] += 1
        else:
            if url not in self.rejected_urls:
                self.rejected_urls.append(url)
            self.search_statistics["total_rejected"] += 1

            if reason:
                reasons_dict = self.search_statistics["rejections_by_reason"]
                reasons_dict[reason] = reasons_dict.get(reason, 0) + 1

    def record_cycle(self, observation: Dict[str, Any], diagnosis: str, decision: str) -> None:
        """Appends an OBSERVE -> DIAGNOSE -> DECIDE state record to strategy history."""
        self.strategy_history.append({
            "iteration": self.iteration,
            "observation": observation,
            "diagnosis": diagnosis,
            "decision": decision
        })

    def save(self, sandbox: Optional[Sandbox] = None, filename: str = "agent_memory.json") -> None:
        """Persists the memory state to the designated sandbox/memory/ directory."""
        sb = sandbox or default_sandbox
        data = self.model_dump()
        sb.write_json("memory", filename, data)
        logger.debug(f"Agent memory persisted to sandbox/memory/{filename}")

    @classmethod
    def load(cls, sandbox: Optional[Sandbox] = None, filename: str = "agent_memory.json") -> "AgentMemory":
        """Loads persistent memory state from sandbox/memory/ if it exists, or returns a fresh instance."""
        sb = sandbox or default_sandbox
        if sb.exists("memory", filename):
            try:
                data = sb.read_json("memory", filename)
                logger.info(f"Loaded existing agent memory from sandbox/memory/{filename}")
                return cls.model_validate(data)
            except Exception as e:
                logger.warning(f"Failed to read existing memory file ({e}). Starting fresh memory.")
        return cls()
