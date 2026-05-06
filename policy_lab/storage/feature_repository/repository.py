from __future__ import annotations

import json

from policy_lab.domain import DerivedFeatureDefinition, StudyContext


class FeatureRepository:
    def load(self, study: StudyContext) -> list[DerivedFeatureDefinition]:
        path = study.study_root / "derived_features.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            return [DerivedFeatureDefinition.from_dict(item) for item in payload]
        return list(study.manifest.derived_features)

    def save(
        self,
        study: StudyContext,
        features: list[DerivedFeatureDefinition],
    ) -> None:
        path = study.study_root / "derived_features.json"
        payload = [feature.to_dict() for feature in features]
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
