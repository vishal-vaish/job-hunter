"""
Job Model Module.

This file is responsible for:
- Defining the normalized, provider-independent Job representation.
- Storing vital job listing attributes: provider, title, company, location, url,
  description, posted text, query used, and metadata.
- Ensuring provider-specific artifacts do not leak into core agent components.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class Job(BaseModel):
    """
    Standard normalized job listing representation used across pipeline and agent tools.
    """
    provider: str = Field(
        ...,
        description="Name of the discovery provider (e.g., 'linkedin')"
    )
    title: str = Field(
        ...,
        description="Job title extracted from the listing"
    )
    company: str = Field(
        default="Unknown",
        description="Hiring company or organization name"
    )
    location: str = Field(
        default="Unknown",
        description="Job location or work arrangement"
    )
    url: str = Field(
        ...,
        description="Canonical, deduplicated job URL"
    )
    description: str = Field(
        default="",
        description="Job description or snippet content"
    )
    posted_text: Optional[str] = Field(
        default=None,
        description="Original posted date or age text if present (e.g., '3 days ago')"
    )
    posted_at: Optional[str] = Field(
        default=None,
        description="ISO 8601 formatted posting timestamp if known"
    )
    posted_age_days: Optional[int] = Field(
        default=None,
        description="Normalized age in days since posting"
    )
    posting_date_confidence: str = Field(
        default="unknown",
        description="Confidence level of posting date: 'high', 'medium', 'low', 'unknown'"
    )
    availability_status: str = Field(
        default="UNKNOWN",
        description="Availability status: 'ACTIVE', 'CLOSED', 'EXPIRED', 'REMOVED', 'UNKNOWN'"
    )
    availability_checked_at: Optional[str] = Field(
        default=None,
        description="UTC timestamp when availability was verified"
    )
    search_query: str = Field(
        default="",
        description="Search query string that discovered this job"
    )
    discovered_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC timestamp when the job was discovered"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional auxiliary data (e.g. search engine score, raw engines)"
    )
