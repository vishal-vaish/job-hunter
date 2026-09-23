"""
Job Availability Verification Module.

This file is responsible for:
- Verifying whether a discovered job posting is currently open and accepting applications.
- Enforcing the controlled availability status set:
  * ACTIVE
  * CLOSED
  * EXPIRED
  * REMOVED
  * UNKNOWN
- Inspecting HTTP response codes (e.g. 404 -> REMOVED/CLOSED), page content indicators
  ('No longer accepting applications', 'Job closed'), and search snippet evidence.
- Storing availability_checked_at timestamps for auditing and freshness lifecycle.
- Preventing stale search-engine results from reaching the candidate as active jobs.
"""

from datetime import datetime, timezone
import re
from typing import List, Optional
import requests

from models.job import Job
from utils.logger import get_logger

logger = get_logger("pipeline.availability")


class JobAvailabilityVerifier:
    """
    Verifies availability status of discovered jobs using HTTP headers, page indicators,
    and metadata evidence.
    """

    CLOSED_PHRASES = [
        "no longer accepting applications",
        "this job is closed",
        "this job has expired",
        "job has expired",
        "position has been filled",
        "position filled",
        "job is no longer available",
        "this listing is no longer available",
        "job posting has expired",
        "job removed"
    ]

    ACTIVE_PHRASES = [
        "apply on company website",
        "easy apply",
        "apply now",
        "submit application",
        "save job",
        "job description",
        "about the job"
    ]

    def __init__(self, timeout_seconds: int = 5) -> None:
        self.timeout = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def verify_job(self, job: Job) -> Job:
        """
        Determines the availability status of a single job listing.
        Updates job.availability_status and job.availability_checked_at in place.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        job.availability_checked_at = now_iso

        # 1. First, check snippet and title metadata for obvious closed indicators
        combined_meta = f"{job.title} {job.description}".lower()
        if any(phrase in combined_meta for phrase in self.CLOSED_PHRASES):
            job.availability_status = "CLOSED"
            logger.info(f"[AVAILABILITY] Job '{job.title}' marked CLOSED from search snippet metadata.")
            return job

        # 2. Probe the job URL directly via HTTP request
        try:
            resp = self.session.get(job.url, timeout=self.timeout, allow_redirects=True)
            status_code = resp.status_code

            # HTTP 404 or 410 -> Job is removed/closed
            if status_code in (404, 410):
                job.availability_status = "REMOVED"
                logger.info(f"[AVAILABILITY] Job '{job.title}' marked REMOVED (HTTP {status_code}) at {job.url}")
                return job

            # HTTP 200 -> Inspect page content for availability markers
            if status_code == 200:
                page_lower = resp.text.lower()

                # Check if page explicitly indicates job closed
                if any(phrase in page_lower for phrase in self.CLOSED_PHRASES):
                    job.availability_status = "CLOSED"
                    logger.info(f"[AVAILABILITY] Job '{job.title}' marked CLOSED from page content indicators.")
                    return job

                # Check for active application indicators
                if any(phrase in page_lower for phrase in self.ACTIVE_PHRASES):
                    job.availability_status = "ACTIVE"
                    logger.info(f"[AVAILABILITY] Job '{job.title}' verified ACTIVE at {job.url}")
                    return job

                # Page returned 200 but content lacks definitive active cues
                job.availability_status = "UNKNOWN"
                logger.debug(f"[AVAILABILITY] Job '{job.title}' status UNKNOWN (no clear active cues in HTML).")
                return job

            # Non-200, non-404 status codes (e.g. 403, 429, 500)
            logger.warning(f"[AVAILABILITY] HTTP {status_code} encountered for '{job.url}'.")
            job.availability_status = "UNKNOWN"
            return job

        except requests.exceptions.Timeout:
            logger.warning(f"[AVAILABILITY] Verification timed out for '{job.url}'. Status set to UNKNOWN.")
            job.availability_status = "UNKNOWN"
            return job
        except requests.exceptions.RequestException as e:
            logger.warning(f"[AVAILABILITY] Request failed for '{job.url}': {e}. Status set to UNKNOWN.")
            job.availability_status = "UNKNOWN"
            return job

    def verify_batch(self, jobs: List[Job]) -> List[Job]:
        """
        Verifies availability across a collection of Job objects.
        """
        verified_jobs: List[Job] = []
        for j in jobs:
            verified_jobs.append(self.verify_job(j))
        return verified_jobs
