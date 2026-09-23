"""
Job Search Providers package.

This package defines the pluggable job board abstraction and implementations:
- base.py: Abstract Base Provider interface.
- linkedin.py: Pluggable LinkedIn provider leveraging SearXNG discovery.
"""

from .base import BaseJobProvider
from .linkedin import LinkedInProvider

__all__ = ["BaseJobProvider", "LinkedInProvider"]
