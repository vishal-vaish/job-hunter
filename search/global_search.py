"""
Global Search Orchestrator Module.

This file is responsible for:
- Implementing the GlobalSearch routing layer between the Agent Search Tool and Job Providers.
- Decoupling the Autonomous Brain from provider-specific mechanics (e.g. LinkedIn dorks, URL patterns).
- Dispatching search queries to SearXNG and routing discovered items to the appropriate
  registered provider (e.g. LinkedIn, and future providers like Indeed or Naukri).
- Aggregating, normalizing, and returning standardized Job models.
"""

from typing import Dict, List, Optional
from infrastructure.searxng import SearXNGClient
from models.job import Job
from providers.base import BaseJobProvider
from providers.linkedin import LinkedInProvider
from utils.logger import get_logger

logger = get_logger("search.global_search")


class GlobalSearch:
    """
    Search router that coordinates queries across multiple pluggable providers via SearXNG.
    """

    def __init__(self, searxng_client: Optional[SearXNGClient] = None) -> None:
        self.searxng = searxng_client or SearXNGClient()
        self._providers: Dict[str, BaseJobProvider] = {}

        # Register default built-in providers
        self.register_provider(LinkedInProvider())

    def register_provider(self, provider: BaseJobProvider) -> None:
        """
        Registers a new search provider into the router.
        """
        self._providers[provider.name.lower()] = provider
        logger.debug(f"Registered job search provider: '{provider.name}'")

    def get_provider(self, name: str) -> Optional[BaseJobProvider]:
        """
        Retrieves a registered provider instance by name.
        """
        return self._providers.get(name.lower())

    def list_providers(self) -> List[str]:
        """
        Lists all currently registered provider names.
        """
        return list(self._providers.keys())

    def build_query_for_provider(
        self,
        provider_name: str,
        role: str,
        location: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        extra_terms: Optional[str] = None
    ) -> str:
        """
        Constructs a provider-specific discovery query string.
        """
        provider = self.get_provider(provider_name)
        if not provider:
            # Fallback generic query if provider unknown
            parts = [role]
            if location:
                parts.append(location)
            if keywords:
                parts.extend(keywords[:3])
            return " ".join(parts)

        return provider.build_search_query(
            role=role,
            location=location,
            keywords=keywords,
            extra_terms=extra_terms
        )

    def search(
        self,
        query: str,
        allowed_providers: Optional[List[str]] = None,
        pageno: int = 1
    ) -> List[Job]:
        """
        Executes a search via SearXNG and routes the raw results to matching allowed providers.
        """
        allowed = [p.lower() for p in (allowed_providers or ["linkedin"])]
        logger.info(f"Executing GlobalSearch: '{query}' | Allowed providers: {allowed}")

        raw_results = self.searxng.search(query=query, pageno=pageno)
        if not raw_results:
            logger.info(f"No raw search results returned from SearXNG for query: '{query}'")
            return []

        jobs: List[Job] = []

        for item in raw_results:
            url = item.get("url", "")
            if not url:
                continue

            # Identify matching provider for this URL
            matched_provider: Optional[BaseJobProvider] = None
            for p_name in allowed:
                provider_candidate = self.get_provider(p_name)
                if provider_candidate and provider_candidate.is_provider_url(url):
                    matched_provider = provider_candidate
                    break

            # If none matched by URL, but the query itself targeted an allowed provider (e.g. site:linkedin.com)
            if not matched_provider and allowed:
                default_p = self.get_provider(allowed[0])
                if default_p and default_p.is_provider_url(url):
                    matched_provider = default_p

            if matched_provider:
                parsed_job = matched_provider.parse_result(item, search_query=query)
                if parsed_job:
                    jobs.append(parsed_job)

        logger.info(f"GlobalSearch successfully extracted {len(jobs)} jobs from {len(raw_results)} raw results.")
        return jobs


# Default shared GlobalSearch instance
default_global_search = GlobalSearch()
