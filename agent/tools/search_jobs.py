"""
Search Jobs Tool Module.

This file is responsible for:
- Providing a strictly controlled search tool for the Autonomous Brain.
- Dispatching structured search requests exclusively through GlobalSearch and SearXNG.
- Enforcing that no unrestricted HTTP, arbitrary network requests, or direct scraping
  can be initiated by the agent or model.
"""

from typing import Any, Dict, List, Optional
from models.job import Job
from search.global_search import GlobalSearch, default_global_search
from utils.logger import get_logger

logger = get_logger("agent.tools.search_jobs")


class SearchJobsTool:
    """
    Narrow tool allowing the Brain to search for jobs via GlobalSearch.
    Enforces safe boundaries without exposing raw HTTP requests.
    """

    def __init__(self, global_search: Optional[GlobalSearch] = None) -> None:
        self.global_search = global_search or default_global_search

    @property
    def last_telemetry(self) -> Any:
        """Returns the raw SearchTelemetry object from the last executed search."""
        return getattr(self.global_search, "last_telemetry", None)

    def get_last_telemetry(self) -> Dict[str, Any]:
        """Returns a serializable dictionary of search execution metrics."""
        if hasattr(self.global_search, "last_telemetry") and self.global_search.last_telemetry:
            return self.global_search.last_telemetry.summary_dict()
        return {}

    def execute(
        self,
        query: str,
        allowed_providers: Optional[List[str]] = None,
        pageno: int = 1
    ) -> List[Job]:
        """
        Executes a job discovery query through registered providers.
        """
        logger.info(f"[TOOL:search_jobs] Executing query: '{query}' (page {pageno})")
        return self.global_search.search(
            query=query,
            allowed_providers=allowed_providers,
            pageno=pageno
        )
