"""
Mission Generator Module.

This file is responsible for:
- Converting a validated CandidateProfile into an actionable SearchMission plan.
- Utilizing the local LLM to reason about keyword synonyms, role prioritization,
  and search strategy based on the candidate's skill set and experience.
- Enforcing structured output validation using Pydantic.
- Providing a deterministic fallback mechanism to ensure the system continues smoothly
  even if the local LLM is temporarily slow or unavailable.
"""

from typing import Optional
from config.settings import settings
from infrastructure.ollama import OllamaClient
from models.candidate import CandidateProfile
from models.mission import SearchMission
from utils.logger import get_logger

logger = get_logger("agent.mission_generator")


class MissionGenerator:
    """
    Generates a SearchMission from a CandidateProfile using local LLM reasoning or fallback rules.
    """

    def __init__(self, ollama_client: Optional[OllamaClient] = None) -> None:
        self.ollama = ollama_client or OllamaClient()

    def generate_mission(self, candidate: CandidateProfile) -> SearchMission:
        """
        Synthesizes a structured SearchMission from the candidate profile.
        """
        logger.info(f"Generating search mission for roles: {candidate.target_roles}")

        system_prompt = (
            "You are an expert technical recruiter and autonomous job search planner. "
            "Your task is to analyze a candidate profile and formulate a focused SearchMission. "
            "Create high-signal search roles, select key technical keywords that recruiters use in job postings, "
            "and establish realistic search parameters."
        )

        user_prompt = (
            f"Candidate Profile:\n"
            f"- Target Roles: {candidate.target_roles}\n"
            f"- Technical Skills: {candidate.skills}\n"
            f"- Years of Experience: {candidate.experience_years}\n"
            f"- Preferred Locations: {candidate.locations}\n"
            f"- Work Modes: {candidate.work_modes}\n"
            f"- Excluded Companies: {candidate.excluded_companies}\n"
            f"- Desired Job Count: {candidate.target_job_count}\n"
            f"- Max Posting Age Days: {candidate.max_posting_age_days}\n\n"
            "Generate a SearchMission JSON object that adheres strictly to the schema."
        )

        try:
            mission = self.ollama.generate_structured(
                prompt=user_prompt,
                schema=SearchMission,
                system=system_prompt,
                max_retries=2
            )
            # Enforce mission bounds matching candidate constraints
            mission.allowed_providers = candidate.job_providers or ["linkedin"]
            mission.minimum_target_jobs = candidate.target_job_count
            mission.excluded_companies = candidate.excluded_companies
            mission.posting_age_days = candidate.max_posting_age_days
            if not mission.locations and candidate.locations:
                mission.locations = candidate.locations
            logger.info(f"Mission generated successfully via LLM: objective='{mission.objective}' | max_age={mission.posting_age_days}d")
            return mission

        except Exception as e:
            logger.warning(f"LLM mission generation failed ({e}). Falling back to deterministic plan.")
            return self._generate_fallback_mission(candidate)

    def _generate_fallback_mission(self, candidate: CandidateProfile) -> SearchMission:
        """
        Creates a deterministic SearchMission directly from candidate attributes
        without invoking the LLM.
        """
        primary_role = candidate.target_roles[0]
        objective = f"Find {candidate.target_job_count} matching positions for {primary_role}"

        return SearchMission(
            objective=objective,
            allowed_providers=candidate.job_providers or ["linkedin"],
            search_roles=candidate.target_roles,
            keywords=candidate.skills[:6],
            locations=candidate.locations,
            work_modes=candidate.work_modes,
            posting_age_days=candidate.max_posting_age_days,
            excluded_companies=candidate.excluded_companies,
            evaluation_threshold=settings.default_evaluation_threshold,
            minimum_target_jobs=candidate.target_job_count,
            max_iterations=settings.default_max_iterations
        )
