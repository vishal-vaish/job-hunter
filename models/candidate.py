"""
Candidate Profile Data Model.

This file is responsible for:
- Defining the structured representation of a job seeker's profile.
- Validating candidate constraints (target roles, technical skills, experience years,
  preferred locations, work modes, excluded companies, and desired job count).
- Providing deterministic validation using Pydantic.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class CandidateProfile(BaseModel):
    """
    Internal structured candidate profile holding career goals and preferences.
    """
    target_roles: List[str] = Field(
        ...,
        description="Target job titles or role keywords, e.g. ['Java Developer', 'Backend Engineer']",
        min_length=1
    )
    skills: List[str] = Field(
        default_factory=list,
        description="Core technical and functional skills, e.g. ['Java', 'Spring Boot', 'PostgreSQL']"
    )
    experience_years: int = Field(
        default=0,
        ge=0,
        description="Years of relevant professional experience"
    )
    locations: List[str] = Field(
        default_factory=list,
        description="Preferred geographic locations or cities, e.g. ['Delhi', 'Noida', 'Gurgaon']"
    )
    work_modes: List[str] = Field(
        default_factory=lambda: ["remote", "hybrid", "onsite"],
        description="Acceptable work arrangements, e.g. ['remote', 'hybrid', 'onsite']"
    )
    job_providers: List[str] = Field(
        default_factory=lambda: ["linkedin"],
        description="Enabled job search providers, e.g. ['linkedin']"
    )
    max_posting_age_days: int = Field(
        default=30,
        gt=0,
        description="Maximum age of job postings in days"
    )
    excluded_companies: List[str] = Field(
        default_factory=list,
        description="Companies to exclude from search results and hard filters"
    )
    target_job_count: int = Field(
        default=10,
        gt=0,
        description="Target number of suitable jobs to accept before stopping"
    )

    @field_validator("work_modes")
    @classmethod
    def normalize_work_modes(cls, modes: List[str]) -> List[str]:
        """Normalize work modes to lowercase clean strings."""
        return [m.strip().lower() for m in modes if m.strip()]

    @field_validator("job_providers")
    @classmethod
    def normalize_providers(cls, providers: List[str]) -> List[str]:
        """Normalize provider names to lowercase clean strings."""
        return [p.strip().lower() for p in providers if p.strip()]
