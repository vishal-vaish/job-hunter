"""
Autonomous Job Hunter - Comprehensive Verification Test Suite.

This file is responsible for:
- Testing Sandbox security boundaries (traversal blocking, permissions, categories).
- Testing Pipeline components (Normalizer, Deduplicator, HardFilterEngine).
- Testing Posting Age normalization (relative phrases, exact timestamps, unknown handling).
- Testing Posting Age deterministic filtering (<= max vs > max, unknown rejection).
- Testing Job Availability status verification (ACTIVE vs CLOSED/EXPIRED/REMOVED/UNKNOWN).
- Testing Latest-First sorting (newest posting age first, secondary score tie-break).
- Testing Providers and Search abstraction (LinkedIn provider query building, parsing, GlobalSearch).
- Testing Candidate Profile validation and Mission generation.
"""

from datetime import datetime, timezone, timedelta
import json
import logging
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

# Suppress console logging noise during automated test suite execution
logging.disable(logging.CRITICAL)

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config.settings import settings
from models.candidate import CandidateProfile
from models.mission import SearchMission
from models.job import Job
from models.evaluation import JobEvaluation
from security.sandbox import Sandbox, SandboxSecurityError, default_sandbox
from pipeline.normalizer import JobNormalizer
from pipeline.deduplicator import JobDeduplicator
from pipeline.filters import HardFilterEngine
from pipeline.availability import JobAvailabilityVerifier
from providers.linkedin import LinkedInProvider
from search.global_search import GlobalSearch
from agent.profile_validator import ProfileValidator, ProfileValidationError
from agent.tools.results import ResultsTool
from utils.logger import generate_run_id, setup_logger, close_run_logger
from storage.candidate_repository import (
    CandidateRepository,
    LocalCandidateRepository,
    ApiCandidateRepository,
    CandidateNotFoundError,
    CandidateDataError,
)


class TestSandboxSecurity(unittest.TestCase):
    """Verifies that the Sandbox enforces strict isolation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sandbox = Sandbox(root_dir=Path(self.temp_dir.name))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sandbox_categories_exist(self):
        for cat in ["output", "memory", "logs", "workspace"]:
            self.assertTrue(self.sandbox.categories[cat].exists())
        self.assertNotIn("input", self.sandbox.categories)

    def test_unauthorized_category_access(self):
        with self.assertRaises(SandboxSecurityError):
            self.sandbox.write_text("input", "forbidden.txt", "content")

    def test_directory_traversal_prevention(self):
        with self.assertRaises(SandboxSecurityError):
            self.sandbox.resolve_safe_path("output", "../../secret.txt")

    def test_absolute_path_prevention(self):
        with self.assertRaises(SandboxSecurityError):
            self.sandbox.resolve_safe_path("output", "C:/Windows/System32/calc.exe")

    def test_safe_write_and_read(self):
        test_file = "test_artifact.txt"
        self.sandbox.write_text("workspace", test_file, "sandbox safe data")
        self.assertTrue(self.sandbox.exists("workspace", test_file))
        content = self.sandbox.read_text("workspace", test_file)
        self.assertEqual(content, "sandbox safe data")


class TestPipeline(unittest.TestCase):
    """Verifies data normalization, deduplication, and deterministic filtering."""

    def test_normalizer(self):
        job = Job(
            provider="linkedin",
            title="Senior &amp; Staff Developer &lt;urgent&gt;",
            company="Acme &quot;Corp&quot;",
            location="Delhi, India\xa0",
            url="https://linkedin.com/jobs/view/123",
            description="Looking for Python &amp; Django developers."
        )
        cleaned = JobNormalizer.normalize_job(job)
        self.assertEqual(cleaned.title, "Senior & Staff Developer")
        self.assertEqual(cleaned.company, 'Acme "Corp"')
        self.assertEqual(cleaned.location, "Delhi, India")
        self.assertEqual(cleaned.description, "Looking for Python & Django developers.")

    def test_deduplicator(self):
        dedup = JobDeduplicator()
        url1 = "https://www.linkedin.com/jobs/view/998877?trackingId=abc1234&refId=xyz"
        url2 = "https://linkedin.com/jobs/view/998877?trk=public_jobs"
        norm1 = dedup.normalize_url(url1)
        norm2 = dedup.normalize_url(url2)
        self.assertEqual(norm1, norm2)
        self.assertEqual(norm1, "https://linkedin.com/jobs/view/998877")

    def test_hard_filters_company_exclusion(self):
        mission = SearchMission(
            objective="Test mission",
            search_roles=["Python Developer"],
            excluded_companies=["BannedCorp", "ShadyLLC"],
            locations=["Delhi"],
            posting_age_days=30
        )
        good_job = Job(
            provider="linkedin",
            title="Python Developer",
            company="GreatStartup",
            location="Delhi",
            url="https://linkedin.com/jobs/view/1",
            posted_age_days=3,
            availability_status="ACTIVE"
        )
        bad_job = Job(
            provider="linkedin",
            title="Python Developer",
            company="BannedCorp India",
            location="Delhi",
            url="https://linkedin.com/jobs/view/2",
            posted_age_days=3,
            availability_status="ACTIVE"
        )
        self.assertTrue(HardFilterEngine.evaluate(good_job, mission)[0])
        self.assertFalse(HardFilterEngine.evaluate(bad_job, mission)[0])


class TestFreshnessAndAvailability(unittest.TestCase):
    """Verifies posting age normalization, age filtering, availability checks, and sorting."""

    def test_posting_age_normalization_relative(self):
        # Test 'Today'
        _, age_today, conf_today = JobNormalizer.parse_posting_age("Today")
        self.assertEqual(age_today, 0)
        self.assertEqual(conf_today, "medium")

        # Test '3 days ago'
        _, age_days, conf_days = JobNormalizer.parse_posting_age("3 days ago")
        self.assertEqual(age_days, 3)
        self.assertEqual(conf_days, "medium")

        # Test '2 weeks ago'
        _, age_weeks, conf_weeks = JobNormalizer.parse_posting_age("2 weeks ago")
        self.assertEqual(age_weeks, 14)
        self.assertEqual(conf_weeks, "medium")

        # Test unknown / empty text
        _, age_none, conf_none = JobNormalizer.parse_posting_age(None, fallback_text="No dates here")
        self.assertIsNone(age_none)
        self.assertEqual(conf_none, "unknown")

    def test_posting_age_filter_logic(self):
        # 1 day <= 7 days -> KEEP
        pass_1d, _ = HardFilterEngine.matches_posting_age(
            Job(provider="linkedin", title="Dev", url="https://u1", posted_age_days=1),
            max_age_days=7
        )
        self.assertTrue(pass_1d)

        # 7 days <= 7 days -> KEEP
        pass_7d, _ = HardFilterEngine.matches_posting_age(
            Job(provider="linkedin", title="Dev", url="https://u2", posted_age_days=7),
            max_age_days=7
        )
        self.assertTrue(pass_7d)

        # 8 days > 7 days -> REJECT
        pass_8d, reason_8d = HardFilterEngine.matches_posting_age(
            Job(provider="linkedin", title="Dev", url="https://u3", posted_age_days=8),
            max_age_days=7
        )
        self.assertFalse(pass_8d)
        self.assertIn("exceeds maximum allowed", reason_8d)

        # Unknown posting age -> REJECT by default
        pass_unknown, reason_unknown = HardFilterEngine.matches_posting_age(
            Job(provider="linkedin", title="Dev", url="https://u4", posted_age_days=None),
            max_age_days=7
        )
        self.assertFalse(pass_unknown)
        self.assertIn("Unknown posting age", reason_unknown)

    def test_availability_filter_logic(self):
        # ACTIVE -> eligible
        pass_active, _ = HardFilterEngine.is_available(
            Job(provider="linkedin", title="Dev", url="https://u1", availability_status="ACTIVE")
        )
        self.assertTrue(pass_active)

        # CLOSED -> rejected
        pass_closed, _ = HardFilterEngine.is_available(
            Job(provider="linkedin", title="Dev", url="https://u2", availability_status="CLOSED")
        )
        self.assertFalse(pass_closed)

        # EXPIRED -> rejected
        pass_expired, _ = HardFilterEngine.is_available(
            Job(provider="linkedin", title="Dev", url="https://u3", availability_status="EXPIRED")
        )
        self.assertFalse(pass_expired)

        # REMOVED -> rejected
        pass_removed, _ = HardFilterEngine.is_available(
            Job(provider="linkedin", title="Dev", url="https://u4", availability_status="REMOVED")
        )
        self.assertFalse(pass_removed)

        # UNKNOWN -> rejected by default
        pass_unknown, _ = HardFilterEngine.is_available(
            Job(provider="linkedin", title="Dev", url="https://u5", availability_status="UNKNOWN")
        )
        self.assertFalse(pass_unknown)

    def test_latest_first_sorting(self):
        jobs = [
            Job(provider="linkedin", title="Job 5d", url="https://u5", posted_age_days=5),
            Job(provider="linkedin", title="Job 1d", url="https://u1", posted_age_days=1),
            Job(provider="linkedin", title="Job 3d", url="https://u3", posted_age_days=3),
            Job(provider="linkedin", title="Job 2d LowScore", url="https://u2a", posted_age_days=2),
            Job(provider="linkedin", title="Job 2d HighScore", url="https://u2b", posted_age_days=2),
        ]
        evaluations = {
            "https://u5": JobEvaluation(score=90, suitable=True),
            "https://u1": JobEvaluation(score=85, suitable=True),
            "https://u3": JobEvaluation(score=80, suitable=True),
            "https://u2a": JobEvaluation(score=75, suitable=True),
            "https://u2b": JobEvaluation(score=95, suitable=True),
        }

        # Sort newest-first (lowest posted_age_days, secondary score DESC)
        sorted_jobs = sorted(
            jobs,
            key=lambda j: (
                j.posted_age_days if j.posted_age_days is not None else 999999,
                -(evaluations[j.url].score if j.url in evaluations else 0)
            )
        )

        expected_order = [
            "Job 1d",
            "Job 2d HighScore",  # 2 days, score 95
            "Job 2d LowScore",   # 2 days, score 75
            "Job 3d",
            "Job 5d"
        ]
        actual_order = [j.title for j in sorted_jobs]
        self.assertEqual(actual_order, expected_order)

    def test_availability_verifier_snippet_markers(self):
        verifier = JobAvailabilityVerifier()
        closed_job = Job(
            provider="linkedin",
            title="Python Developer (No longer accepting applications)",
            company="Acme",
            location="Delhi",
            url="https://linkedin.com/jobs/view/999",
            description="Position has been filled."
        )
        verified = verifier.verify_job(closed_job)
        self.assertEqual(verified.availability_status, "CLOSED")
        self.assertIsNotNone(verified.availability_checked_at)


class TestProviders(unittest.TestCase):
    """Verifies LinkedIn provider query building and URL parsing."""

    def test_linkedin_query_builder(self):
        provider = LinkedInProvider()
        query = provider.build_search_query(
            role="Python Developer",
            location="Delhi",
            keywords=["Django", "FastAPI"]
        )
        self.assertIn("site:linkedin.com/jobs/view", query)
        self.assertIn('"Python Developer"', query)
        self.assertIn('"Delhi"', query)
        self.assertIn("Django", query)

    def test_linkedin_url_check(self):
        provider = LinkedInProvider()
        self.assertTrue(provider.is_provider_url("https://www.linkedin.com/jobs/view/12345"))
        self.assertFalse(provider.is_provider_url("https://github.com/torvalds/linux"))


class TestRunLifecycleAndLogging(unittest.TestCase):
    """Verifies per-run logging, execution history isolation, and failure safety."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sandbox = Sandbox(root_dir=Path(self.temp_dir.name))

    def tearDown(self):
        close_run_logger()
        self.temp_dir.cleanup()

    def test_run_id_generation(self):
        run_id_1 = generate_run_id()
        run_id_2 = generate_run_id()

        # Verify format: run_YYYYMMDD_HHMMSS_<4 hex chars>
        pattern = r"^run_\d{8}_\d{6}_[0-9a-f]{4}$"
        self.assertRegex(run_id_1, pattern)
        self.assertRegex(run_id_2, pattern)
        self.assertNotEqual(run_id_1, run_id_2)

    def test_per_run_logging(self):
        # Temporarily enable logging for isolated test verification
        logging.disable(logging.NOTSET)
        try:
            run_id = generate_run_id()
            logger_instance = setup_logger("test.run.lifecycle", run_id=run_id, sandbox=self.sandbox)
            # Remove console stream handlers so nothing is printed to terminal during test
            root = logging.getLogger()
            stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)]
            for h in stream_handlers:
                root.removeHandler(h)

            test_message = f"Lifecycle test log entry for {run_id}"
            logger_instance.info(test_message)

            # Verify log file exists in isolated temp sandbox/logs/<run_id>.log
            log_filename = f"{run_id}.log"
            self.assertTrue(self.sandbox.exists("logs", log_filename))
            log_content = self.sandbox.read_text("logs", log_filename)
            self.assertIn(run_id, log_content)
            self.assertIn(test_message, log_content)
        finally:
            close_run_logger()
            logging.disable(logging.CRITICAL)

    def test_results_tool_run_isolation(self):
        run_id = generate_run_id()
        tool = ResultsTool(self.sandbox)

        mission = SearchMission(
            objective="Run isolation test",
            search_roles=["Backend Developer"],
            locations=["Remote"],
            posting_age_days=14
        )

        job1 = Job(
            provider="linkedin",
            title="Junior Backend Dev",
            company="Startup A",
            location="Remote",
            url="https://linkedin.com/jobs/view/10001",
            posted_age_days=2,
            availability_status="ACTIVE"
        )
        job2 = Job(
            provider="linkedin",
            title="Senior Backend Dev",
            company="Startup B",
            location="Remote",
            url="https://linkedin.com/jobs/view/10002",
            posted_age_days=1,
            availability_status="ACTIVE"
        )

        evaluations = {
            job1.url: JobEvaluation(score=85, suitable=True, reasons=["Good fit"]),
            job2.url: JobEvaluation(score=92, suitable=True, reasons=["Strong match"])
        }

        # 1. Save run results
        paths = tool.save_run_results(run_id, mission, [job1, job2], evaluations)
        self.assertTrue(paths["historical"].exists())
        self.assertTrue(paths["current"].exists())

        # Check historical jobs.json
        hist_data = json.loads(self.sandbox.read_text("output", f"runs/{run_id}/jobs.json"))
        self.assertEqual(hist_data["metadata"]["run_id"], run_id)
        self.assertEqual(len(hist_data["jobs"]), 2)
        # Check newest first (job2 is 1d, job1 is 2d)
        self.assertEqual(hist_data["jobs"][0]["url"], job2.url)
        self.assertEqual(hist_data["jobs"][1]["url"], job1.url)

        # Check current jobs.json
        curr_data = json.loads(self.sandbox.read_text("output", "jobs.json"))
        self.assertEqual(curr_data["metadata"]["run_id"], run_id)
        self.assertEqual(len(curr_data["jobs"]), 2)

        # 2. Save summary.json
        stats = {
            "discovered": 10, "unique": 8, "stale": 2, "fresh": 6,
            "availability_checked": 6, "active": 4, "closed": 1,
            "expired": 0, "removed": 0, "unknown": 1, "hard_filter_passed": 3,
            "llm_evaluated": 3, "accepted": 2, "rejected": 1
        }
        rejections = [{"url": "https://linkedin.com/jobs/view/999", "stage": "hard_filter", "reason": "stale"}]
        tool.save_run_summary(run_id, stats, rejections)
        self.assertTrue(self.sandbox.exists("output", f"runs/{run_id}/summary.json"))
        summary_data = json.loads(self.sandbox.read_text("output", f"runs/{run_id}/summary.json"))
        self.assertEqual(summary_data["statistics"]["discovered"], 10)
        self.assertEqual(summary_data["statistics"]["accepted"], 2)
        self.assertEqual(len(summary_data["rejections"]), 1)

        # 3. Save run.json
        run_record = {
            "run_id": run_id,
            "status": "COMPLETED",
            "candidate_roles": ["Backend Developer"],
            "locations": ["Remote"]
        }
        tool.save_run_record(run_id, run_record)
        self.assertTrue(self.sandbox.exists("output", f"runs/{run_id}/run.json"))
        record_data = json.loads(self.sandbox.read_text("output", f"runs/{run_id}/run.json"))
        self.assertEqual(record_data["status"], "COMPLETED")

    def test_failure_safety_preserves_current_jobs(self):
        tool = ResultsTool(self.sandbox)
        run_id_success = generate_run_id()
        run_id_fail = generate_run_id()

        mission = SearchMission(
            objective="Baseline run",
            search_roles=["DevOps"],
            locations=["Remote"]
        )
        job = Job(
            provider="linkedin",
            title="DevOps Engineer",
            company="Stable Co",
            location="Remote",
            url="https://linkedin.com/jobs/view/20001",
            posted_age_days=1,
            availability_status="ACTIVE"
        )
        evals = {job.url: JobEvaluation(score=90, suitable=True)}

        # Run 1 succeeds: writes to current jobs.json
        tool.save_run_results(run_id_success, mission, [job], evals)
        curr_before = json.loads(self.sandbox.read_text("output", "jobs.json"))
        self.assertEqual(curr_before["metadata"]["run_id"], run_id_success)

        # Run 2 fails: only writes run.json with FAILED status, does not save run results
        fail_record = {
            "run_id": run_id_fail,
            "status": "FAILED",
            "error": "Simulated network timeout during search"
        }
        tool.save_run_record(run_id_fail, fail_record)

        # Verify run.json in failed run folder
        self.assertTrue(self.sandbox.exists("output", f"runs/{run_id_fail}/run.json"))
        fail_data = json.loads(self.sandbox.read_text("output", f"runs/{run_id_fail}/run.json"))
        self.assertEqual(fail_data["status"], "FAILED")

        # Verify current jobs.json is preserved and still references run_id_success!
        curr_after = json.loads(self.sandbox.read_text("output", "jobs.json"))
        self.assertEqual(curr_after["metadata"]["run_id"], run_id_success)
        self.assertEqual(curr_after["jobs"][0]["title"], "DevOps Engineer")


class TestCandidateRepositoryAndCLI(unittest.TestCase):
    """Verifies CandidateRepository abstraction, local lookup, CLI execution modes, and error handling."""

    def setUp(self):
        self.repo = LocalCandidateRepository()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sandbox = Sandbox(root_dir=Path(self.temp_dir.name))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_local_repository_lookup_success(self):
        profile = self.repo.get_candidate("12345")
        self.assertIsInstance(profile, CandidateProfile)
        self.assertEqual(profile.customer_id, "12345")
        self.assertTrue(len(profile.target_roles) > 0)
        self.assertEqual(profile.target_roles[0], "Python Developer")

    def test_local_repository_missing_customer(self):
        with self.assertRaises(CandidateNotFoundError) as ctx:
            self.repo.get_candidate("99999")
        self.assertIn("Candidate not found: 99999", str(ctx.exception))

    def test_local_repository_invalid_candidate_json(self):
        corrupt_file = self.repo.data_dir / "test_corrupt.json"
        try:
            corrupt_file.write_text("{ this is not valid json }", encoding="utf-8")
            with self.assertRaises(CandidateDataError) as ctx:
                self.repo.get_candidate("test_corrupt")
            self.assertIn("Malformed JSON", str(ctx.exception))
        finally:
            if corrupt_file.exists():
                corrupt_file.unlink()

    def test_repository_abstraction_interface(self):
        class MockApiRepository(CandidateRepository):
            def get_candidate(self, customer_id: str) -> CandidateProfile:
                return CandidateProfile(
                    customer_id=customer_id,
                    target_roles=["Rust Developer"],
                    skills=["Rust", "Tokio"],
                    locations=["Remote"],
                    target_job_count=3
                )

        mock_repo: CandidateRepository = MockApiRepository()
        cand = mock_repo.get_candidate("remote_cust_01")
        self.assertIsInstance(cand, CandidateProfile)
        self.assertEqual(cand.customer_id, "remote_cust_01")
        self.assertEqual(cand.target_roles, ["Rust Developer"])

    def test_profile_validator_from_prompt(self):
        prompt = "Find remote React/Next.js developer jobs in Bangalore posted within last 7 days"
        profile = ProfileValidator.from_prompt(prompt)
        self.assertIsInstance(profile, CandidateProfile)
        self.assertEqual(profile.customer_id, "prompt_user")
        self.assertEqual(profile.max_posting_age_days, 7)
        self.assertIn("remote", profile.work_modes)
        self.assertIn("Bangalore", profile.locations)

    def test_inspect_prompt_missing_location(self):
        # Prompt without location
        prompt1 = "Find senior Python developer jobs"
        details1 = ProfileValidator.inspect_prompt_details(prompt1)
        self.assertIn("location", details1["missing"])
        self.assertEqual(len(details1["locations"]), 0)

        # Prompt with location
        prompt2 = "Find Python developer jobs in Delhi"
        details2 = ProfileValidator.inspect_prompt_details(prompt2)
        self.assertNotIn("location", details2["missing"])
        self.assertIn("Delhi", details2["locations"])

    def test_inspect_prompt_off_topic_detection(self):
        off_topic_queries = [
            "what is too weather?",
            "tell me a joke",
            "how are you today?",
            "what is the capital of France?",
            "how to cook pasta",
            "just random chatter"
        ]
        for query in off_topic_queries:
            details = ProfileValidator.inspect_prompt_details(query)
            self.assertFalse(
                details["is_job_related"],
                f"Query '{query}' should be recognized as off-topic"
            )
            self.assertIsNotNone(details["reason"])

        # Legitimate queries should be marked job-related
        legit_queries = [
            "Python developer in Bangalore",
            "Looking for React jobs",
            "Data scientist remote",
            "Java backend engineer"
        ]
        for query in legit_queries:
            details = ProfileValidator.inspect_prompt_details(query)
            self.assertTrue(
                details["is_job_related"],
                f"Query '{query}' should be recognized as job-related"
            )

    def test_from_prompt_rejects_off_topic(self):
        with self.assertRaises(ProfileValidationError):
            ProfileValidator.from_prompt("what is too weather?")

    def test_cli_off_topic_prompt_exit_code(self):
        python_exe = sys.executable
        cmd = [python_exe, "main.py", "--prompt=what is too weather?"]
        proc = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Query appears to be a general inquiry or off-topic question", proc.stderr)


    def test_cli_mutually_exclusive_arguments(self):
        python_exe = sys.executable
        cmd = [python_exe, "main.py", "--customer-id=12345", "--prompt=Find Python jobs"]
        proc = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Error: --customer-id and --prompt are mutually exclusive", proc.stderr)

    def test_cli_unknown_customer_exit_code(self):
        python_exe = sys.executable
        cmd = [python_exe, "main.py", "--customer-id=99999"]
        proc = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Candidate not found: 99999", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_run_metadata_contains_customer_and_prompt(self):
        tool = ResultsTool(self.sandbox)
        run_id = generate_run_id()
        mission = SearchMission(
            objective="Metadata test",
            search_roles=["Fullstack"],
            locations=["Remote"]
        )
        job = Job(
            provider="linkedin",
            title="Fullstack Engineer",
            company="TestCo",
            location="Remote",
            url="https://linkedin.com/jobs/view/30001",
            posted_age_days=2,
            availability_status="ACTIVE"
        )
        evals = {job.url: JobEvaluation(score=88, suitable=True)}

        tool.save_run_results(
            run_id=run_id,
            mission=mission,
            accepted_jobs=[job],
            evaluations=evals,
            customer_id="12345",
            search_prompt="Find Fullstack jobs"
        )

        hist_data = json.loads(self.sandbox.read_text("output", f"runs/{run_id}/jobs.json"))
        self.assertEqual(hist_data["metadata"]["customer_id"], "12345")
        self.assertEqual(hist_data["metadata"]["search_prompt"], "Find Fullstack jobs")

        tool.save_run_summary(
            run_id=run_id,
            statistics={"discovered": 1, "accepted": 1},
            rejections=[],
            customer_id="12345",
            search_prompt="Find Fullstack jobs"
        )
        summary_data = json.loads(self.sandbox.read_text("output", f"runs/{run_id}/summary.json"))
        self.assertEqual(summary_data["customer_id"], "12345")
        self.assertEqual(summary_data["search_prompt"], "Find Fullstack jobs")


if __name__ == "__main__":
    unittest.main()


