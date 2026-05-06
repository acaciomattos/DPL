from __future__ import annotations

import json

from policy_lab.domain import ScenarioDefinition, StudyContext


class ScenarioRepository:
    def save(self, study: StudyContext, scenario: ScenarioDefinition) -> None:
        path = study.study_root / "scenarios" / f"{scenario.scenario_id}.json"
        path.write_text(
            json.dumps(scenario.to_dict(), indent=2),
            encoding="utf-8",
        )

    def load_all(self, study: StudyContext) -> list[ScenarioDefinition]:
        scenarios: list[ScenarioDefinition] = []
        for path in sorted((study.study_root / "scenarios").glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            scenarios.append(ScenarioDefinition.from_dict(payload))
        return scenarios

