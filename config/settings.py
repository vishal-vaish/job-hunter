"""
Application Configuration and Settings Module.

This file is responsible for:
- Loading environment variables from .env if present.
- Centralizing application configuration (Ollama host, SearXNG host, models, timeouts).
- Providing deterministic defaults for project paths and execution limits.
- Preventing hardcoding of external URLs or infrastructure dependencies across the codebase.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load variables from .env file located at repository root
load_dotenv()

# Root directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Sandbox root directory (enforced by the security layer)
SANDBOX_DIR = BASE_DIR / "sandbox"


class Settings:
    """
    Centralized configuration settings for the Autonomous Job Hunter system.
    """

    def __init__(self) -> None:
        # ---------------------------------------------------------
        # Ollama LLM Configuration
        # ---------------------------------------------------------
        # URL where the local Ollama instance is serving API requests
        self.ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        # Model identifier for reasoning, mission generation, and job evaluation
        self.ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        # Request timeout for Ollama inference in seconds
        self.ollama_timeout_seconds: int = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
        # Maximum retries on transient connection or malformed JSON errors
        self.ollama_max_retries: int = int(os.getenv("OLLAMA_MAX_RETRIES", "3"))

        # ---------------------------------------------------------
        # SearXNG Configuration
        # ---------------------------------------------------------
        # URL where local SearXNG is serving search requests
        self.searxng_base_url: str = os.getenv("SEARXNG_BASE_URL", "http://localhost:8081").rstrip("/")
        # Request timeout for SearXNG searches in seconds
        self.searxng_timeout_seconds: int = int(os.getenv("SEARXNG_TIMEOUT_SECONDS", "30"))

        # ---------------------------------------------------------
        # Directory Paths (Filesystem and Sandbox)
        # ---------------------------------------------------------
        self.base_dir: Path = BASE_DIR
        self.sandbox_dir: Path = SANDBOX_DIR
        self.input_dir: Path = SANDBOX_DIR / "input"
        self.output_dir: Path = SANDBOX_DIR / "output"
        self.memory_dir: Path = SANDBOX_DIR / "memory"
        self.logs_dir: Path = SANDBOX_DIR / "logs"
        self.workspace_dir: Path = SANDBOX_DIR / "workspace"

        # ---------------------------------------------------------
        # Agent & Execution Defaults
        # ---------------------------------------------------------
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
        self.default_target_jobs: int = int(os.getenv("DEFAULT_TARGET_JOBS", "10"))
        self.default_max_iterations: int = int(os.getenv("DEFAULT_MAX_ITERATIONS", "5"))
        self.default_evaluation_threshold: int = int(os.getenv("DEFAULT_EVALUATION_THRESHOLD", "70"))


# Global singleton instance for settings
settings = Settings()
