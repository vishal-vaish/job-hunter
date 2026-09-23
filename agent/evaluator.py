"""
Job Semantic Evaluator Module.

This file is responsible for:
- Performing semantic matching between a candidate profile and a discovered job listing.
- Invoking the local LLM to assess fit, technical requirements, and experience relevance.
- Enforcing structured output validation using the JobEvaluation Pydantic model.
- Suppressing model hallucinations by requiring reasons grounded strictly in the listing.
- Providing a deterministic heuristic evaluation fallback to guarantee uninterrupted execution.
"""

from typing import Optional
from config.settings import settings
from infrastructure.ollama import OllamaClient
from models.candidate import CandidateProfile
from models.evaluation import JobEvaluation
from models.job import Job
from utils.logger import get_logger

logger = get_logger("agent.evaluator")


class JobEvaluator:
    """
    Evaluates job postings against candidate profiles using local LLM reasoning.
    """

    def __init__(self, ollama_client: Optional[OllamaClient] = None) -> None:
        self.ollama = ollama_client or OllamaClient()

    def evaluate(
        self,
        candidate: CandidateProfile,
        job: Job,
        threshold: int = 70
    ) -> JobEvaluation:
        """
        Assesses a job's suitability for a candidate.
        Returns a validated JobEvaluation object.
        """
        logger.info(f"Evaluating job '{job.title}' at '{job.company}' (Threshold: {threshold})")

        system_prompt = (
            "You are a precise technical hiring evaluator. Your job is to semantically evaluate "
            "how well a candidate's profile matches a job posting.\n"
            "Rules:\n"
            "1. Output a score between 0 and 100.\n"
            "2. Mark suitable as true ONLY if score is greater than or equal to the threshold.\n"
            "3. matched_skills must ONLY contain skills mentioned in both candidate profile and the job snippet.\n"
            "4. missing_skills should contain important skills needed by the job that the candidate lacks.\n"
            "5. Do NOT invent or assume qualifications not present in the provided text."
        )

        user_prompt = (
            f"EVALUATION THRESHOLD: {threshold}\n\n"
            f"CANDIDATE:\n"
            f"- Target Roles: {candidate.target_roles}\n"
            f"- Skills: {candidate.skills}\n"
            f"- Experience: {candidate.experience_years} years\n"
            f"- Preferred Locations: {candidate.locations}\n"
            f"- Work Modes: {candidate.work_modes}\n\n"
            f"JOB POSTING:\n"
            f"- Title: {job.title}\n"
            f"- Company: {job.company}\n"
            f"- Location: {job.location}\n"
            f"- Snippet/Description: {job.description}\n\n"
            "Evaluate this job against the candidate profile and return JSON conforming to the JobEvaluation schema."
        )

        try:
            evaluation = self.ollama.generate_structured(
                prompt=user_prompt,
                schema=JobEvaluation,
                system=system_prompt,
                max_retries=2
            )
            # Ensure suitable flag is consistent with the numerical threshold
            if evaluation.score >= threshold and not evaluation.suitable:
                evaluation.suitable = True
            elif evaluation.score < threshold and evaluation.suitable:
                evaluation.suitable = False

            logger.info(
                f"Evaluation result for '{job.title}': score={evaluation.score}, suitable={evaluation.suitable}"
            )
            return evaluation

        except Exception as e:
            logger.warning(
                f"LLM evaluation failed for '{job.title}' ({e}). Utilizing heuristic evaluation fallback."
            )
            return self._heuristic_evaluation(candidate, job, threshold)

    def _heuristic_evaluation(
        self,
        candidate: CandidateProfile,
        job: Job,
        threshold: int
    ) -> JobEvaluation:
        """
        Deterministic fallback evaluation based on keyword and role token overlap.
        """
        job_text = f"{job.title} {job.description}".lower()
        score = 50  # baseline neutral score

        # Check role match
        matched_roles = [r for r in candidate.target_roles if r.lower() in job_text]
        if matched_roles:
            score += 25

        # Check skills match
        matched_skills = [s for s in candidate.skills if s.lower() in job_text]
        missing_skills = [s for s in candidate.skills if s.lower() not in job_text]

        skill_bonus = min(25, len(matched_skills) * 8)
        score += skill_bonus

        # Check for negative experience indicators
        if candidate.experience_years <= 2 and ("senior" in job.title.lower() or "lead" in job.title.lower() or "principal" in job.title.lower()):
            score -= 30

        final_score = max(0, min(100, score))
        suitable = final_score >= threshold

        return JobEvaluation(
            score=final_score,
            suitable=suitable,
            reasons=[
                f"Heuristic match: matched {len(matched_skills)} skills and {len(matched_roles)} target roles."
            ],
            matched_skills=matched_skills,
            missing_skills=missing_skills[:3]
        )
