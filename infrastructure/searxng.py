"""
SearXNG Local Meta-Search Client Module.

This file is responsible for:
- Querying the local SearXNG meta-search instance (default: http://localhost:8081).
- Executing searches across enabled search engines and returning normalized JSON results.
- Providing defensive error handling (timeouts, empty results, network glitches)
  to ensure the Autonomous Brain never crashes due to search engine anomalies.
- Restricting search mechanics to local discovery without exposing arbitrary HTTP scraping to the LLM.
"""

from typing import Any, Dict, List, Optional
import requests

from config.settings import settings
from utils.logger import get_logger

logger = get_logger("infrastructure.searxng")


class SearXNGError(Exception):
    """Raised when SearXNG fails or returns an unrecoverable error."""
    pass


class SearXNGClient:
    """
    Client for interacting with local SearXNG meta-search API.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None
    ) -> None:
        self.base_url = (base_url or settings.searxng_base_url).rstrip("/")
        self.timeout = timeout or settings.searxng_timeout_seconds

    def check_health(self) -> bool:
        """
        Verifies that SearXNG is reachable and serving HTTP requests.
        """
        try:
            resp = requests.get(f"{self.base_url}/", timeout=3)
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"SearXNG health check failed at {self.base_url}: {e}")
            return False

    def search(
        self,
        query: str,
        categories: str = "general",
        time_range: Optional[str] = None,
        pageno: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Executes a search query against SearXNG and retrieves results as a list of raw dicts.
        Returns an empty list on failure rather than crashing the system.
        """
        endpoint = f"{self.base_url}/search"
        params: Dict[str, Any] = {
            "q": query,
            "format": "json",
            "categories": categories,
            "pageno": pageno,
            "safesearch": 0,
        }
        if time_range:
            params["time_range"] = time_range

        logger.info(f"Querying SearXNG: '{query}' (page {pageno})")

        try:
            resp = requests.get(endpoint, params=params, timeout=self.timeout)
            if resp.status_code != 200:
                logger.error(f"SearXNG returned HTTP {resp.status_code} for query '{query}': {resp.text[:200]}")
                return []

            data = resp.json()
            results = data.get("results", [])
            logger.info(f"SearXNG returned {len(results)} results for query: '{query}'")
            return results

        except requests.exceptions.Timeout:
            logger.warning(f"SearXNG query timed out after {self.timeout}s: '{query}'")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error querying SearXNG: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing SearXNG response: {e}")
            return []
