"""
Base Job Provider Module.

This file is responsible for:
- Defining the abstract interface BaseJobProvider that all search providers must implement.
- Providing standardized contracts for query formatting, URL identification,
  raw search result parsing, and normalization.
- Ensuring the Autonomous Brain remains completely decoupled from provider-specific logic.
- Allowing future providers (e.g. Indeed, Naukri, Glassdoor) to be plugged in without
  modifying the core Brain or search router.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from models.job import Job


class BaseJobProvider(ABC):
    """
    Abstract interface for job search providers discovered via SearXNG or external APIs.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier (e.g. 'linkedin', 'indeed')."""
        pass

    @abstractmethod
    def build_search_query(
        self,
        role: str,
        location: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        extra_terms: Optional[str] = None
    ) -> str:
        """
        Builds a provider-optimized search query targeted for discovery engines (SearXNG).
        """
        pass

    @abstractmethod
    def is_provider_url(self, url: str) -> bool:
        """
        Determines whether a given URL belongs to this job provider.
        """
        pass

    @abstractmethod
    def clean_url(self, url: str) -> str:
        """
        Cleans and canonicalizes a provider URL, removing tracking/referral parameters.
        """
        pass

    @abstractmethod
    def parse_result(self, raw_result: Dict[str, Any], search_query: str) -> Optional[Job]:
        """
        Converts a raw SearXNG result dictionary into a normalized Job model.
        Returns None if the result cannot be parsed as a valid job posting.
        """
        pass

    def parse_result_detailed(
        self,
        raw_result: Dict[str, Any],
        search_query: str
    ) -> Tuple[Optional[Job], Optional[str]]:
        """
        Converts a raw SearXNG result dictionary into a normalized Job model,
        or returns (None, failure_reason) explaining why it could not be parsed.
        Default implementation delegates to parse_result.
        """
        job = self.parse_result(raw_result, search_query=search_query)
        if job:
            return job, None
        return None, "Provider parse_result returned None"
