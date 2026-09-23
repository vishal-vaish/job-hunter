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

    @classmethod
    def from_prompt(cls, prompt: str, ollama_client: Optional[Any] = None) -> CandidateProfile:
        """
        Synthesizes a CandidateProfile directly from a natural-language search prompt.
        Uses Ollama structured generation if available, with deterministic fallback.
        """
        clean_prompt = prompt.strip()
        if not clean_prompt:
            raise ProfileValidationError("Search prompt cannot be empty.")

        # Ensure prompt is job-related
        details = cls.inspect_prompt_details(clean_prompt)
        if not details.get("is_job_related", True):
            reason = details.get("reason", "Query does not appear to be a job search request.")
            raise ProfileValidationError(f"Invalid search prompt: {reason}")

        # Attempt LLM synthesis if ollama_client provided
        if ollama_client:
            try:
                system_prompt = (
                    "You are an expert technical recruiter. Analyze the user's job search prompt "
                    "and extract a structured CandidateProfile JSON object. "
                    "Extract target roles, skills, locations, work modes, and maximum posting age if specified."
                )
                user_msg = f"Search Prompt: \"{clean_prompt}\"\nGenerate a CandidateProfile matching this request."
                profile = ollama_client.generate_structured(
                    prompt=user_msg,
                    schema=CandidateProfile,
                    system=system_prompt,
                    max_retries=1
                )
                profile.customer_id = "prompt_user"
                return cls.validate_profile(profile)
            except Exception as e:
                logger.warning(f"LLM candidate synthesis from prompt failed ({e}). Using deterministic extractor.")

        # Deterministic extraction fallback
        import re
        lower = clean_prompt.lower()

        # Extract posting age constraint e.g. "last 7 days", "within 14 days"
        max_age = 30
        age_match = re.search(r'(?:last|within|past)\s+(\d+)\s*(?:days?|d)', lower)
        if age_match:
            try:
                max_age = int(age_match.group(1))
            except ValueError:
                pass

        # Extract work modes
        modes = []
        if "remote" in lower:
            modes.append("remote")
        if "hybrid" in lower:
            modes.append("hybrid")
        if "onsite" in lower or "on-site" in lower:
            modes.append("onsite")
        if not modes:
            modes = ["remote", "hybrid", "onsite"]

        # Extract locations
        common_locations = ["bangalore", "bengaluru", "delhi", "noida", "gurgaon", "gurugram",
                            "mumbai", "hyderabad", "pune", "chennai", "remote", "new york", "san francisco"]
        found_locations = [loc.capitalize() for loc in common_locations if loc in lower]

        # Extract target roles / title
        # Strip common prompt stop phrases
        roles = []
        cleaned_for_role = re.sub(
            r'\b(find|search|looking for|jobs?|positions?|roles?|in|at|preferably|posted|within|last|\d+\s*days?)\b',
            ' ',
            lower
        )
        tokens = [t.strip().capitalize() for t in cleaned_for_role.split() if len(t.strip()) > 2]
        if tokens:
            roles.append(" ".join(tokens[:3]))
        if not roles:
            roles = [clean_prompt[:50]]

        fallback_profile = CandidateProfile(
            customer_id="prompt_user",
            target_roles=roles,
            skills=tokens[:5],
            experience_years=3,
            locations=found_locations or ["Remote"],
            work_modes=modes,
            max_posting_age_days=max_age,
            target_job_count=5
        )
        return cls.validate_profile(fallback_profile)

    @classmethod
    def inspect_prompt_details(cls, prompt: str) -> Dict[str, Any]:
        """
        Analyzes a natural-language search prompt to see if:
        1. It is actually a job search request (and not an off-topic question/greeting).
        2. Key parameters such as location, role, or posting age are present.
        Returns detected parameters, validity flag, and a list of missing fields.
        """
        import re
        clean_prompt = prompt.strip()
        lower = clean_prompt.lower()

        # 1. Check for off-topic / non-job patterns
        off_topic_patterns = [
            r'\bweather\b', r'\bforecast\b', r'\btemperature\b', r'\brain(?:ing)?\b',
            r'\bclimate\b', r'\brecipe\b', r'\bjoke\b', r'\bsong\b', r'\bmovie\b',
            r'\bgame\b', r'\bhow are you\b', r'\bwho are you\b', r'\bwhat is the capital\b',
            r'\bnews\b', r'\bsports\b', r'\bscore\b', r'\bstock price\b', r'\bhow to cook\b'
        ]
        is_clearly_off_topic = any(re.search(pat, lower) for pat in off_topic_patterns)

        # 2. Check for job-related keywords (roles, skills, employment terms)
        job_indicators = [
            # Job titles & suffixes
            "developer", "engineer", "architect", "programmer", "coder", "analyst",
            "scientist", "designer", "consultant", "administrator", "manager", "lead",
            "intern", "internship", "devops", "sre", "qa", "tester", "fullstack",
            "full-stack", "backend", "frontend", "specialist", "officer", "director",
            "executive", "associate", "technician", "trainee", "recruiter",
            # Generic employment words
            "job", "jobs", "hiring", "hire", "position", "positions", "role", "roles",
            "vacancy", "vacancies", "opening", "openings", "career", "careers",
            "work", "employment", "contract", "freelance",
            # Common technical & professional skills / stacks
            "python", "java", "javascript", "typescript", "react", "angular", "vue",
            "node", "django", "fastapi", "flask", "spring", "docker", "kubernetes",
            "aws", "azure", "gcp", "sql", "postgres", "mysql", "mongodb", "redis",
            "rust", "golang", "go", "c++", "c#", ".net", "php", "ruby", "rails",
            "swift", "kotlin", "flutter", "data", "ml", "ai", "machine learning",
            "cloud", "cybersecurity", "security", "linux", "sales", "marketing", "accounting"
        ]
        has_job_indicator = any(re.search(rf'\b{re.escape(ind)}\b', lower) for ind in job_indicators)

        # Determine if query is job-related
        if is_clearly_off_topic and not has_job_indicator:
            return {
                "is_job_related": False,
                "reason": "Query appears to be a general inquiry or off-topic question, not a job search request",
                "locations": [],
                "roles": [],
                "missing": []
            }

        if not has_job_indicator:
            return {
                "is_job_related": False,
                "reason": "No job title, technical skill, or career keyword was recognized",
                "locations": [],
                "roles": [],
                "missing": []
            }

        # 3. Location detection
        common_locations = [
            "bangalore", "bengaluru", "delhi", "noida", "gurgaon", "gurugram",
            "mumbai", "hyderabad", "pune", "chennai", "kolkata", "remote",
            "new york", "san francisco", "london", "singapore", "berlin",
            "canada", "india", "us", "usa", "uk"
        ]
        found_locations = [loc.capitalize() for loc in common_locations if loc in lower]

        # Check for phrases like "in <Location>" or "at <Location>"
        in_matches = re.findall(r'\b(?:in|at)\s+([a-zA-Z]+)', lower)
        for m in in_matches:
            if m not in ["the", "a", "an", "last", "past", "next", "remote", "hybrid", "terms", "days", "weeks", "months"]:
                cap = m.capitalize()
                if cap not in found_locations:
                    found_locations.append(cap)

        # 4. Roles / tokens
        cleaned_for_role = re.sub(
            r'\b(find|search|looking for|jobs?|positions?|roles?|in|at|preferably|posted|within|last|\d+\s*days?)\b',
            ' ',
            lower
        )
        tokens = [t.strip().capitalize() for t in cleaned_for_role.split() if len(t.strip()) > 2]

        missing = []
        if not found_locations:
            missing.append("location")
        if not tokens:
            missing.append("role")

        return {
            "is_job_related": True,
            "reason": None,
            "locations": found_locations,
            "roles": tokens,
            "missing": missing
        }


