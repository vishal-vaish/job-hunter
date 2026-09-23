"""
Candidate Profile Validator Module.

This file is responsible for:
- Validating candidate profiles deterministically against schemas and business constraints.
- Ensuring essential search criteria (target roles, experience, skills) are properly populated.
- Providing structured transformation from raw candidate dictionary or JSON files
  into validated CandidateProfile instances.
- Flagging inconsistencies before the Autonomous Brain begins execution.
"""

from typing import Any, Dict, List, Optional
from models.candidate import CandidateProfile
from utils.logger import get_logger

logger = get_logger("agent.profile_validator")


class ProfileValidationError(ValueError):
    """Raised when candidate profile data violates core schema or business rules."""
    pass


class ProfileValidator:
    """
    Validates and normalizes candidate profile input data.
    """

    @classmethod
    def validate_profile(cls, profile: CandidateProfile) -> CandidateProfile:
        """
        Performs semantic and business rule validation on a CandidateProfile.
        """
        # Ensure at least one target role is specified
        clean_roles = [r.strip() for r in profile.target_roles if r.strip()]
        if not clean_roles:
            raise ProfileValidationError("Candidate profile must specify at least one target role.")
        profile.target_roles = clean_roles

        # Ensure experience is non-negative
        if profile.experience_years < 0:
            raise ProfileValidationError("Experience years cannot be negative.")

        # Clean skills
        profile.skills = [s.strip() for s in profile.skills if s.strip()]

        # Clean locations
        profile.locations = [loc.strip() for loc in profile.locations if loc.strip()]

        # Ensure target job count is at least 1
        if profile.target_job_count <= 0:
            profile.target_job_count = 10

        # Ensure max posting age is reasonable
        if profile.max_posting_age_days <= 0:
            profile.max_posting_age_days = 30

        logger.info(
            f"Candidate profile validated successfully: roles={profile.target_roles}, "
            f"experience={profile.experience_years}y, skills={len(profile.skills)}"
        )
        return profile

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CandidateProfile:
        """
        Instantiates and validates a CandidateProfile from a dictionary.
        """
        try:
            profile = CandidateProfile(**data)
            return cls.validate_profile(profile)
        except Exception as e:
            logger.error(f"Candidate profile validation error: {e}")
            raise ProfileValidationError(f"Invalid candidate profile: {e}") from e
