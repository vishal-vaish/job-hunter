"""
Job Availability Verification Module.

Availability is evidence-based.

Important:
- ACTIVE means we found positive evidence that the job is open.
- CLOSED/EXPIRED/REMOVED means we found explicit evidence that the job is no
  longer available.
- UNKNOWN means the job could not be reliably verified. UNKNOWN is NOT the
  same as CLOSED.
"""

import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple
import requests

from models.job import Job
from utils.logger import get_logger

logger = get_logger("pipeline.availability")


class JobAvailabilityVerifier:
    """
    Verifies availability of discovered job listings.

    For providers such as LinkedIn, direct HTTP access can return login pages,
    bot protection, 403/429 responses, or incomplete HTML. Those cases must
    remain UNKNOWN rather than being treated as CLOSED.
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
        "job removed",
        "no longer available",
        "applications are closed",
        "applications closed",
    ]

    ACTIVE_PHRASES = [
        "apply now",
        "easy apply",
        "apply on company website",
        "submit application",
        "apply",
        "save job",
        "job description",
        "about the job",
        "responsibilities",
        "qualifications",
    ]

    BLOCKED_STATUS_CODES = {
        401,
        403,
        429,
        451,
        500,
        502,
        503,
        504,
    }

    def __init__(self, timeout_seconds: int = 8) -> None:
        self.timeout = timeout_seconds

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    @staticmethod
    def _contains_phrase(text: str, phrases: List[str]) -> bool:
        if not text:
            return False

        text_lower = text.lower()
        return any(phrase in text_lower for phrase in phrases)

    @staticmethod
    def _set_evidence(job: Job, status: str, reason: str) -> None:
        job.availability_status = status

        if job.metadata is None:
            job.metadata = {}

        job.metadata["availability"] = {
            "status": status,
            "reason": reason,
            "checked_at": job.availability_checked_at,
        }

    @staticmethod
    def extract_html_posting_date(html: str) -> Optional[str]:
        """
        Extracts posting date text from HTML elements on the page.
        Primary source: LinkedIn posted-time-ago__text element in topcard.
        Fallback elements: JSON-LD datePosted, HTML5 <time> tag, meta date tags.
        """
        if not html:
            return None

        # 1. Primary: LinkedIn posted-time-ago__text (found in topcard header)
        m = re.search(
            r'class=[\'"][^\'"]*posted-time-ago__text[^\'"]*[\'"][^>]*>(.*?)</span',
            html,
            re.DOTALL | re.IGNORECASE
        )
        if m:
            cleaned = re.sub(r'<[^>]+>', ' ', m.group(1)).strip()
            cleaned = re.sub(r'\s+', ' ', cleaned)
            if cleaned:
                return cleaned

        # 2. JSON-LD datePosted
        m = re.search(
            r'["\']datePosted["\']\s*:\s*["\']([^"\']+)["\']',
            html,
            re.IGNORECASE
        )
        if m:
            return m.group(1).strip()

        # 3. HTML5 <time> tag datetime attribute or text
        m = re.search(
            r'<time[^>]*datetime=[\'"]([^\'"]+)[\'"]',
            html,
            re.IGNORECASE
        )
        if m:
            return m.group(1).strip()

        m = re.search(
            r'<time[^>]*>(.*?)</time>',
            html,
            re.DOTALL | re.IGNORECASE
        )
        if m:
            cleaned = re.sub(r'<[^>]+>', ' ', m.group(1)).strip()
            cleaned = re.sub(r'\s+', ' ', cleaned)
            if cleaned:
                return cleaned

        # 4. Metadata tags
        m = re.search(
            r'<meta[^>]+(?:itemprop|property)=[\'"](?:datePosted|article:published_time)[\'"][^>]+content=[\'"]([^\'"]+)[\'"]',
            html,
            re.IGNORECASE
        )
        if m:
            return m.group(1).strip()

        return None

    def verify_job(self, job: Job) -> Job:
        """
        Determines availability status of one job.

        UNKNOWN is deliberately preserved when direct verification cannot
        reliably determine whether the job is active or closed.
        """

        now_iso = datetime.now(timezone.utc).isoformat()
        job.availability_checked_at = now_iso

        # ---------------------------------------------------------
        # 1. Search-result metadata / snippet evidence
        # ---------------------------------------------------------

        combined_meta = " ".join([
            str(job.title or ""),
            str(job.description or ""),
            str(job.posted_text or ""),
        ])

        if self._contains_phrase(combined_meta, self.CLOSED_PHRASES):
            self._set_evidence(
                job,
                "CLOSED",
                "Explicit closed/expired phrase found in search metadata.",
            )

            logger.info(
                f"[AVAILABILITY] '{job.title}' -> CLOSED "
                f"(search metadata evidence)"
            )
            return job

        # ---------------------------------------------------------
        # 2. Direct HTTP verification
        # ---------------------------------------------------------

        try:
            resp = self.session.get(
                job.url,
                timeout=self.timeout,
                allow_redirects=True,
            )

            status_code = resp.status_code
            final_url = str(resp.url or job.url)

            # Save verification information for auditing.
            if job.metadata is None:
                job.metadata = {}

            job.metadata["availability_http"] = {
                "status_code": status_code,
                "final_url": final_url,
            }

            # -----------------------------------------------------
            # Explicitly removed
            # -----------------------------------------------------

            if status_code in (404, 410):
                self._set_evidence(
                    job,
                    "REMOVED",
                    f"HTTP {status_code} indicates the listing is unavailable.",
                )

                logger.info(
                    f"[AVAILABILITY] '{job.title}' -> REMOVED "
                    f"(HTTP {status_code})"
                )
                return job

            # -----------------------------------------------------
            # Access blocked / rate limited / server problem
            #
            # IMPORTANT:
            # These do NOT prove the job is closed.
            # -----------------------------------------------------

            if status_code in self.BLOCKED_STATUS_CODES:
                self._set_evidence(
                    job,
                    "UNKNOWN",
                    f"Direct verification unavailable because HTTP {status_code} "
                    f"was returned.",
                )

                logger.warning(
                    f"[AVAILABILITY] '{job.title}' -> UNKNOWN "
                    f"(HTTP {status_code}; not treated as CLOSED)"
                )
                return job

            # -----------------------------------------------------
            # Redirected to login/checkpoint
            # -----------------------------------------------------

            final_url_lower = final_url.lower()

            if any(
                marker in final_url_lower
                for marker in (
                    "/login",
                    "/signup",
                    "/checkpoint",
                    "/authwall",
                )
            ):
                self._set_evidence(
                    job,
                    "UNKNOWN",
                    f"Direct page redirected to authentication/protection page: "
                    f"{final_url}",
                )

                logger.warning(
                    f"[AVAILABILITY] '{job.title}' -> UNKNOWN "
                    f"(authentication/protection redirect)"
                )
                return job

            # -----------------------------------------------------
            # HTTP 200 / inspect page
            # -----------------------------------------------------

            if status_code == 200:
                html_text = resp.text or ""
                page_lower = html_text.lower()

                # Extract posting date from HTML element first; if not found, retain timestamp
                html_posted_date = self.extract_html_posting_date(html_text)
                if html_posted_date:
                    from pipeline.normalizer import JobNormalizer
                    posted_at, age_days, confidence = JobNormalizer.parse_posting_age(html_posted_date)
                    job.posted_text = html_posted_date
                    job.posted_at = posted_at
                    job.posted_age_days = age_days
                    job.posting_date_confidence = "high"
                    logger.info(
                        f"[AVAILABILITY] Extracted authoritative posting age from HTML element for '{job.title}': "
                        f"'{html_posted_date}' ({age_days}d)"
                    )
                else:
                    logger.debug(
                        f"[AVAILABILITY] No posting age HTML element found for '{job.title}'; "
                        f"retaining timestamp: '{job.posted_text}' ({job.posted_age_days}d)"
                    )

                if self._contains_phrase(
                    page_lower,
                    self.CLOSED_PHRASES,
                ):
                    self._set_evidence(
                        job,
                        "CLOSED",
                        "Explicit closed/expired phrase found in page content.",
                    )

                    logger.info(
                        f"[AVAILABILITY] '{job.title}' -> CLOSED "
                        f"(page evidence)"
                    )
                    return job

                if self._contains_phrase(
                    page_lower,
                    self.ACTIVE_PHRASES,
                ):
                    self._set_evidence(
                        job,
                        "ACTIVE",
                        "Active application/job-page evidence found in HTML.",
                    )

                    logger.info(
                        f"[AVAILABILITY] '{job.title}' -> ACTIVE"
                    )
                    return job

                # 200 does not automatically mean ACTIVE.
                self._set_evidence(
                    job,
                    "UNKNOWN",
                    "HTTP 200 received but no reliable active/closed evidence "
                    "was found.",
                )

                logger.info(
                    f"[AVAILABILITY] '{job.title}' -> UNKNOWN "
                    f"(HTTP 200 without definitive availability evidence)"
                )
                return job

            # -----------------------------------------------------
            # Any other status
            # -----------------------------------------------------

            self._set_evidence(
                job,
                "UNKNOWN",
                f"HTTP {status_code} did not provide reliable availability evidence.",
            )

            logger.warning(
                f"[AVAILABILITY] '{job.title}' -> UNKNOWN "
                f"(HTTP {status_code})"
            )
            return job

        except requests.exceptions.Timeout:
            self._set_evidence(
                job,
                "UNKNOWN",
                "Direct verification timed out.",
            )

            logger.warning(
                f"[AVAILABILITY] '{job.title}' -> UNKNOWN (timeout)"
            )
            return job

        except requests.exceptions.RequestException as exc:
            self._set_evidence(
                job,
                "UNKNOWN",
                f"Direct verification request failed: {exc}",
            )

            logger.warning(
                f"[AVAILABILITY] '{job.title}' -> UNKNOWN "
                f"(request failure: {exc})"
            )
            return job

    def verify_batch(self, jobs: List[Job]) -> List[Job]:
        """
        Verifies availability across a collection of jobs.
        """

        verified_jobs: List[Job] = []

        for job in jobs:
            verified_jobs.append(self.verify_job(job))

        counts = {
            "ACTIVE": 0,
            "CLOSED": 0,
            "EXPIRED": 0,
            "REMOVED": 0,
            "UNKNOWN": 0,
        }

        for job in verified_jobs:
            status = job.availability_status or "UNKNOWN"
            counts[status] = counts.get(status, 0) + 1

        logger.info(
            "[AVAILABILITY] Batch complete: "
            f"ACTIVE={counts.get('ACTIVE', 0)}, "
            f"CLOSED={counts.get('CLOSED', 0)}, "
            f"EXPIRED={counts.get('EXPIRED', 0)}, "
            f"REMOVED={counts.get('REMOVED', 0)}, "
            f"UNKNOWN={counts.get('UNKNOWN', 0)}"
        )

        return verified_jobs
