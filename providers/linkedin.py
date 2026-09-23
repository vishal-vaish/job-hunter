"""
LinkedIn Job Provider Module.

This file is responsible for:
- Implementing the BaseJobProvider interface specifically for LinkedIn.
- Constructing targeted discovery queries using SearXNG (e.g. site:linkedin.com/jobs/view).
- Identifying LinkedIn job URLs, cleaning extraneous tracking parameters (trackingId, refId, trk),
  and extracting canonical job IDs.
- Parsing raw search engine snippets and titles into structured Job models without requiring
  browser automation, scraping, or CAPTCHA bypasses.
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from models.job import Job
from providers.base import BaseJobProvider
from utils.logger import get_logger

logger = get_logger("providers.linkedin")


class LinkedInProvider(BaseJobProvider):
    """
    Job search provider for LinkedIn discovery via SearXNG.
    """

    @property
    def name(self) -> str:
        return "linkedin"

    def build_search_query(
        self,
        role: str,
        location: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        extra_terms: Optional[str] = None
    ) -> str:
        """
        Builds a targeted Google/SearXNG dork query specifically matching LinkedIn job postings.
        Example: site:linkedin.com/jobs/view "Python Developer" "Delhi" "Django"
        """
        parts = ["site:linkedin.com/jobs/view"]

        # Enforce exact or clean role title match
        if role:
            clean_role = role.strip().strip('"')
            parts.append(f'"{clean_role}"')

        # Add location if specified
        if location:
            clean_loc = location.strip().strip('"')
            parts.append(f'"{clean_loc}"')

        # Add keywords if specified
        if keywords:
            for kw in keywords[:4]:
                clean_kw = kw.strip().strip('"')
                if clean_kw and clean_kw.lower() not in role.lower():
                    parts.append(clean_kw)

        # Extra search constraints (e.g. seniority terms or work modes)
        if extra_terms:
            parts.append(extra_terms.strip())

        return " ".join(parts)

    def is_provider_url(self, url: str) -> bool:
        """
        Checks whether the URL belongs to LinkedIn and points to a job posting or directory.
        Accepts:
          - https://www.linkedin.com/jobs/view/...
          - https://[country].linkedin.com/jobs/view/...
          - https://[country].linkedin.com/jobs/...
        Rejects non-job LinkedIn sections (/feed, /in/, /company/, /school/, /pulse).
        """
        if not url:
            return False
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if "linkedin.com" not in domain:
            return False

        path = parsed.path.lower()

        # Reject explicitly non-job LinkedIn paths
        non_job_prefixes = (
            "/feed", "/in/", "/company/", "/school/", "/pulse",
            "/groups", "/events", "/login", "/signup", "/checkpoint", "/m/"
        )
        for prefix in non_job_prefixes:
            if path.startswith(prefix) and "/jobs" not in path:
                return False

        # Matches job views, collections, search directories, and general job paths
        return "/jobs/view" in path or path.startswith("/jobs") or "/jobs/" in path

    def clean_url(self, url: str) -> str:
        """
        Normalizes LinkedIn job URLs:
        - Extracts the core /jobs/view/<job_id> path.
        - Strips tracking tokens (trackingId, refId, trk, position, pageNum, etc.).
        """
        if not url:
            return ""

        parsed = urlparse(url)
        # Check for /jobs/view/<id> or /jobs/view/slug-<id>
        match = re.search(r"/jobs/view/(?:[^/?#]+-)?(\d+)", parsed.path)
        if match:
            # Canonical standard format: https://www.linkedin.com/jobs/view/<id>
            job_id = match.group(1)
            return f"https://www.linkedin.com/jobs/view/{job_id}"

        # If it's a generic /jobs/ path, strip tracking query parameters
        clean_parts = list(parsed)
        if clean_parts[4]:
            q_dict = parse_qs(clean_parts[4])
            tracking_keys = {
                "trackingid", "refid", "trk", "midtoken", "position",
                "pagenum", "orig", "currentjobid", "originalsubdomain",
                "geoid", "distance"
            }
            cleaned_q = {k: v for k, v in q_dict.items() if k.lower() not in tracking_keys}
            clean_parts[4] = urlencode(cleaned_q, doseq=True)
        clean_parts[5] = ""  # remove fragment
        return urlunparse(clean_parts).rstrip("/")

    def parse_result_detailed(
        self,
        raw_result: Dict[str, Any],
        search_query: str
    ) -> Tuple[Optional[Job], Optional[str]]:
        """
        Converts a SearXNG result item into a normalized Job model with detailed failure rationale.
        Extracts title, company, and location using heuristic parsing of the search title and snippet.
        Guarantees that results are never rejected merely because company or location is 'Unknown'.
        """
        raw_url = str(raw_result.get("url") or "").strip()
        if not raw_url:
            return None, "Missing or empty URL in raw search result"

        if not self.is_provider_url(raw_url):
            return None, f"URL '{raw_url}' is not a recognized LinkedIn job URL"

        canonical_url = self.clean_url(raw_url)
        raw_title = str(raw_result.get("title") or "").strip()
        raw_content = str(raw_result.get("content") or "").strip()

        # Clean common LinkedIn title suffixes
        # e.g. "Software Engineer - Acme Corp - Bengaluru | LinkedIn"
        title_clean = re.sub(r"\s*\|\s*LinkedIn.*$", "", raw_title, flags=re.IGNORECASE).strip()
        title_clean = re.sub(r"\s*-\s*LinkedIn.*$", "", title_clean, flags=re.IGNORECASE).strip()

        # If title is empty, attempt extraction from URL slug
        if not title_clean:
            parsed_path = urlparse(raw_url).path
            slug_match = re.search(r"/jobs/view/([a-zA-Z0-9-]+)-\d+", parsed_path)
            if slug_match:
                title_clean = slug_match.group(1).replace("-", " ").title()
            else:
                title_clean = "Job Posting"

        company = "Unknown"
        location = "Unknown"
        job_title = title_clean

        # Heuristic Pattern 1: "Company hiring Role in Location"
        hiring_match = re.search(r"^(.+?)\s+hiring\s+(.+?)\s+in\s+(.+)$", title_clean, re.IGNORECASE)
        if hiring_match:
            company = hiring_match.group(1).strip()
            job_title = hiring_match.group(2).strip()
            location = hiring_match.group(3).strip()
        else:
            # Heuristic Pattern 2: "Role - Company - Location" or "Role - Company"
            if " - " in title_clean:
                segments = [s.strip() for s in title_clean.split(" - ") if s.strip()]
                if len(segments) >= 3:
                    job_title = segments[0]
                    company = segments[1]
                    location = segments[2]
                elif len(segments) == 2:
                    job_title = segments[0]
                    company = segments[1]
            elif " at " in title_clean:
                at_parts = title_clean.split(" at ", 1)
                job_title = at_parts[0].strip()
                comp_part = at_parts[1].strip()
                if " in " in comp_part:
                    c_sub, l_sub = comp_part.split(" in ", 1)
                    company = c_sub.strip()
                    location = l_sub.strip()
                else:
                    company = comp_part

        # Clean extraneous quotes
        job_title = job_title.strip("\"' ")
        company = company.strip("\"' ")
        location = location.strip("\"' ")

        # Extract posted date string if present
        posted_raw = raw_result.get("publishedDate") or raw_result.get("pubdate")
        posted_text = str(posted_raw) if posted_raw is not None else None
        if not posted_text and raw_content:
            date_match = re.search(r"\b(\d+\s+(?:days?|weeks?|months?|hours?)\s+ago)\b", raw_content, re.IGNORECASE)
            if date_match:
                posted_text = date_match.group(1)

        try:
            job = Job(
                provider=self.name,
                title=job_title or "Job Posting",
                company=company or "Unknown",
                location=location or "Unknown",
                url=canonical_url,
                description=raw_content,
                posted_text=posted_text,
                search_query=search_query,
                metadata={
                    "engines": raw_result.get("engines", []),
                    "score": raw_result.get("score", 0.0),
                    "original_title": raw_title
                }
            )
            return job, None
        except Exception as e:
            logger.warning(f"Failed to instantiate Job model for '{canonical_url}': {e}")
            return None, f"Job model validation error: {e}"

    def parse_result(self, raw_result: Dict[str, Any], search_query: str) -> Optional[Job]:
        """
        Converts a SearXNG result item into a normalized Job model.
        Returns None if parsing fails.
        """
        job, _ = self.parse_result_detailed(raw_result, search_query=search_query)
        return job
