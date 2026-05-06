from __future__ import annotations

from typing import Any, Protocol

from policy_lab.domain import PolicyDefinition


class PolicyAdapter(Protocol):
    """Normalizes policy payloads into the internal policy definition."""

    adapter_name: str

    def normalize(self, source: dict[str, Any]) -> PolicyDefinition:
        ...

