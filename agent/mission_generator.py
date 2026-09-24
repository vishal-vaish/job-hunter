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

    def generate_mission(
        self,
        candidate: CandidateProfile,
        search_prompt: Optional[str] = None
    ) -> SearchMission:
        """
        Synthesizes a structured SearchMission from the candidate profile and optional run-specific search prompt.
        """
        logger.info(f"Generating search mission for roles: {candidate.target_roles}")
        if search_prompt:
            logger.info(f"Incorporating run search prompt: '{search_prompt}'")

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
            f"- Max Posting Age Days: {candidate.max_posting_age_days}\n"
        )

        if search_prompt:
            user_prompt += (
                f"""
                Specific Search Request for this Run:
                
                "{search_prompt}"
                
                IMPORTANT SEARCH CONSTRAINTS:
                
                The search request above contains explicit user requirements.
                
                Treat the following as HARD constraints:
                
                - Requested job roles must be preserved.
                - Requested locations must be preserved.
                - Requested work modes must be preserved.
                - Requested posting-age limit must be preserved.
                - Do not replace a requested role with an unrelated role.
                - Do not add new locations that were not requested.
                - Do not remove one of the requested roles merely because another role appears more common.
                - Technical skills may be used to improve search precision, but they must not override the user's requested role/location/work-mode constraints.
                - The posting-age limit must never be relaxed.
                
                The SearchMission should represent the user's actual request,
                not merely the candidate profile.
                """
            )

        user_prompt += "\nGenerate a SearchMission JSON object that adheres strictly to the schema."

        try:
            mission = self.ollama.generate_structured(
                prompt=user_prompt,
                schema=SearchMission,
                system=system_prompt,
                max_retries=2
            )

            # Never allow the LLM to reduce autonomous search to a
            # single iteration unless the application explicitly
            # configures that behavior.
            configured_max_iterations = settings.default_max_iterations

            if configured_max_iterations < 2:
                configured_max_iterations = 5

            mission.max_iterations = max(
                2,
                min(
                    mission.max_iterations,
                    configured_max_iterations,
                )
            )

            logger.info(
                f"Mission iteration budget normalized: "
                f"max_iterations={mission.max_iterations}"
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
            return self._generate_fallback_mission(candidate, search_prompt=search_prompt)

    def _generate_fallback_mission(
        self,
        candidate: CandidateProfile,
        search_prompt: Optional[str] = None
    ) -> SearchMission:
        """
        Creates a deterministic SearchMission directly from candidate attributes
        without invoking the LLM.
        """
        primary_role = candidate.target_roles[0]
        if search_prompt:
            objective = f"{search_prompt} (Target: {primary_role})"
        else:
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
