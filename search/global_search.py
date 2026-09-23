"""
Global Search Orchestrator Module.

This file is responsible for:
- Implementing the GlobalSearch routing layer between the Agent Search Tool and Job Providers.
- Decoupling the Autonomous Brain from provider-specific mechanics (e.g. LinkedIn dorks, URL patterns).
- Dispatching search queries to SearXNG and routing discovered items to the appropriate
  registered provider (e.g. LinkedIn, and future providers like Indeed or Naukri).
- Aggregating, normalizing, and returning standardized Job models.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from infrastructure.searxng import SearXNGClient
from models.job import Job
from providers.base import BaseJobProvider
from providers.linkedin import LinkedInProvider
from utils.logger import get_logger

logger = get_logger("search.global_search")


@dataclass
class SearchTelemetry:
    """
    Structured metrics capturing the full lifecycle of a search execution:
    raw_results -> provider_matches -> parse_successes -> parse_failures.
    """
    query: str = ""
    raw_results: int = 0
    provider_matches: int = 0
    parse_successes: int = 0
    parse_failures: int = 0
    unmatched_urls: int = 0
    rejections: List[Dict[str, Any]] = field(default_factory=list)

    def summary_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "raw_results": self.raw_results,
            "provider_matches": self.provider_matches,
            "parse_successes": self.parse_successes,
            "parse_failures": self.parse_failures,
            "unmatched_urls": self.unmatched_urls,
            "rejections": self.rejections
        }


class GlobalSearch:
    """
    Search router that coordinates queries across multiple pluggable providers via SearXNG.
    """

    def __init__(self, searxng_client: Optional[SearXNGClient] = None) -> None:
        self.searxng = searxng_client or SearXNGClient()
        self._providers: Dict[str, BaseJobProvider] = {}
        self.last_telemetry: SearchTelemetry = SearchTelemetry()

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
        Captures comprehensive diagnostic telemetry:
          - raw_results
          - provider_matches
          - parse_successes
          - parse_failures
          - unmatched_urls
        """
        allowed = [p.lower() for p in (allowed_providers or ["linkedin"])]
        logger.info(f"Executing GlobalSearch: '{query}' | Allowed providers: {allowed}")

        telemetry = SearchTelemetry(query=query)
        raw_results = self.searxng.search(query=query, pageno=pageno)
        telemetry.raw_results = len(raw_results)

        if not raw_results:
            logger.info(f"No raw search results returned from SearXNG for query: '{query}'")
            self.last_telemetry = telemetry
            return []

        jobs: List[Job] = []

        for idx, item in enumerate(raw_results, 1):
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()

            if not url:
                telemetry.parse_failures += 1
                reason = "Missing or empty URL in raw search result"
                telemetry.rejections.append({
                    "index": idx,
                    "url": "",
                    "title": title,
                    "reason": reason
                })
                logger.debug(
                    f"[SEARCH_PARSE] raw_result #{idx} url='' title='{title[:60]}' "
                    f"provider_match=false parse_result=failure reason='{reason}'"
                )
                continue

            # Identify matching provider for this URL
            matched_provider: Optional[BaseJobProvider] = None
            for p_name in allowed:
                provider_candidate = self.get_provider(p_name)
                if provider_candidate and provider_candidate.is_provider_url(url):
                    matched_provider = provider_candidate
                    break

            # If none matched by URL, check default allowed provider
            if not matched_provider and allowed:
                default_p = self.get_provider(allowed[0])
                if default_p and default_p.is_provider_url(url):
                    matched_provider = default_p

            if not matched_provider:
                telemetry.unmatched_urls += 1
                reason = f"URL domain/path does not match any allowed provider ({allowed})"
                telemetry.rejections.append({
                    "index": idx,
                    "url": url,
                    "title": title,
                    "reason": reason
                })
                logger.info(
                    f"[SEARCH_PARSE] raw_result #{idx} url='{url}' title='{title[:60]}' "
                    f"provider_match=false parse_result=skipped reason='{reason}'"
                )
                continue

            # URL matched an allowed provider
            telemetry.provider_matches += 1

            # Parse result with detailed failure extraction
            if hasattr(matched_provider, "parse_result_detailed"):
                parsed_job, fail_reason = matched_provider.parse_result_detailed(item, search_query=query)
            else:
                parsed_job = matched_provider.parse_result(item, search_query=query)
                fail_reason = "Provider parse_result returned None" if not parsed_job else None

            if parsed_job:
                telemetry.parse_successes += 1
                jobs.append(parsed_job)
                logger.info(
                    f"[SEARCH_PARSE] raw_result #{idx} url='{url}' title='{parsed_job.title[:60]}' "
                    f"provider_match=true parse_result=success provider='{matched_provider.name}'"
                )
            else:
                telemetry.parse_failures += 1
                reason = fail_reason or "Unknown parser rejection"
                telemetry.rejections.append({
                    "index": idx,
                    "url": url,
                    "title": title,
                    "reason": reason
                })
                logger.warning(
                    f"[SEARCH_PARSE] {matched_provider.name.capitalize()} result rejected: "
                    f"reason='{reason}' url='{url}' title='{title[:60]}'"
                )

        self.last_telemetry = telemetry

        # Emit structured telemetry diagnostic log
        telemetry_log = (
            f"\n[SEARCH_TELEMETRY]\n"
            f"Query: {query}\n"
            f"SearXNG:\n"
            f"  raw_results={telemetry.raw_results}\n"
            f"Provider:\n"
            f"  provider_matches={telemetry.provider_matches}\n"
            f"  unmatched_urls={telemetry.unmatched_urls}\n"
            f"Parser:\n"
            f"  parse_successes={telemetry.parse_successes}\n"
            f"  parse_failures={telemetry.parse_failures}\n"
            f"GlobalSearch:\n"
            f"  jobs={len(jobs)}"
        )
        logger.info(telemetry_log)
        return jobs


# Default shared GlobalSearch instance
default_global_search = GlobalSearch()
