"""
Job Processing Pipeline package.

This package provides deterministic data processing:
- normalizer.py: Standardizes raw provider attributes and cleans text.
- deduplicator.py: Deduplicates job listings by canonical URL and identifier.
- filters.py: Implements deterministic hard filters (companies, locations, work modes).
"""

from .normalizer import JobNormalizer
from .deduplicator import JobDeduplicator
from .filters import HardFilterEngine
from .availability import JobAvailabilityVerifier

__all__ = ["JobNormalizer", "JobDeduplicator", "HardFilterEngine", "JobAvailabilityVerifier"]
