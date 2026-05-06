from __future__ import annotations

import json

from policy_lab.domain import ScenarioResult, StudyContext


class ResultRepository:
    def save(self, study: StudyContext, result: ScenarioResult) -> None:
        path = study.study_root / "results" / f"{result.scenario_id}.json"
        path.write_text(
            json.dumps(result.to_dict(), indent=2),
            encoding="utf-8",
        )

    def load_all(self, study: StudyContext) -> list[ScenarioResult]:
        results: list[ScenarioResult] = []
        for path in sorted((study.study_root / "results").glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            results.append(ScenarioResult.from_dict(payload))
        return results
