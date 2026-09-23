"""
Search routing package for Autonomous Job Hunter.
Exposes GlobalSearch for orchestrating provider queries without coupling to the Brain.
"""

from .global_search import GlobalSearch, default_global_search

__all__ = ["GlobalSearch", "default_global_search"]
