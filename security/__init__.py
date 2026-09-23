"""
Security package for Autonomous Job Hunter.
Exposes the Sandbox abstraction preventing arbitrary or unauthorized filesystem access.
"""

from .sandbox import Sandbox, SandboxSecurityError, default_sandbox

__all__ = ["Sandbox", "SandboxSecurityError", "default_sandbox"]
