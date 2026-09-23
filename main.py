"""
Autonomous Job Hunter - Main CLI Entrypoint.

This file is responsible for:
- Orchestrating the end-to-end execution flow of the Autonomous Job Hunter system:
  1. Verifying health of local infrastructure (Ollama at localhost:11434, SearXNG at localhost:8081).
  2. Loading the structured CandidateProfile from sandbox/input/.
  3. Validating the profile deterministically with ProfileValidator.
  4. Synthesizing a SearchMission via MissionGenerator.
  5. Initializing the Autonomous Brain and running the OBSERVE -> DIAGNOSE -> DECIDE -> ACT -> REFLECT loop.
  6. Storing the final accepted jobs into sandbox/output/jobs.json.
- Providing command-line argument handling for candidate profiles and execution limits.
"""

import argparse
import sys
from pathlib import Path

from agent.brain import AutonomousBrain
from agent.mission_generator import MissionGenerator
from agent.profile_validator import ProfileValidator
from config.settings import settings
from infrastructure.ollama import OllamaClient
from infrastructure.searxng import SearXNGClient
from security.sandbox import default_sandbox
from utils.logger import get_logger, setup_logger

# Initialize logger
logger = setup_logger("main")


def check_prerequisites(ollama: OllamaClient, searxng: SearXNGClient) -> bool:
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


def load_candidate_profile(filename: str = "candidate.json"):
    """
    Loads candidate data from the sandbox/input/ directory.
    """
    if not default_sandbox.exists("input", filename):
        logger.error(f"Candidate profile not found in sandbox/input/{filename}")
        sys.exit(1)

    raw_data = default_sandbox.read_json("input", filename)
    profile = ProfileValidator.from_dict(raw_data)
    return profile


def run_pipeline(candidate_file: str = "candidate.json") -> None:
    """
    Runs the complete autonomous job hunting pipeline.
    """
    logger.info("=================================================================")
    logger.info("             AUTONOMOUS JOB HUNTER - STARTING                    ")
    logger.info("=================================================================")

    # 1. Initialize Infrastructure Clients
    ollama_client = OllamaClient()
    searxng_client = SearXNGClient()

    # 2. Check Prerequisites
    check_prerequisites(ollama_client, searxng_client)

    # 3. Load Candidate Profile
    logger.info(f"Loading candidate profile from sandbox/input/{candidate_file}...")
    candidate = load_candidate_profile(candidate_file)
    logger.info(
        f"Candidate loaded: Target Roles={candidate.target_roles}, "
        f"Skills={candidate.skills}, Experience={candidate.experience_years}y, "
        f"Max Posting Age={candidate.max_posting_age_days}d"
    )

    # 4. Generate Mission
    logger.info("Generating Search Mission from candidate profile...")
    mission_gen = MissionGenerator(ollama_client)
    mission = mission_gen.generate_mission(candidate)
    logger.info(f"Mission generated: Objective='{mission.objective}'")
    logger.info(
        f"Mission Parameters: Target={mission.minimum_target_jobs} jobs | "
        f"Max Age={mission.posting_age_days}d | Max Iterations={mission.max_iterations}"
    )

    # 5. Initialize and Run Autonomous Brain
    brain = AutonomousBrain(
        candidate=candidate,
        mission=mission,
        ollama_client=ollama_client
    )

    accepted_jobs = brain.run()

    # 6. Display Summary
    logger.info("=================================================================")
    logger.info("             JOB SEARCH MISSION COMPLETED                        ")
    logger.info("=================================================================")
    logger.info(f"Total Accepted Jobs: {len(accepted_jobs)}/{mission.minimum_target_jobs} (Sorted: Newest First)")

    for idx, job in enumerate(accepted_jobs, 1):
        eval_score = brain.evaluations.get(job.url)
        score_str = f"Score: {eval_score.score}" if eval_score else "N/A"
        age_str = f"{job.posted_age_days}d ago" if job.posted_age_days is not None else "Unknown age"
        logger.info(f"  {idx}. [{job.company}] {job.title} ({job.location}) - {score_str} | {age_str} | Status: {job.availability_status}")
        logger.info(f"     URL: {job.url}")

    logger.info("\nResults saved to: sandbox/output/jobs.json")
    logger.info("Search memory saved to: sandbox/memory/agent_memory.json")
    logger.info("Execution log saved to: sandbox/logs/agent.log")


def main() -> None:
    """CLI Argument Parsing and Entrypoint."""
    parser = argparse.ArgumentParser(
        description="Autonomous Job Hunter — Local-first AI Job Search Engine"
    )
    parser.add_argument(
        "--candidate",
        type=str,
        default="candidate.json",
        help="Filename of the candidate profile JSON inside sandbox/input/ (default: candidate.json)"
    )
    args = parser.parse_args()

    run_pipeline(candidate_file=args.candidate)


if __name__ == "__main__":
    main()
