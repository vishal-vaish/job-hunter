"""
Job Evaluation Model Module.

This file is responsible for:
- Defining the structured output produced when the local LLM evaluates a job
  against the candidate's profile.
- Capturing semantic score (0-100), suitability boolean flag, reasons,
  matched skills, and missing skills.
- Guaranteeing strict JSON schema adherence via Pydantic.
"""

from typing import List
from pydantic import BaseModel, Field


class JobEvaluation(BaseModel):
    """
    Semantic evaluation result for a job against a candidate profile.
    """
    score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Fit score from 0 to 100 assessing relevance to candidate profile"
    )
    suitable: bool = Field(
        ...,
        description="True if the job matches the candidate profile threshold and criteria"
    )
    reasons: List[str] = Field(
        default_factory=list,
        description="List of concise justifications for the score and suitability decision"
    )
    matched_skills: List[str] = Field(
        default_factory=list,
        description="Skills from the candidate profile matched in the job posting"
    )
    missing_skills: List[str] = Field(
        default_factory=list,
        description="Desired candidate skills not observed or required qualifications missing"
    )
