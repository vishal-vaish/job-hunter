"""
Infrastructure package for Autonomous Job Hunter.
Exposes communication clients for local Ollama LLM and SearXNG meta-search engine.
"""

from .ollama import OllamaClient, OllamaError
from .searxng import SearXNGClient, SearXNGError

__all__ = ["OllamaClient", "OllamaError", "SearXNGClient", "SearXNGError"]
