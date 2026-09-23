"""
Autonomous Job Hunter - Main CLI Entrypoint.

This file is responsible for:
- Providing the primary application entrypoint with 3 clean execution modes:
  1. Interactive Mode (`python main.py`):
     Prompts for Customer ID and optional Search Prompt, executes one run, and finishes cleanly.
     (No persistent REPL or command shell).
  2. Customer ID Mode (`python main.py --customer-id=12345`):
     Retrieves candidate via CandidateRepository abstraction and runs search.
  3. Direct Prompt Mode (`python main.py --prompt="..."`):
     Synthesizes candidate profile from search prompt and executes run.
- Enforcing candidate source data isolation:
  Candidate data is loaded strictly via CandidateRepository (data/candidates/),
  while sandbox/ is used solely for execution outputs, logs, and memory.
- Enforcing mutual exclusivity and strict argument validation.
- Handling missing or invalid customers cleanly with exit code 1 and no stack traces.
- Orchestrating the end-to-end run lifecycle:
  Unique run_id -> per-run log -> isolated run directory -> Brain loop -> dual outputs.
- Recording external customer_id, execution run_id, and search_prompt across metadata.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Optional

from agent.brain import AutonomousBrain
from agent.mission_generator import MissionGenerator
from agent.profile_validator import ProfileValidator, ProfileValidationError
from agent.tools.results import ResultsTool
from config.settings import settings
from infrastructure.ollama import OllamaClient
from infrastructure.searxng import SearXNGClient
from models.candidate import CandidateProfile
from storage.candidate_repository import (
    CandidateRepository,
    LocalCandidateRepository,
    CandidateNotFoundError,
    CandidateDataError,
)
from utils.logger import setup_logger, get_logger, generate_run_id, close_run_logger


def check_prerequisites(ollama: OllamaClient, searxng: SearXNGClient, logger) -> bool:
    """
    Checks that local Ollama and SearXNG instances are reachable.
    Logs clear actionable warnings if either service is offline.
    """
    logger.info("Verifying local infrastructure status...")

    ollama_ok = ollama.check_health()
    searxng_ok = searxng.check_health()

    if ollama_ok:
        logger.info(f"Ollama is reachable at {ollama.base_url} (Model: {ollama.model})")
    else:
        logger.warning(
            f"Ollama is not reachable at {ollama.base_url}. "
            "Please ensure Ollama is running (`ollama serve`). "
            "System will attempt heuristic fallback if needed."
        )

    if searxng_ok:
        logger.info(f"SearXNG is reachable at {searxng.base_url}")
    else:
        logger.warning(
            f"SearXNG is not reachable at {searxng.base_url}. "
            "Please ensure SearXNG is running on port 8081."
        )

    return ollama_ok and searxng_ok


def run_pipeline(
    candidate: CandidateProfile,
    customer_id: str,
    search_prompt: Optional[str] = None,
    custom_run_id: Optional[str] = None
) -> None:
    """
    Runs the complete autonomous job hunting pipeline enforcing the per-run lifecycle.
    """
    # 1. Generate unique run_id
    run_id = custom_run_id or generate_run_id()
    start_time = datetime.now(timezone.utc)

    # 2. Configure per-run logger (sandbox/logs/<run_id>.log and console)
    logger = setup_logger("main", run_id=run_id)
    results_tool = ResultsTool()

    logger.info("=================================================================")
    logger.info(f"             AUTONOMOUS JOB HUNTER - STARTING [{run_id}]        ")
    logger.info("=================================================================")
    logger.info(f"RUN_STARTED: {run_id} at {start_time.isoformat()}")
    logger.info(f"Customer ID: {customer_id}")
    if search_prompt:
        logger.info(f"Search Prompt: \"{search_prompt}\"")

    # Initialize structured run metadata record
    run_record = {
        "run_id": run_id,
        "customer_id": customer_id,
        "search_prompt": search_prompt,
        "status": "running",
        "started_at": start_time.isoformat(),
        "completed_at": None,
        "duration_seconds": None,
        "candidate": {
            "target_job_count": candidate.target_job_count,
            "max_posting_age_days": candidate.max_posting_age_days,
            "target_roles": candidate.target_roles,
            "locations": candidate.locations,
            "work_modes": candidate.work_modes
        },
        "iterations": 0,
        "error": None
    }
    results_tool.save_run_record(run_id, run_record)

    try:
        # 3. Initialize Infrastructure Clients
        ollama_client = OllamaClient()
        searxng_client = SearXNGClient()

        # 4. Check Prerequisites
        check_prerequisites(ollama_client, searxng_client, logger)

        logger.info(
            f"Candidate loaded: Target Roles={candidate.target_roles}, "
            f"Skills={candidate.skills}, Experience={candidate.experience_years}y, "
            f"Max Posting Age={candidate.max_posting_age_days}d"
        )

        # 5. Generate Mission
        logger.info("Generating Search Mission...")
        mission_gen = MissionGenerator(ollama_client)
        mission = mission_gen.generate_mission(candidate, search_prompt=search_prompt)
        logger.info(f"Mission generated: Objective='{mission.objective}'")
        logger.info(
            f"Mission Parameters: Target={mission.minimum_target_jobs} jobs | "
            f"Max Age={mission.posting_age_days}d | Max Iterations={mission.max_iterations}"
        )

        # 6. Initialize and Run Autonomous Brain
        brain = AutonomousBrain(
            candidate=candidate,
            mission=mission,
            ollama_client=ollama_client,
            run_id=run_id,
            search_prompt=search_prompt
        )

        accepted_jobs = brain.run()

        # 7. Record Completion Metadata
        end_time = datetime.now(timezone.utc)
        duration = int((end_time - start_time).total_seconds())

        run_record["status"] = "completed"
        run_record["completed_at"] = end_time.isoformat()
        run_record["duration_seconds"] = duration
        run_record["iterations"] = brain.iteration
        results_tool.save_run_record(run_id, run_record)

        # 8. Display Summary
        logger.info("=================================================================")
        logger.info(f"             JOB SEARCH MISSION COMPLETED [{run_id}]            ")
        logger.info("=================================================================")
        logger.info(f"Total Accepted Jobs: {len(accepted_jobs)}/{mission.minimum_target_jobs} (Sorted: Newest First)")

        for idx, job in enumerate(accepted_jobs, 1):
            eval_score = brain.evaluations.get(job.url)
            score_str = f"Score: {eval_score.score}" if eval_score else "N/A"
            age_str = f"{job.posted_age_days}d ago" if job.posted_age_days is not None else "Unknown age"
            logger.info(f"  {idx}. [{job.company}] {job.title} ({job.location}) - {score_str} | {age_str} | Status: {job.availability_status}")
            logger.info(f"     URL: {job.url}")

        logger.info(f"\nHistorical results saved to: sandbox/output/runs/{run_id}/jobs.json")
        logger.info(f"Execution summary saved to:  sandbox/output/runs/{run_id}/summary.json")
        logger.info(f"Run metadata saved to:       sandbox/output/runs/{run_id}/run.json")
        logger.info(f"Latest results updated to:   sandbox/output/jobs.json")
        logger.info(f"Search memory saved to:      sandbox/memory/agent_memory.json")
        logger.info(f"Run log saved to:            sandbox/logs/{run_id}.log")
        logger.info(f"RUN_COMPLETED: {run_id}")

    except Exception as e:
        end_time = datetime.now(timezone.utc)
        duration = int((end_time - start_time).total_seconds())
        run_record["status"] = "interrupted" if isinstance(e, KeyboardInterrupt) else "failed"
        run_record["completed_at"] = end_time.isoformat()
        run_record["duration_seconds"] = duration
        run_record["error"] = str(e)
        results_tool.save_run_record(run_id, run_record)
        logger.error(f"RUN_FAILED: {run_id} encountered an error: {e}", exc_info=True)
        raise

    finally:
        close_run_logger()


def main() -> None:
    """CLI Argument Parsing, Mode Routing, and Entrypoint."""
    parser = argparse.ArgumentParser(
        description="Autonomous Job Hunter — Local-first AI Job Search Engine"
    )
    parser.add_argument(
        "--customer-id",
        type=str,
        default=None,
        help="Customer ID of the candidate (e.g. 12345) to load via CandidateRepository"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Direct search prompt string (e.g. 'Find React jobs in Bangalore')"
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Optional custom run identifier (generated automatically if omitted)"
    )
    # Backward compatibility flag
    parser.add_argument(
        "--candidate",
        type=str,
        default=None,
        help=argparse.SUPPRESS
    )

    args = parser.parse_args()

    # 1. Enforce Mutual Exclusivity between --customer-id and --prompt
    if args.customer_id and args.prompt:
        sys.stderr.write(
            "Error: --customer-id and --prompt are mutually exclusive. "
            "Specify either --customer-id to search for a registered candidate, "
            "or --prompt for a direct search prompt, or run without arguments for interactive mode.\n"
        )
        sys.exit(2)

    repository: CandidateRepository = LocalCandidateRepository()

    # Determine Customer ID if --candidate alias was passed
    active_customer_id = args.customer_id
    if not active_customer_id and args.candidate:
        cand_str = args.candidate.strip()
        active_customer_id = cand_str[:-5] if cand_str.endswith(".json") else cand_str

    # 2. Mode Routing
    if args.prompt:
        # MODE 3: Direct Prompt Mode
        search_prompt = args.prompt.strip()
        if not search_prompt:
            sys.stderr.write("Error: --prompt cannot be empty.\n")
            sys.exit(2)

        # Validate that prompt is job-related
        details = ProfileValidator.inspect_prompt_details(search_prompt)
        if not details.get("is_job_related", True):
            reason = details.get("reason", "Query does not appear to be a job search request.")
            sys.stderr.write(f"Error: {reason}\n")
            sys.exit(1)

        ollama_client = OllamaClient()
        try:
            candidate = ProfileValidator.from_prompt(search_prompt, ollama_client=ollama_client)
        except Exception as e:
            sys.stderr.write(f"Failed to generate profile from prompt: {e}\n")
            sys.exit(1)

        run_pipeline(
            candidate=candidate,
            customer_id="prompt_user",
            search_prompt=search_prompt,
            custom_run_id=args.run_id
        )

    elif active_customer_id:
        # MODE 2: Customer ID Mode
        customer_id = active_customer_id.strip()
        try:
            candidate = repository.get_candidate(customer_id)
        except CandidateNotFoundError:
            sys.stderr.write(f"Candidate not found: {customer_id}\n")
            sys.exit(1)
        except (CandidateDataError, ProfileValidationError) as e:
            sys.stderr.write(f"Candidate validation error for '{customer_id}': {e}\n")
            sys.exit(1)
        except Exception as e:
            sys.stderr.write(f"Unexpected error loading candidate '{customer_id}': {e}\n")
            sys.exit(1)

        run_pipeline(
            candidate=candidate,
            customer_id=customer_id,
            search_prompt=None,
            custom_run_id=args.run_id
        )

    else:
        # MODE 1: Interactive Prompt Mode (Customer-independent)
        print("=== Autonomous Job Hunter ===")
        try:
            while True:
                prompt_input = input("What kind of jobs are you looking for?\n> ").strip()
                if not prompt_input:
                    continue

                # Inspect prompt to check if it's job-related
                details = ProfileValidator.inspect_prompt_details(prompt_input)
                if not details.get("is_job_related", True):
                    reason = details.get("reason", "Query does not appear to be a job search request.")
                    print(f"\n[!] That does not appear to be a job search request ({reason}).")
                    print("Please enter a job search request (e.g. 'Looking for Python Backend Developer jobs in Delhi' or 'React developer'):\n")
                    continue
                break

            # If location was not provided, ask for location
            if "location" in details.get("missing", []):
                loc_input = input("Location was not specified. Enter target location (or press Enter for 'Remote'): ").strip()
                loc = loc_input if loc_input else "Remote"
                prompt_input += f" in {loc}"

            # If role was not detected, ask for role
            if "role" in details.get("missing", []):
                role_input = input("Job title or role was not specified. Enter target role (e.g. 'Software Engineer'): ").strip()
                if role_input:
                    prompt_input = f"{role_input} - {prompt_input}"

        except (EOFError, KeyboardInterrupt):
            print("\nExecution cancelled.")
            sys.exit(0)

        ollama_client = OllamaClient()
        try:
            candidate = ProfileValidator.from_prompt(prompt_input, ollama_client=ollama_client)
        except Exception as e:
            sys.stderr.write(f"Failed to generate profile from prompt: {e}\n")
            sys.exit(1)

        run_pipeline(
            candidate=candidate,
            customer_id="adhoc_user",
            search_prompt=prompt_input,
            custom_run_id=args.run_id
        )


if __name__ == "__main__":
    main()
