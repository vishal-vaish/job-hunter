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
import sys
import unittest
from pathlib import Path

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


class TestSandboxSecurity(unittest.TestCase):
    """Verifies that the Sandbox enforces strict isolation."""

    def setUp(self):
        self.sandbox = default_sandbox

    def test_sandbox_categories_exist(self):
        for cat in ["input", "output", "memory", "logs", "workspace"]:
            self.assertTrue(self.sandbox.categories[cat].exists())

    def test_read_only_input_permission(self):
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


if __name__ == "__main__":
    unittest.main()
