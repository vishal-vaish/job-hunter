"""
Sandbox Security Module.

This file is responsible for:
- Enforcing application-level filesystem isolation for the autonomous agent.
- Restricting file access strictly to execution subdirectories under sandbox/:
    * output/    (read/write)
    * memory/    (read/write)
    * logs/      (append/write)
    * workspace/ (read/write)
- Preventing directory traversal (../, ..\\), absolute paths, symlink escapes, and Windows junction bypasses.
- Ensuring the LLM or agent components cannot access project source code, .env, .git, or system files.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Set
from config.settings import settings


class SandboxSecurityError(PermissionError):
    """Raised when an operation attempts to violate sandbox boundaries or permissions."""
    pass


class Sandbox:
    """
    Manages and isolates all filesystem operations initiated by or on behalf of the agent.
    Guarantees that files cannot be read or written outside of designated sandbox areas.
    """

    ALLOWED_CATEGORIES: Dict[str, Set[str]] = {
        "output": {"read", "write"},
        "memory": {"read", "write"},
        "logs": {"read", "write", "append"},
        "workspace": {"read", "write"},
    }

    def __init__(self, root_dir: Path | None = None) -> None:
        """
        Initializes the sandbox and ensures all isolation directories exist.
        """
        self.root_dir: Path = (root_dir or settings.sandbox_dir).resolve()

        # Define internal category root directories
        self.categories: Dict[str, Path] = {
            "output": (self.root_dir / "output").resolve(),
            "memory": (self.root_dir / "memory").resolve(),
            "logs": (self.root_dir / "logs").resolve(),
            "workspace": (self.root_dir / "workspace").resolve(),
        }

        # Create all sandbox folders on disk if they do not exist yet
        for cat_dir in self.categories.values():
            cat_dir.mkdir(parents=True, exist_ok=True)

    def resolve_safe_path(self, category: str, relative_path: str | Path) -> Path:
        """
        Resolves a user-provided relative path within a specific sandbox category.

        Guards against:
        1. Non-existent category names.
        2. Absolute paths (e.g., C:/Windows, /etc/passwd).
        3. Directory traversal tricks (e.g., ../../../.env).
        4. Symlink or junction point escape outside the category root.
        """
        if category not in self.categories:
            raise SandboxSecurityError(
                f"Access denied: '{category}' is not an authorized sandbox category. "
                f"Valid categories are: {list(self.categories.keys())}"
            )

        category_root = self.categories[category]

        # Convert to Path object
        rel_path = Path(relative_path)

        # Reject absolute paths immediately
        if rel_path.is_absolute():
            raise SandboxSecurityError(
                f"Security violation: Absolute paths are strictly prohibited in sandbox ({relative_path})."
            )

        # Build prospective path and resolve any dots/symlinks
        target_path = (category_root / rel_path).resolve()

        # Enforce that target_path is strictly within category_root
        try:
            target_path.relative_to(category_root)
        except ValueError:
            raise SandboxSecurityError(
                f"Security violation: Path '{relative_path}' resolves outside the '{category}' sandbox "
                f"boundary to '{target_path}'."
            )

        return target_path

    def _check_permission(self, category: str, action: str) -> None:
        """
        Validates whether the requested action is permitted for the given category.
        """
        allowed_actions = self.ALLOWED_CATEGORIES.get(category, set())
        if action not in allowed_actions:
            raise SandboxSecurityError(
                f"Permission denied: Action '{action}' is not permitted in sandbox category '{category}'. "
                f"Allowed actions: {allowed_actions}"
            )

    def read_text(self, category: str, relative_path: str | Path, encoding: str = "utf-8") -> str:
        """
        Reads textual content from a sandboxed file.
        """
        self._check_permission(category, "read")
        safe_path = self.resolve_safe_path(category, relative_path)
        if not safe_path.exists():
            raise FileNotFoundError(f"File not found in sandbox '{category}': {relative_path}")
        return safe_path.read_text(encoding=encoding)

    def write_text(self, category: str, relative_path: str | Path, content: str, encoding: str = "utf-8") -> Path:
        """
        Writes textual content to a sandboxed file, creating parent directories within the category if needed.
        """
        self._check_permission(category, "write")
        safe_path = self.resolve_safe_path(category, relative_path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content, encoding=encoding)
        return safe_path

    def append_text(self, category: str, relative_path: str | Path, content: str, encoding: str = "utf-8") -> Path:
        """
        Appends textual content to a sandboxed file (e.g. log files).
        """
        self._check_permission(category, "append" if "append" in self.ALLOWED_CATEGORIES[category] else "write")
        safe_path = self.resolve_safe_path(category, relative_path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        with open(safe_path, mode="a", encoding=encoding) as f:
            f.write(content)
        return safe_path

    def read_json(self, category: str, relative_path: str | Path) -> Any:
        """
        Loads and parses JSON data from a sandboxed file.
        """
        raw_text = self.read_text(category, relative_path)
        return json.loads(raw_text)

    def write_json(self, category: str, relative_path: str | Path, data: Any, indent: int = 2) -> Path:
        """
        Serializes and writes JSON data to a sandboxed file.
        """
        content = json.dumps(data, indent=indent, ensure_ascii=False)
        return self.write_text(category, relative_path, content)

    def exists(self, category: str, relative_path: str | Path) -> bool:
        """
        Checks whether a file exists in the specified sandbox category.
        """
        try:
            safe_path = self.resolve_safe_path(category, relative_path)
            return safe_path.exists()
        except SandboxSecurityError:
            return False

    def list_files(self, category: str, pattern: str = "*") -> List[str]:
        """
        Lists files within a category matching a glob pattern, returning relative paths.
        """
        self._check_permission(category, "read")
        category_root = self.categories[category]
        results: List[str] = []
        for path in category_root.glob(pattern):
            if path.is_file():
                results.append(str(path.relative_to(category_root)).replace("\\", "/"))
        return results


# Default shared sandbox instance configured to settings.sandbox_dir
default_sandbox = Sandbox()
