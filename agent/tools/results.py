"""
Results Persistence Tool Module.

This file is responsible for:
- Saving finalized, accepted job listings and their semantic evaluations.
- Writing output strictly to sandbox/output/jobs.json via the Sandbox abstraction.
- Generating a rich, well-structured output document containing metadata, fit scores,
  matched skills, freshness metrics (posted_at, posted_age_days), availability status,
  and direct URLs for the candidate.
- Enforcing latest-first sorting (newest posting age first, secondary by evaluation score).
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from models.evaluation import JobEvaluation
from models.job import Job
from models.mission import SearchMission
from security.sandbox import Sandbox, default_sandbox
from utils.logger import get_logger

logger = get_logger("agent.tools.results")


class ResultsTool:
    """
    Narrow tool allowing the Brain to persist final accepted jobs to sandbox/output/.
    """

    def __init__(self, sandbox: Optional[Sandbox] = None) -> None:
        self.sandbox = sandbox or default_sandbox

    def save_results(
        self,
        mission: SearchMission,
        accepted_jobs: List[Job],
        evaluations: Dict[str, JobEvaluation],
        filename: str = "jobs.json"
    ) -> Path:
        """
        Saves accepted jobs along with evaluation details to sandbox/output/jobs.json.
        Enforces latest-first sorting (posted_age_days ASC, secondary evaluation.score DESC).
        """
        logger.info(f"[TOOL:results] Persisting {len(accepted_jobs)} accepted jobs to output/{filename}")

        # Deterministic sorting: Newest first (lowest posted_age_days), secondary highest score
        sorted_jobs = sorted(
            accepted_jobs,
            key=lambda j: (
                j.posted_age_days if j.posted_age_days is not None else 999999,
                -(evaluations[j.url].score if j.url in evaluations and evaluations[j.url] else 0)
            )
        )

        formatted_jobs: List[Dict[str, Any]] = []

        for job in sorted_jobs:
            eval_info = evaluations.get(job.url)
            item: Dict[str, Any] = {
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "url": job.url,
                "provider": job.provider,
                "posted_text": job.posted_text,
                "posted_at": job.posted_at,
                "posted_age_days": job.posted_age_days,
                "posting_date_confidence": job.posting_date_confidence,
                "availability_status": job.availability_status,
                "availability_checked_at": job.availability_checked_at,
                "discovered_via_query": job.search_query,
                "evaluation": {
                    "score": eval_info.score if eval_info else None,
                    "suitable": eval_info.suitable if eval_info else True,
                    "reasons": eval_info.reasons if eval_info else [],
                    "matched_skills": eval_info.matched_skills if eval_info else [],
                    "missing_skills": eval_info.missing_skills if eval_info else []
                },
                "snippet": job.description
            }
            formatted_jobs.append(item)

        output_payload: Dict[str, Any] = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "objective": mission.objective,
                "target_roles": mission.search_roles,
                "threshold": mission.evaluation_threshold,
                "max_posting_age_days": mission.posting_age_days,
                "sorting": "newest_first (posted_age_days ASC, score DESC)",
                "total_accepted_jobs": len(formatted_jobs)
            },
            "jobs": formatted_jobs
        }

        saved_path = self.sandbox.write_json("output", filename, output_payload, indent=2)
        logger.info(f"[TOOL:results] Successfully saved {len(formatted_jobs)} sorted jobs to {saved_path}")
        return saved_path
