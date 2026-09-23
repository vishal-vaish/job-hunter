"""
Job Listing Normalizer Module.

This file is responsible for:
- Sanitizing raw text fields extracted from search engine snippets and titles.
- Unescaping HTML entities (&amp;, &lt;, &gt;, &quot;, &#39;, &nbsp;, \\xa0).
- Standardizing titles, company names, and locations into clean, uniform strings.
- Parsing and normalizing posting age from relative phrases ('Today', '2 days ago', '1 week ago')
  and timestamp formats into standardized posted_at, posted_age_days, and confidence levels.
- Producing normalized Job instances ready for deduplication and filtering.
"""

from datetime import datetime, timezone, timedelta
import html
import re
from typing import Optional, Tuple
from models.job import Job
from utils.logger import get_logger

logger = get_logger("pipeline.normalizer")


class JobNormalizer:
    """
    Normalizes and cleans fields within a Job instance.
    """

    @staticmethod
    def clean_text(text: str) -> str:
        """
        Removes HTML tags, decodes HTML entities, and collapses redundant whitespace.
        """
        if not text:
            return ""
        # Unescape HTML entities
        text = html.unescape(text)
        # Strip HTML markup tags if present in snippets
        text = re.sub(r"<[^>]+>", " ", text)
        # Replace non-breaking spaces and irregular whitespace characters
        text = text.replace("\xa0", " ").replace("\u200b", "")
        # Collapse multiple whitespace characters into a single space
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @classmethod
    def parse_posting_age(
        cls,
        posted_text: Optional[str],
        fallback_text: str = ""
    ) -> Tuple[Optional[str], Optional[int], str]:
        """
        Parses raw posting text or fallback snippet into normalized:
        (posted_at_iso, posted_age_days, confidence)

        Confidence levels:
        - 'high': derived from exact date/timestamp
        - 'medium': derived from explicit relative text (e.g. '2 days ago', '1 week ago')
        - 'unknown': no reliable posting age could be determined
        """
        now_utc = datetime.now(timezone.utc)

        # 1. Check if posted_text is an exact date or timestamp
        if posted_text:
            clean_str = posted_text.strip()

            # Attempt ISO format parsing
            try:
                # Handle trailing 'Z' if present
                iso_str = clean_str.replace("Z", "+00:00")
                dt = datetime.fromisoformat(iso_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_days = max(0, (now_utc - dt).days)
                return dt.isoformat(), age_days, "high"
            except (ValueError, TypeError):
                pass

            # Attempt common human date formats
            for fmt in (
                "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y",
                "%b %d, %Y", "%d %b %Y", "%B %d, %Y", "%d %B %Y"
            ):
                try:
                    dt = datetime.strptime(clean_str, fmt).replace(tzinfo=timezone.utc)
                    age_days = max(0, (now_utc - dt).days)
                    return dt.isoformat(), age_days, "high"
                except (ValueError, TypeError):
                    continue

        # 2. Check for relative phrases in posted_text or fallback content
        candidates_to_check = []
        if posted_text:
            candidates_to_check.append(posted_text.lower())
        if fallback_text:
            candidates_to_check.append(fallback_text.lower())

        for text in candidates_to_check:
            # Matches 'today', 'just posted', 'just now'
            if re.search(r"\b(today|just posted|just now)\b", text):
                return now_utc.isoformat(), 0, "medium"

            # Matches 'X hours/mins ago'
            if re.search(r"\b\d+\s*(?:hour|hr|minute|min)s?\s*ago\b", text):
                return now_utc.isoformat(), 0, "medium"

            # Matches 'X day(s) ago'
            m_day = re.search(r"\b(\d+)\s*day[s]?\s*ago\b", text)
            if m_day:
                days = int(m_day.group(1))
                posted_dt = now_utc - timedelta(days=days)
                return posted_dt.isoformat(), days, "medium"

            # Matches 'X week(s) ago'
            m_week = re.search(r"\b(\d+)\s*week[s]?\s*ago\b", text)
            if m_week:
                weeks = int(m_week.group(1))
                days = weeks * 7
                posted_dt = now_utc - timedelta(days=days)
                return posted_dt.isoformat(), days, "medium"

            # Matches 'X month(s) ago'
            m_month = re.search(r"\b(\d+)\s*month[s]?\s*ago\b", text)
            if m_month:
                months = int(m_month.group(1))
                days = months * 30
                posted_dt = now_utc - timedelta(days=days)
                return posted_dt.isoformat(), days, "medium"

        # 3. Unable to determine reliable posting age
        return None, None, "unknown"

    @classmethod
    def normalize_job(cls, job: Job) -> Job:
        """
        Returns a sanitized and normalized copy of the Job model with normalized posting age.
        """
        clean_title = cls.clean_text(job.title)
        clean_company = cls.clean_text(job.company)
        clean_location = cls.clean_text(job.location)
        clean_description = cls.clean_text(job.description)

        # Standardize empty or missing values to 'Unknown'
        if not clean_company or clean_company.lower() in {"unknown", "n/a", "none"}:
            clean_company = "Unknown"

        if not clean_location or clean_location.lower() in {"unknown", "n/a", "none"}:
            clean_location = "Unknown"

        # Parse posting age
        posted_at, posted_age_days, confidence = cls.parse_posting_age(
            posted_text=job.posted_text,
            fallback_text=f"{clean_title} {clean_description}"
        )

        return Job(
            provider=job.provider.strip().lower(),
            title=clean_title,
            company=clean_company,
            location=clean_location,
            url=job.url.strip(),
            description=clean_description,
            posted_text=job.posted_text,
            posted_at=posted_at,
            posted_age_days=posted_age_days,
            posting_date_confidence=confidence,
            availability_status=job.availability_status,
            availability_checked_at=job.availability_checked_at,
            search_query=job.search_query,
            discovered_at=job.discovered_at,
            metadata=job.metadata
        )

    @classmethod
    def normalize_batch(cls, jobs: list[Job]) -> list[Job]:
        """
        Normalizes a collection of Job objects.
        """
        return [cls.normalize_job(j) for j in jobs]
