"""
Models package for Autonomous Job Hunter.
Exposes data transfer objects and validation models.
"""

from .candidate import CandidateProfile
from .mission import SearchMission
from .job import Job
from .evaluation import JobEvaluation

__all__ = [
    "CandidateProfile",
    "SearchMission",
    "Job",
    "JobEvaluation",
]
