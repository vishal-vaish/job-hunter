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
    """Verifies LinkedIn provider query building, URL matching, defensive parsing, and GlobalSearch telemetry."""

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

    def test_linkedin_url_matching_comprehensive(self):
        provider = LinkedInProvider()
        valid_urls = [
            "https://www.linkedin.com/jobs/view/12345",
            "https://in.linkedin.com/jobs/view/45678",
            "https://uk.linkedin.com/jobs/view/software-engineer-7890",
            "https://in.linkedin.com/jobs/python-developer-jobs-kolkata",
            "https://www.linkedin.com/jobs/search?keywords=Python",
            "https://www.linkedin.com/jobs/collections/recommended",
            "https://www.linkedin.com/jobs/",
            "https://www.linkedin.com/jobs/view/senior-python-dev-at-tech-998877?position=1&trk=public_jobs"
        ]
        for url in valid_urls:
            self.assertTrue(provider.is_provider_url(url), f"Should match valid LinkedIn job URL: {url}")

        invalid_urls = [
            "https://www.linkedin.com/feed/",
            "https://www.linkedin.com/in/john-doe",
            "https://www.linkedin.com/company/google",
            "https://www.linkedin.com/school/stanford-university/",
            "https://www.linkedin.com/pulse/some-article",
            "https://www.python.org/",
            "https://www.w3schools.com/python/",
            "https://github.com/torvalds/linux",
            "",
            None
        ]
        for url in invalid_urls:
            self.assertFalse(provider.is_provider_url(url), f"Should reject non-job URL: {url}")

    def test_linkedin_clean_url(self):
        provider = LinkedInProvider()
        # View URL with slug and query params
        url1 = "https://in.linkedin.com/jobs/view/python-developer-at-acme-123456?trk=public_jobs&trackingId=abc"
        self.assertEqual(provider.clean_url(url1), "https://www.linkedin.com/jobs/view/123456")

        # View URL with just id
        url2 = "https://www.linkedin.com/jobs/view/998877?refId=xyz"
        self.assertEqual(provider.clean_url(url2), "https://www.linkedin.com/jobs/view/998877")

        # General jobs directory URL stripping tracking
        url3 = "https://in.linkedin.com/jobs/python-jobs?position=1&pageNum=0&trk=public_jobs"
        self.assertEqual(provider.clean_url(url3), "https://in.linkedin.com/jobs/python-jobs")

    def test_linkedin_parse_realistic_searxng_result(self):
        provider = LinkedInProvider()
        raw_result = {
            "url": "https://in.linkedin.com/jobs/view/python-developer-at-acme-corp-4467855637?trk=public_jobs",
            "title": "Python Developer - Acme Corp - Delhi, India | LinkedIn",
            "content": "Acme Corp is hiring a Python Developer in Delhi. 3 days ago. Experience with FastAPI and PostgreSQL required.",
            "publishedDate": "3 days ago",
            "engines": ["bing"],
            "score": 1.0
        }
        job, fail_reason = provider.parse_result_detailed(raw_result, search_query="test query")
        self.assertIsNotNone(job)
        self.assertIsNone(fail_reason)
        self.assertEqual(job.title, "Python Developer")
        self.assertEqual(job.company, "Acme Corp")
        self.assertEqual(job.location, "Delhi, India")
        self.assertEqual(job.url, "https://www.linkedin.com/jobs/view/4467855637")
        self.assertEqual(job.posted_text, "3 days ago")
        self.assertEqual(job.provider, "linkedin")

    def test_linkedin_parse_fallback_unknown_company_location(self):
        provider = LinkedInProvider()
        raw_result = {
            "url": "https://www.linkedin.com/jobs/view/555123",
            "title": "Senior Backend Engineer | LinkedIn",
            "content": "Looking for senior backend developers to join our team.",
            "engines": ["bing"],
            "score": 0.8
        }
        job, fail_reason = provider.parse_result_detailed(raw_result, search_query="test query")
        self.assertIsNotNone(job)
        self.assertEqual(job.title, "Senior Backend Engineer")
        self.assertEqual(job.company, "Unknown")
        self.assertEqual(job.location, "Unknown")
        self.assertEqual(job.url, "https://www.linkedin.com/jobs/view/555123")

    def test_linkedin_parse_failure_on_non_provider_url(self):
        provider = LinkedInProvider()
        raw_result = {
            "url": "https://www.python.org/downloads/",
            "title": "Download Python | Python.org",
            "content": "The official home of the Python Programming Language"
        }
        job, fail_reason = provider.parse_result_detailed(raw_result, search_query="test query")
        self.assertIsNone(job)
        self.assertIn("not a recognized LinkedIn job URL", fail_reason)

    def test_global_search_telemetry_all_matched(self):
        class MockSearXNGClient:
            def search(self, query: str, pageno: int = 1):
                return [
                    {
                        "url": f"https://www.linkedin.com/jobs/view/{i}",
                        "title": f"Python Developer - Company {i} - Delhi | LinkedIn",
                        "content": f"Description for job {i}",
                        "publishedDate": "1 day ago"
                    }
                    for i in range(10)
                ]

        gs = GlobalSearch(searxng_client=MockSearXNGClient())
        jobs = gs.search(query="site:linkedin.com/jobs/view Python", allowed_providers=["linkedin"])
        self.assertEqual(len(jobs), 10)
        telemetry = gs.last_telemetry
        self.assertEqual(telemetry.raw_results, 10)
        self.assertEqual(telemetry.provider_matches, 10)
        self.assertEqual(telemetry.parse_successes, 10)
        self.assertEqual(telemetry.parse_failures, 0)
        self.assertEqual(telemetry.unmatched_urls, 0)

    def test_global_search_telemetry_domain_mismatch(self):
        class MockSearXNGClient:
            def search(self, query: str, pageno: int = 1):
                # Search engine returned general web results instead of LinkedIn
                return [
                    {"url": "https://www.python.org/", "title": "Welcome to Python.org", "content": "Official site"},
                    {"url": "https://www.w3schools.com/python/", "title": "Python Tutorial", "content": "Tutorials"},
                    {"url": "https://en.wikipedia.org/wiki/Python", "title": "Python Wikipedia", "content": "Wiki"}
                ]

        gs = GlobalSearch(searxng_client=MockSearXNGClient())
        jobs = gs.search(query="Python jobs", allowed_providers=["linkedin"])
        self.assertEqual(len(jobs), 0)
        telemetry = gs.last_telemetry
        self.assertEqual(telemetry.raw_results, 3)
        self.assertEqual(telemetry.provider_matches, 0)
        self.assertEqual(telemetry.unmatched_urls, 3)
        self.assertEqual(telemetry.parse_successes, 0)
        self.assertEqual(len(telemetry.rejections), 3)

    def test_brain_diagnose_case_distinction(self):
        from agent.brain import AutonomousBrain
        from models.candidate import CandidateProfile
        from models.mission import SearchMission

        candidate = CandidateProfile(
            customer_id="test_user",
            target_roles=["Python Developer", "Backend Engineer"],
            skills=["Python", "FastAPI"],
            locations=["Delhi"],
            max_posting_age_days=7
        )
        mission = SearchMission(
            objective="Test mission",
            search_roles=["Python Developer"],
            locations=["Delhi"],
            posting_age_days=7,
            max_iterations=5
        )
        brain = AutonomousBrain(candidate=candidate, mission=mission)

        # Case A: Search engine returned 0 results
        obs_a = {
            "accepted_jobs_count": 0,
            "target_job_count": 10,
            "last_iteration_stats": {
                "raw_count": 0,
                "search_raw_results": 0,
                "search_provider_matches": 0,
                "search_parse_failures": 0
            }
        }
        brain.iteration = 1
        diag_a = brain.diagnose(obs_a)
        self.assertIn("Zero search results returned by search engine", diag_a)

        # Case B1: Search engine returned results, but none matched provider (domain mismatch)
        obs_b1 = {
            "accepted_jobs_count": 0,
            "target_job_count": 10,
            "last_iteration_stats": {
                "raw_count": 0,
                "search_raw_results": 10,
                "search_provider_matches": 0,
                "search_unmatched_urls": 10
            }
        }
        diag_b1 = brain.diagnose(obs_b1)
        self.assertIn("Provider domain mismatch", diag_b1)
        self.assertIn("without mutating candidate target roles", diag_b1)

        # Case B2: Provider URLs found, but parsing failed
        obs_b2 = {
            "accepted_jobs_count": 0,
            "target_job_count": 10,
            "last_iteration_stats": {
                "raw_count": 0,
                "search_raw_results": 10,
                "search_provider_matches": 10,
                "search_parse_failures": 10
            }
        }
        diag_b2 = brain.diagnose(obs_b2)
        self.assertIn("Provider parsing failure", diag_b2)
        self.assertIn("without mutating candidate target roles", diag_b2)

    def test_full_brain_search_pipeline_flow_with_mocked_data(self):
        """
        Verifies the full end-to-end code flow with realistic mocked SearXNG data:
        SearXNG raw results (mixed LinkedIn + non-provider) -> GlobalSearch routing & telemetry
        -> LinkedIn parsing & normalization -> Deduplication -> Freshness & Hard filters
        -> Semantic evaluation -> Brain state reflection -> Final results saving.
        Ensures zero realtime network calls, zero sandbox pollution, and no role mutation.
        """
        from agent.brain import AutonomousBrain
        from agent.tools.search_jobs import SearchJobsTool
        from agent.tools.memory import MemoryTool
        from agent.tools.results import ResultsTool
        from agent.evaluator import JobEvaluator

        # 1. Realistic mocked SearXNG search engine output (Bing style with mixed results)
        mock_raw_searxng_results = [
            # 3 Non-provider URLs injected by search engine
            {"url": "https://www.python.org/", "title": "Welcome to Python.org", "content": "Official Python website."},
            {"url": "https://www.w3schools.com/python/", "title": "Python Tutorial - W3Schools", "content": "Learn Python."},
            {"url": "https://en.wikipedia.org/wiki/Python", "title": "Python (programming language) - Wikipedia", "content": "Wiki."},
            # 7 LinkedIn results with varying freshness and locations
            {
                "url": "https://in.linkedin.com/jobs/view/python-developer-at-techcorp-4467855631?trk=public_jobs",
                "title": "Python Developer - TechCorp - Delhi, India | LinkedIn",
                "content": "TechCorp is hiring a Python Developer in Delhi. 2 days ago. Experience with FastAPI and Django.",
                "publishedDate": "2 days ago"
            },
            {
                "url": "https://in.linkedin.com/jobs/view/backend-engineer-at-startupx-4467855632",
                "title": "Backend Engineer - StartupX - Delhi, India | LinkedIn",
                "content": "StartupX is seeking a Backend Engineer in Delhi. 3 days ago. Python, REST, PostgreSQL.",
                "publishedDate": "3 days ago"
            },
            {
                "url": "https://in.linkedin.com/jobs/view/senior-python-dev-at-innovate-4467855633",
                "title": "Senior Python Developer - Innovate - Delhi, India | LinkedIn",
                "content": "Innovate is hiring in Delhi. 1 day ago. Python, Microservices.",
                "publishedDate": "1 day ago"
            },
            {
                "url": "https://in.linkedin.com/jobs/view/stale-python-dev-at-oldco-4467855634",
                "title": "Python Developer - OldCo - Delhi, India | LinkedIn",
                "content": "OldCo hiring Python developer in Delhi. 45 days ago.",
                "publishedDate": "45 days ago"  # Stale: > 7 days constraint!
            },
            {
                "url": "https://uk.linkedin.com/jobs/view/python-engineer-at-londonltd-4467855635",
                "title": "Python Developer - LondonLtd - London, UK | LinkedIn",
                "content": "LondonLtd hiring Python developer in London, UK. 2 days ago.",
                "publishedDate": "2 days ago"  # Location mismatch: London != Delhi
            },
            {
                "url": "https://in.linkedin.com/jobs/view/closed-python-job-4467855636",
                "title": "Python Developer (No longer accepting applications) - InActiveCo - Delhi | LinkedIn",
                "content": "Position has been filled. Delhi, India. 2 days ago.",
                "publishedDate": "2 days ago"  # Closed status
            },
            {
                "url": "https://in.linkedin.com/jobs/view/python-backend-at-cloudco-4467855637",
                "title": "Python Backend Developer - CloudCo - Delhi, India | LinkedIn",
                "content": "CloudCo hiring in Delhi. 4 days ago. Python, AWS, Docker.",
                "publishedDate": "4 days ago"
            }
        ]

        class MockSearXNGClient:
            def search(self, query: str, pageno: int = 1):
                return mock_raw_searxng_results

        from agent.brain import QueryStrategy

        class MockOllamaClient:
            def generate_structured(self, prompt: str, schema=None, system: str = "", max_retries: int = 2):
                if schema == QueryStrategy or (schema and getattr(schema, "__name__", "") == "QueryStrategy"):
                    return QueryStrategy(
                        query='site:linkedin.com/jobs/view "Python Developer" "Delhi" Python',
                        rationale="Mocked query strategy for Python Developer in Delhi"
                    )
                # Return high score evaluation for candidate
                return JobEvaluation(
                    score=88,
                    suitable=True,
                    reasons=["Matches Python and Backend requirements in Delhi"],
                    matched_skills=["Python", "FastAPI"],
                    missing_skills=[]
                )

        class MockAvailabilityVerifier(JobAvailabilityVerifier):
            def verify_batch(self, jobs):
                for j in jobs:
                    if "closed" in j.url or (j.description and "filled" in j.description):
                        j.availability_status = "CLOSED"
                    else:
                        j.availability_status = "ACTIVE"
                    j.availability_checked_at = datetime.now(timezone.utc).isoformat()
                return jobs

        # 2. Setup isolated temp sandbox to avoid writing to real sandbox directories
        temp_dir = tempfile.TemporaryDirectory()
        try:
            mock_ollama = MockOllamaClient()
            isolated_sandbox = Sandbox(root_dir=Path(temp_dir.name))
            results_tool = ResultsTool(sandbox=isolated_sandbox)
            memory_tool = MemoryTool(sandbox=isolated_sandbox)
            evaluator = JobEvaluator(ollama_client=mock_ollama)

            gs = GlobalSearch(searxng_client=MockSearXNGClient())
            search_tool = SearchJobsTool(global_search=gs)

            candidate = CandidateProfile(
                customer_id="mock_user_1",
                target_roles=["Python Developer", "Backend Engineer"],
                skills=["Python", "FastAPI", "PostgreSQL"],
                locations=["Delhi"],
                work_modes=["remote", "hybrid"],
                max_posting_age_days=7,
                target_job_count=2
            )
            mission = SearchMission(
                objective="Find Python Developer or Backend Engineer jobs in Delhi, remote or hybrid, posted within the last 7 days",
                search_roles=["Python Developer", "Backend Engineer"],
                locations=["Delhi"],
                posting_age_days=7,
                minimum_target_jobs=2,
                max_iterations=3
            )

            brain = AutonomousBrain(
                candidate=candidate,
                mission=mission,
                search_tool=search_tool,
                memory_tool=memory_tool,
                results_tool=results_tool,
                evaluator=evaluator,
                availability_verifier=MockAvailabilityVerifier(),
                ollama_client=mock_ollama,
                run_id="run_mock_test_0001"
            )

            # 3. Execute brain loop
            accepted = brain.run()

            # 4. Verify telemetry captured during the search step
            telemetry = search_tool.last_telemetry
            self.assertEqual(telemetry.raw_results, 10)
            self.assertEqual(telemetry.provider_matches, 7)
            self.assertEqual(telemetry.unmatched_urls, 3)
            self.assertEqual(telemetry.parse_successes, 7)
            self.assertEqual(telemetry.parse_failures, 0)

            # 5. Verify filtering and acceptance
            self.assertGreaterEqual(len(accepted), 2)
            self.assertTrue(brain.is_stopped)

            # Verify accepted jobs all match target roles, locations, and age <= 7
            for job in accepted:
                self.assertIn("Delhi", job.location)
                self.assertLessEqual(job.posted_age_days, 7)
                self.assertIn(job.url, [
                    "https://linkedin.com/jobs/view/4467855631",
                    "https://linkedin.com/jobs/view/4467855632",
                    "https://linkedin.com/jobs/view/4467855633",
                    "https://linkedin.com/jobs/view/4467855637"
                ])

            # Verify brain did not mutate roles to generic titles
            self.assertEqual(candidate.target_roles, ["Python Developer", "Backend Engineer"])

            # Verify persisted results in isolated sandbox
            self.assertTrue(isolated_sandbox.exists("output", "runs/run_mock_test_0001/jobs.json"))
            self.assertTrue(isolated_sandbox.exists("output", "runs/run_mock_test_0001/summary.json"))
            summary = json.loads(isolated_sandbox.read_text("output", "runs/run_mock_test_0001/summary.json"))
            self.assertGreaterEqual(summary["statistics"]["accepted"], 2)

        finally:
            temp_dir.cleanup()



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


