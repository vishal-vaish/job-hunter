"""
Ollama Local LLM Client Module.

This file is responsible for:
- Interacting with the locally hosted Ollama inference server (default: http://localhost:11434).
- Executing natural language generation and structured JSON generation.
- Validating LLM outputs strictly against Pydantic schemas.
- Handling communication retries, model recovery, and preventing application crashes
  when Ollama encounters timeouts or malformed outputs.
"""

import json
from typing import Any, Dict, List, Optional, Type, TypeVar
import requests
from pydantic import BaseModel, ValidationError

from config.settings import settings
from utils.logger import get_logger

logger = get_logger("infrastructure.ollama")

T = TypeVar("T", bound=BaseModel)


class OllamaError(Exception):
    """Raised when Ollama API returns an error or is unreachable."""
    pass


class OllamaClient:
    """
    Client for interacting with local Ollama API for reasoning and structured evaluation.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None
    ) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout = timeout or settings.ollama_timeout_seconds

    def check_health(self) -> bool:
        """
        Verifies that the Ollama server is reachable and responsive.
        """
        try:
            resp = requests.get(f"{self.base_url}/", timeout=3)
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama health check failed at {self.base_url}: {e}")
            return False

    def list_models(self) -> List[str]:
        """
        Retrieves the list of installed models on the local Ollama instance.
        """
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return [m.get("name", "") for m in data.get("models", [])]
            return []
        except Exception as e:
            logger.error(f"Failed to query Ollama models: {e}")
            return []

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        format_type: Any = None,
        options: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Sends a completion request to Ollama /api/generate.
        """
        endpoint = f"{self.base_url}/api/generate"
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }
        if system:
            payload["system"] = system
        if format_type is not None:
            payload["format"] = format_type
        if options:
            payload["options"] = options
        else:
            payload["options"] = {"temperature": 0.2}

        try:
            resp = requests.post(endpoint, json=payload, timeout=self.timeout)
            if resp.status_code != 200:
                raise OllamaError(f"Ollama returned HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            return data.get("response", "").strip()
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error communicating with Ollama: {e}")
            raise OllamaError(f"Ollama connection error: {e}") from e

    def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        system: Optional[str] = None,
        max_retries: Optional[int] = None
    ) -> T:
        """
        Requests structured JSON from Ollama using native grammar-constrained decoding
        and validates it with a Pydantic schema.
        Automatically retries with targeted error feedback if validation fails.
        """
        retries = max_retries or settings.ollama_max_retries
        current_prompt = prompt
        schema_dict = schema.model_json_schema()

        augmented_system = (
            (system + "\n\n" if system else "") +
            "You are a structured data generator. "
            "Output a complete JSON object with all required properties filled with concrete values. "
            "Do not include markdown fences or conversational text."
        )

        for attempt in range(1, retries + 1):
            try:
                raw_response = self.generate(
                    prompt=current_prompt,
                    system=augmented_system,
                    format_type=schema_dict
                )

                if not raw_response:
                    raise OllamaError("Empty response received from Ollama")

                # Parse JSON
                parsed_json = json.loads(raw_response)

                # Validate with Pydantic
                validated_obj = schema.model_validate(parsed_json)
                return validated_obj

            except (json.JSONDecodeError, ValidationError, OllamaError) as err:
                logger.warning(
                    f"Structured generation attempt {attempt}/{retries} failed for schema {schema.__name__}: {err}"
                )
                if attempt == retries:
                    logger.error(f"All {retries} structured generation attempts failed for schema {schema.__name__}.")
                    raise

                # Add corrective instruction to prompt for subsequent retry
                current_prompt = (
                    f"{prompt}\n\n"
                    f"ATTENTION: Your previous output produced this error:\n{str(err)}\n"
                    "Please fix the error and return ONLY the valid JSON object conforming to the schema."
                )

        raise OllamaError(f"Failed to generate structured data for {schema.__name__}")
