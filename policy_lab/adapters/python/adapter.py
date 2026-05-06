from __future__ import annotations

from typing import Any

from policy_lab.domain import PolicyDefinition


class PythonPolicyAdapter:
    """Demonstrative adapter for already-structured Python payloads."""

    adapter_name = "python"

    def normalize(self, source: dict[str, Any]) -> PolicyDefinition:
        return PolicyDefinition.from_dict(source)
