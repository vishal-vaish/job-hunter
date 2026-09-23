"""
Candidate Repository Module.

This file is responsible for:
- Defining the CandidateRepository abstraction interface (ABC) for loading candidate profiles.
- Providing LocalCandidateRepository for loading candidate profiles from data/candidates/<customer_id>.json.
- Providing ApiCandidateRepository as a future REST API candidate source integration point.
- Defining custom exceptions: CandidateNotFoundError and CandidateDataError.
- Enforcing that candidate source data lives outside the sandbox execution directory.
- Ensuring the Autonomous Brain and CLI depend only on the CandidateRepository interface.
"""

from abc import ABC, abstractmethod
import json
from pathlib import Path
from typing import Any, Dict, Optional

from models.candidate import CandidateProfile
from agent.profile_validator import ProfileValidator, ProfileValidationError
from utils.logger import get_logger

logger = get_logger("storage.candidate_repository")


class CandidateNotFoundError(Exception):
    """Raised when a candidate cannot be located by customer_id."""
    pass


class CandidateDataError(Exception):
    """Raised when candidate data exists but fails parsing or schema validation."""
    pass


class CandidateRepository(ABC):
    """
    Abstract interface for retrieving candidate profiles.
    Allows transparent switching between local file storage and future REST APIs.
    """

    @abstractmethod
    def get_candidate(self, customer_id: str) -> CandidateProfile:
        """
        Fetch and return a validated CandidateProfile by customer_id.

        Args:
            customer_id: The external unique customer identity (e.g. '12345').

        Returns:
            Validated CandidateProfile instance.

        Raises:
            CandidateNotFoundError: If the customer profile cannot be found.
            CandidateDataError: If the profile data is invalid or corrupt.
        """
        pass


class LocalCandidateRepository(CandidateRepository):
    """
    Local filesystem implementation of CandidateRepository.
    Loads candidate data from data/candidates/<customer_id>.json.
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        if data_dir is not None:
            self.data_dir = Path(data_dir).resolve()
        else:
            # Default to project_root / data / candidates
            project_root = Path(__file__).resolve().parent.parent
            self.data_dir = (project_root / "data" / "candidates").resolve()

        # Ensure candidates directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def get_candidate(self, customer_id: str) -> CandidateProfile:
        """
        Loads and validates a candidate profile from data/candidates/<customer_id>.json.
        """
        clean_id = str(customer_id).strip()
        if not clean_id:
            raise CandidateNotFoundError("Candidate ID cannot be empty.")

        # Prevent basic directory traversal in ID
        if ".." in clean_id or "/" in clean_id or "\\" in clean_id:
            raise CandidateNotFoundError(f"Invalid candidate ID: {clean_id}")

        candidate_file = self.data_dir / f"{clean_id}.json"

        if not candidate_file.exists() or not candidate_file.is_file():
            logger.warning(f"Candidate file not found: {candidate_file}")
            raise CandidateNotFoundError(f"Candidate not found: {clean_id}")

        # 1. Read JSON file
        try:
            content = candidate_file.read_text(encoding="utf-8")
            raw_data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON for customer '{clean_id}': {e}")
            raise CandidateDataError(f"Malformed JSON in candidate data for '{clean_id}': {e}") from e
        except Exception as e:
            logger.error(f"Error reading candidate file {candidate_file}: {e}")
            raise CandidateDataError(f"Error reading candidate data for '{clean_id}': {e}") from e

        # 2. Validate with ProfileValidator
        try:
            profile = ProfileValidator.from_dict(raw_data)
        except ProfileValidationError as e:
            logger.error(f"Candidate profile schema validation failed for '{clean_id}': {e}")
            raise CandidateDataError(f"Candidate validation failed for '{clean_id}': {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error validating candidate '{clean_id}': {e}")
            raise CandidateDataError(f"Unexpected validation error for '{clean_id}': {e}") from e

        # 3. Associate customer_id
        profile.customer_id = clean_id
        logger.info(f"Loaded candidate profile for customer_id '{clean_id}' from {candidate_file}")
        return profile


class ApiCandidateRepository(CandidateRepository):
    """
    Future REST API candidate repository.
    Enables retrieving candidate profiles from a remote customer service.
    """

    def __init__(self, base_url: str = "http://localhost:8000/api", api_key: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def get_candidate(self, customer_id: str) -> CandidateProfile:
        """
        Retrieves candidate profile via REST API (stub for future integration).
        """
        raise NotImplementedError(
            f"ApiCandidateRepository is not yet implemented. Future REST API integration point for customer '{customer_id}'."
        )
