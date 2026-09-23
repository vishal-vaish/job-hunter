"""
Job Deduplication Module.

This file is responsible for:
- Detecting and filtering out duplicate job postings discovered across searches and iterations.
- Normalizing URLs by stripping query tracking strings (UTM, refId, trackingId, session tokens).
- Canonicalizing provider URLs (e.g., standardizing LinkedIn job IDs).
- Checking against both in-memory seen URLs and persistent memory state.
- Preventing the system from evaluating the same job posting repeatedly.
"""

import re
from typing import List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from models.job import Job
from utils.logger import get_logger

logger = get_logger("pipeline.deduplicator")


class JobDeduplicator:
    """
    Handles URL normalization and deduplication across search results.
    """

    # Query parameters that do not identify the job and should be stripped
    TRACKING_PARAMS: Set[str] = {
        "trackingid", "refid", "trk", "trkinfo", "position", "pagenum",
        "currentjobid", "originalsubdomain", "utm_source", "utm_medium",
        "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid",
        "midtoken", "eBP", "rcm"
    }

    def __init__(self, initial_urls: Optional[Set[str]] = None) -> None:
        self.seen_urls: Set[str] = set(initial_urls or [])
        self.seen_signatures: Set[str] = set()

    @classmethod
    def normalize_url(cls, url: str) -> str:
        """
        Normalizes a URL to a canonical format for robust deduplication:
        - Converts scheme and netloc to lowercase.
        - Strips default ports and fragments.
        - Removes tracking query parameters.
        - Canonicalizes LinkedIn job URLs to https://www.linkedin.com/jobs/view/<job_id>.
        """
        if not url:
            return ""

        url_str = url.strip()
        parsed = urlparse(url_str)

        scheme = "https"  # Standardize all web listings to https
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]

        path = parsed.path.rstrip("/")

        # Check for LinkedIn job id pattern
        if "linkedin.com" in netloc:
            match = re.search(r"/jobs/view/(?:[^/?]+-)?(\d+)", path)
            if match:
                job_id = match.group(1)
                return f"https://linkedin.com/jobs/view/{job_id}"

        # Filter out tracking query parameters
        query_dict = parse_qs(parsed.query, keep_blank_values=False)
        cleaned_params = {
            k: v for k, v in query_dict.items()
            if k.lower() not in cls.TRACKING_PARAMS
        }
        clean_query = urlencode(cleaned_params, doseq=True)

        return urlunparse((scheme, netloc, path, "", clean_query, "")).rstrip("/")

    @classmethod
    def get_job_signature(cls, job: Job) -> str:
        """
        Generates a fuzzy composite signature (company + title) to catch duplicate
        postings across different URL aliases.
        """
        norm_company = re.sub(r"[^a-z0-9]", "", job.company.lower())
        norm_title = re.sub(r"[^a-z0-9]", "", job.title.lower())
        return f"{norm_company}::{norm_title}"

    def is_duplicate(self, job: Job) -> bool:
        """
        Checks whether the job has already been seen via URL or exact signature.
        """
        norm_url = self.normalize_url(job.url)
        if norm_url in self.seen_urls:
            return True

        sig = self.get_job_signature(job)
        # Only use signature deduplication if company is known and not generic
        if job.company != "Unknown" and sig in self.seen_signatures:
            return True

        return False

    def mark_seen(self, job: Job) -> None:
        """
        Registers a job's URL and signature as seen.
        """
        norm_url = self.normalize_url(job.url)
        self.seen_urls.add(norm_url)
        if job.company != "Unknown":
            self.seen_signatures.add(self.get_job_signature(job))

    def deduplicate(
        self,
        jobs: List[Job],
        external_seen_urls: Optional[Set[str]] = None
    ) -> Tuple[List[Job], int]:
        """
        Filters out duplicate jobs from a batch, updating the deduplicator's state.
        Optionally takes an external set of seen URLs (e.g. loaded from persistent memory).
        Returns a tuple of (unique_jobs, duplicate_count).
        """
        if external_seen_urls:
            for u in external_seen_urls:
                self.seen_urls.add(self.normalize_url(u))

        unique_jobs: List[Job] = []
        duplicates_count = 0

        for job in jobs:
            # Canonicalize job's own URL field in place
            job.url = self.normalize_url(job.url)

            if self.is_duplicate(job):
                duplicates_count += 1
                logger.debug(f"Discarding duplicate job: '{job.title}' at '{job.company}' ({job.url})")
            else:
                self.mark_seen(job)
                unique_jobs.append(job)

        logger.info(f"Deduplication complete: {len(unique_jobs)} unique jobs kept, {duplicates_count} duplicates removed.")
        return unique_jobs, duplicates_count
