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
from typing import Any, Dict, List, Optional
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
        Checks whether the URL belongs to LinkedIn and points to a job posting.
        """
        if not url:
            return False
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if "linkedin.com" not in domain:
            return False
        # Matches job views, job postings, or job directory items
        return "/jobs/view" in parsed.path or "/jobs/" in parsed.path

    def clean_url(self, url: str) -> str:
        """
        Normalizes LinkedIn job URLs:
        - Extracts the core /jobs/view/<job_id> path.
        - Strips tracking tokens (trackingId, refId, trk, position, pageNum, etc.).
        """
        if not url:
            return ""

        parsed = urlparse(url)
        # Check for /jobs/view/<id>
        match = re.search(r"(/jobs/view/(?:[^/?]+-)?(\d+))", parsed.path)
        if match:
            # Canonical standard format: https://www.linkedin.com/jobs/view/<id>
            job_id = match.group(2)
            return f"https://www.linkedin.com/jobs/view/{job_id}"

        # If it's a generic /jobs/ path, strip all query and fragment tracking
        # Whitelist only essential params if needed, or drop all tracking params
        clean_parts = list(parsed)
        clean_parts[4] = ""  # remove query params
        clean_parts[5] = ""  # remove fragment
        return urlunparse(clean_parts).rstrip("/")

    def parse_result(self, raw_result: Dict[str, Any], search_query: str) -> Optional[Job]:
        """
        Converts a SearXNG result item into a normalized Job model.
        Extracts title, company, and location using heuristic parsing of the search title and snippet.
        """
        raw_url = raw_result.get("url", "")
        if not self.is_provider_url(raw_url):
            return None

        canonical_url = self.clean_url(raw_url)
        raw_title = raw_result.get("title", "").strip()
        raw_content = raw_result.get("content", "").strip()

        # Clean common LinkedIn title suffixes
        # e.g. "Software Engineer - Acme Corp - Bengaluru | LinkedIn"
        title_clean = re.sub(r"\s*\|\s*LinkedIn.*$", "", raw_title, flags=re.IGNORECASE)
        title_clean = re.sub(r"\s*-\s*LinkedIn.*$", "", title_clean, flags=re.IGNORECASE)

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
            # Heuristic Pattern 2: "Role - Company - Location" or "Role at Company"
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
                company = at_parts[1].strip()

        # Clean snippet content
        description = raw_content

        return Job(
            provider=self.name,
            title=job_title,
            company=company,
            location=location,
            url=canonical_url,
            description=description,
            posted_text=raw_result.get("publishedDate") or raw_result.get("pubdate"),
            search_query=search_query,
            metadata={
                "engines": raw_result.get("engines", []),
                "score": raw_result.get("score", 0.0),
                "original_title": raw_title
            }
        )
