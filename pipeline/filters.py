"""
Deterministic Hard Filters Module.

This file is responsible for:
- Enforcing deterministic filtering rules without burdening the LLM:
  * Allowed providers enforcement.
  * Posting age / freshness constraint (max_posting_age_days, rejecting unknown age).
  * Availability verification constraint (requiring ACTIVE status, rejecting CLOSED/EXPIRED/REMOVED/UNKNOWN).
  * Excluded companies check.
  * Geographic location constraints.
  * Work mode compatibility (remote vs on-site).
- Providing clear internal reasons whenever a job listing is rejected.
- Keeping deterministic screening in Python for high speed, reliability, and auditability.
"""

import re
from typing import List, Optional, Tuple

from models.job import Job
from models.mission import SearchMission
from utils.logger import get_logger

logger = get_logger("pipeline.filters")


class HardFilterEngine:
    """
    Deterministic rule engine that validates jobs against mission constraints.
    """

    @staticmethod
    def is_company_excluded(company_name: str, excluded_companies: List[str]) -> bool:
        """
        Checks if the hiring company matches any name on the exclusion list.
        """
        if not company_name or company_name.lower() == "unknown":
            return False

        clean_company = company_name.strip().lower()
        for excluded in excluded_companies:
            clean_ex = excluded.strip().lower()
            if clean_ex and (clean_ex == clean_company or clean_ex in clean_company):
                return True
        return False

    @staticmethod
    def matches_location(job: Job, target_locations: List[str], allowed_work_modes: List[str]) -> bool:
        """
        Evaluates whether the job matches the candidate's preferred locations or remote mode.
        """
        # If no specific locations were requested, all locations pass
        if not target_locations:
            return True

        combined_text = f"{job.location} {job.title} {job.description}".lower()

        # If remote is an acceptable work mode, check for remote markers
        is_remote_allowed = any(m.lower() in {"remote", "hybrid", "any"} for m in allowed_work_modes)
        if is_remote_allowed:
            remote_keywords = ["remote", "work from home", "wfh", "telecommute", "anywhere"]
            if any(kw in combined_text for kw in remote_keywords):
                return True

        # Check if any requested location appears in the location or content
        for loc in target_locations:
            clean_loc = loc.strip().lower()
            if clean_loc and clean_loc in combined_text:
                return True

        # If the job location is unknown and cannot be verified, we do not reject it outright
        # to prevent false negatives from sparse search snippets
        if job.location.lower() == "unknown":
            return True

        return False

    @staticmethod
    def matches_work_mode(job: Job, allowed_work_modes: List[str]) -> bool:
        """
        Checks if the job's work arrangement conflicts with candidate requirements.
        For example, if candidate only allows 'remote', reject postings that strictly require 'on-site only'.
        """
        modes_lower = {m.lower() for m in allowed_work_modes}
        combined_text = f"{job.location} {job.title} {job.description}".lower()

        # Case 1: Candidate demands strictly remote work
        if modes_lower == {"remote"}:
            if "on-site only" in combined_text or "no remote" in combined_text or "in-office only" in combined_text:
                return False

        return True

    @staticmethod
    def matches_posting_age(job: Job, max_age_days: int) -> Tuple[bool, Optional[str]]:
        """
        Enforces posting age constraint:
        - If posting age is unknown, reject by default to avoid stale search engine results.
        - If posting age exceeds max_age_days, reject.
        """
        if job.posted_age_days is None:
            return False, "Unknown posting age (rejected by default)"

        if job.posted_age_days > max_age_days:
            return False, f"Posting age ({job.posted_age_days}d) exceeds maximum allowed ({max_age_days}d)"

        return True, None

    @staticmethod
    def is_available(job: Job) -> Tuple[bool, Optional[str]]:
        """
        Enforces availability constraint:
        - Must have status 'ACTIVE'.
        - 'CLOSED', 'EXPIRED', 'REMOVED', or 'UNKNOWN' are rejected.
        """
        if job.availability_status != "ACTIVE":
            return False, f"Job availability is '{job.availability_status}', required 'ACTIVE'"

        return True, None

    @classmethod
    def evaluate(cls, job: Job, mission: SearchMission) -> Tuple[bool, Optional[str]]:
        """
        Applies all deterministic hard filters to a single job listing.
        Returns (True, None) if accepted, or (False, "Reason for rejection") if rejected.
        """
        # 1. Provider restriction
        if mission.allowed_providers:
            allowed_p = [p.lower() for p in mission.allowed_providers]
            if job.provider.lower() not in allowed_p:
                return False, f"Provider '{job.provider}' not in allowed providers {allowed_p}"

        # 2. Posting age / freshness filter
        age_ok, age_reason = cls.matches_posting_age(job, mission.posting_age_days)
        if not age_ok:
            return False, age_reason

        # 3. Availability verification filter
        avail_ok, avail_reason = cls.is_available(job)
        if not avail_ok:
            return False, avail_reason

        # 4. Excluded companies
        if cls.is_company_excluded(job.company, mission.excluded_companies):
            return False, f"Company '{job.company}' is in candidate excluded list"

        # 5. Location criteria
        if not cls.matches_location(job, mission.locations, mission.work_modes):
            return False, f"Location '{job.location}' does not match target locations {mission.locations}"

        # 6. Work mode criteria
        if not cls.matches_work_mode(job, mission.work_modes):
            return False, f"Job arrangement conflicts with candidate work modes {mission.work_modes}"

        return True, None

    @classmethod
    def filter_batch(
        cls,
        jobs: List[Job],
        mission: SearchMission
    ) -> Tuple[List[Job], List[Tuple[Job, str]]]:
        """
        Applies deterministic hard filters across a list of jobs.
        Returns:
            (passed_jobs, rejected_jobs_with_reasons)
        """
        passed: List[Job] = []
        rejected: List[Tuple[Job, str]] = []

        for job in jobs:
            is_valid, reason = cls.evaluate(job, mission)
            if is_valid:
                passed.append(job)
            else:
                logger.info(f"Hard filter rejected job '{job.title}' ({job.url}): {reason}")
                rejected.append((job, reason or "Failed hard filter"))

        logger.info(f"Hard filters: {len(passed)} jobs passed, {len(rejected)} rejected.")
        return passed, rejected
