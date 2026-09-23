"""
Search Mission Data Model.

This file is responsible for:
- Defining the structured search plan derived from a CandidateProfile.
- Specifying search objectives, enabled providers, roles, targeted keywords,
  location criteria, age constraints, company exclusions, quality thresholds,
  target quotas, and maximum search iterations.
- Serving as the operational blueprint for the Autonomous Brain.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class SearchMission(BaseModel):
    """
    Search Mission model defining the plan that the Autonomous Brain executes and adapts.
    """
    objective: str = Field(
        ...,
        description="High-level mission objective statement"
    )
    allowed_providers: List[str] = Field(
        default_factory=lambda: ["linkedin"],
        description="List of providers enabled for this mission"
    )
    search_roles: List[str] = Field(
        ...,
        description="Prioritized list of roles to search for"
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="Keywords representing skills, stacks, or domains"
    )
    locations: List[str] = Field(
        default_factory=list,
        description="Locations to target in query formulations"
    )
    work_modes: List[str] = Field(
        default_factory=lambda: ["remote", "hybrid"],
        description="Acceptable work modes"
    )
    posting_age_days: int = Field(
        default=30,
        description="Maximum posting age in days"
    )
    excluded_companies: List[str] = Field(
        default_factory=list,
        description="Companies excluded from matches"
    )
    evaluation_threshold: int = Field(
        default=70,
        ge=0,
        le=100,
        description="Minimum semantic score (0-100) required to accept a job"
    )
    minimum_target_jobs: int = Field(
        default=10,
        gt=0,
        description="Desired quota of accepted jobs"
    )
    max_iterations: int = Field(
        default=5,
        gt=0,
        description="Maximum feedback-loop iterations allowed before stopping"
    )
