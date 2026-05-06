from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from policy_lab.config import get_settings
from policy_lab.domain import StudyContext, StudyManifest


class StudyRepository:
    def __init__(self, studies_root: Path | None = None) -> None:
        self.studies_root = studies_root or get_settings().studies_root

    def list_studies(self) -> list[StudyContext]:
        contexts: list[StudyContext] = []
        for manifest_path in sorted(self.studies_root.glob("*/study.json")):
            contexts.append(self.load(manifest_path.parent.name))
        return contexts

    def load(self, study_id: str) -> StudyContext:
        study_root = self.studies_root / study_id
        manifest_path = study_root / "study.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = StudyManifest.from_dict(payload)
        return StudyContext(manifest=manifest, study_root=study_root)

    def load_snapshot(self, study: StudyContext) -> pl.DataFrame:
        snapshot_path = study.snapshot_path
        snapshot_format = study.manifest.snapshot.format.lower()
        if snapshot_format == "csv":
            frame = pl.read_csv(snapshot_path)
            return self._validate_snapshot_schema(study, frame)
        if snapshot_format == "parquet":
            frame = pl.read_parquet(snapshot_path)
            return self._validate_snapshot_schema(study, frame)
        raise ValueError(f"Unsupported snapshot format '{snapshot_format}'")

    def _validate_snapshot_schema(
        self,
        study: StudyContext,
        frame: pl.DataFrame,
    ) -> pl.DataFrame:
        required_columns = {
            study.manifest.snapshot.entity_id_column,
            study.manifest.snapshot.historical_decision_column,
            *study.manifest.snapshot.outcome_columns,
            *study.manifest.snapshot.metadata_columns,
            *study.manifest.snapshot.analysis_feature_columns,
            *study.manifest.snapshot.performance_columns.values(),
        }
        if study.manifest.snapshot.date_column:
            required_columns.add(study.manifest.snapshot.date_column)
        required_columns.update(
            predicate.field for predicate in study.manifest.baseline_policy.iter_predicates()
        )
        missing_columns = sorted(
            column for column in required_columns if column and column not in frame.columns
        )
        if missing_columns:
            raise ValueError(
                "Snapshot schema does not match the study manifest. "
                f"Study '{study.study_id}' is missing columns: {', '.join(missing_columns)}"
            )
        return frame
