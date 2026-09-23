"""
Results Persistence Tool Module.

This file is responsible for:
- Saving finalized, accepted job listings and their semantic evaluations.
- Supporting the run-isolated output architecture:
  * Current output: sandbox/output/jobs.json (latest completed execution).
  * Historical output: sandbox/output/runs/<run_id>/jobs.json.
  * Run summary: sandbox/output/runs/<run_id>/summary.json.
  * Run metadata: sandbox/output/runs/<run_id>/run.json.
- Enforcing latest-first sorting (newest posting age first, secondary by evaluation score).
- Recording deterministic execution statistics and granular rejection reasons.
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
    Narrow tool allowing the Brain to persist run-isolated results to sandbox/output/.
    """

    def __init__(self, sandbox: Optional[Sandbox] = None) -> None:
        self.sandbox = sandbox or default_sandbox

    def format_accepted_jobs(
        self,
        accepted_jobs: List[Job],
        evaluations: Dict[str, JobEvaluation]
    ) -> List[Dict[str, Any]]:
        """
        Sorts jobs newest-first and serializes each job into a comprehensive dictionary.
        """
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

        return formatted_jobs

    def save_run_results(
        self,
        run_id: str,
        mission: SearchMission,
        accepted_jobs: List[Job],
        evaluations: Dict[str, JobEvaluation],
        customer_id: Optional[str] = None,
        search_prompt: Optional[str] = None
    ) -> Dict[str, Path]:
        """
        Persists accepted jobs to both the historical run directory:
          sandbox/output/runs/<run_id>/jobs.json
        and the latest current output:
          sandbox/output/jobs.json
        """
        formatted_jobs = self.format_accepted_jobs(accepted_jobs, evaluations)

        metadata: Dict[str, Any] = {
            "run_id": run_id,
            "customer_id": customer_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "objective": mission.objective,
            "target_roles": mission.search_roles,
            "threshold": mission.evaluation_threshold,
            "max_posting_age_days": mission.posting_age_days,
            "sorting": "newest_first (posted_age_days ASC, score DESC)",
            "total_accepted_jobs": len(formatted_jobs)
        }
        if search_prompt:
            metadata["search_prompt"] = search_prompt

        output_payload: Dict[str, Any] = {
            "metadata": metadata,
            "jobs": formatted_jobs
        }

        # 1. Historical run output: sandbox/output/runs/<run_id>/jobs.json
        historical_rel = f"runs/{run_id}/jobs.json"
        historical_path = self.sandbox.write_json("output", historical_rel, output_payload, indent=2)

        # 2. Latest current output: sandbox/output/jobs.json
        current_path = self.sandbox.write_json("output", "jobs.json", output_payload, indent=2)

        logger.info(f"[TOOL:results] Saved historical jobs to {historical_path} and current jobs to {current_path}")
        return {"historical": historical_path, "current": current_path}

    def save_run_summary(
        self,
        run_id: str,
        statistics: Dict[str, Any],
        rejections: List[Dict[str, Any]],
        customer_id: Optional[str] = None,
        search_prompt: Optional[str] = None
    ) -> Path:
        """
        Persists deterministic execution statistics and granular rejection reasons to:
          sandbox/output/runs/<run_id>/summary.json
        """
        summary_payload: Dict[str, Any] = {
            "run_id": run_id,
            "customer_id": customer_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "statistics": statistics,
            "rejections": rejections
        }
        if search_prompt:
            summary_payload["search_prompt"] = search_prompt

        rel_path = f"runs/{run_id}/summary.json"
        saved_path = self.sandbox.write_json("output", rel_path, summary_payload, indent=2)
        logger.info(f"[TOOL:results] Saved run summary to {saved_path}")
        return saved_path


    def save_run_record(
        self,
        run_id: str,
        run_record: Dict[str, Any]
    ) -> Path:
        """
        Persists structured run metadata (status, timestamps, candidate parameters) to:
          sandbox/output/runs/<run_id>/run.json
        """
        rel_path = f"runs/{run_id}/run.json"
        saved_path = self.sandbox.write_json("output", rel_path, run_record, indent=2)
        logger.info(f"[TOOL:results] Saved run metadata to {saved_path}")
        return saved_path

    def save_results(
        self,
        mission: SearchMission,
        accepted_jobs: List[Job],
        evaluations: Dict[str, JobEvaluation],
        filename: str = "jobs.json",
        run_id: Optional[str] = None
    ) -> Path:
        """
        Backwards-compatible convenience method.
        """
        if run_id:
            res = self.save_run_results(run_id, mission, accepted_jobs, evaluations)
            return res["current"]

        formatted_jobs = self.format_accepted_jobs(accepted_jobs, evaluations)
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
        return self.sandbox.write_json("output", filename, output_payload, indent=2)
