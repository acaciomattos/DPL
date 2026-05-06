from __future__ import annotations

import json
from typing import Any

from policy_lab.domain import StudyContext


class CreatedRuleRepository:
    def load(self, study: StudyContext) -> list[dict[str, Any]]:
        path = study.study_root / "created_rules.json"
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            entries = payload.get("rules", [])
            return [dict(entry) for entry in entries if isinstance(entry, dict)]
        if isinstance(payload, list):
            return [dict(entry) for entry in payload if isinstance(entry, dict)]
        return []

    def save(
        self,
        study: StudyContext,
        entries: list[dict[str, Any]],
    ) -> None:
        path = study.study_root / "created_rules.json"
        payload = {
            "study_id": study.study_id,
            "rules": entries,
        }
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
