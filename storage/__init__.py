"""
Storage package for Autonomous Job Hunter.

This package exposes:
- AgentMemory: Persistent agent search memory and statistics.
- CandidateRepository: Abstraction interface for candidate profile retrieval.
- LocalCandidateRepository: Filesystem-backed candidate repository (data/candidates/).
- ApiCandidateRepository: Future REST API candidate repository stub.
- CandidateNotFoundError, CandidateDataError: Repository domain exceptions.
"""

from .memory import AgentMemory
from .candidate_repository import (
    CandidateRepository,
    LocalCandidateRepository,
    ApiCandidateRepository,
    CandidateNotFoundError,
    CandidateDataError,
)

__all__ = [
    "AgentMemory",
    "CandidateRepository",
    "LocalCandidateRepository",
    "ApiCandidateRepository",
    "CandidateNotFoundError",
    "CandidateDataError",
]
