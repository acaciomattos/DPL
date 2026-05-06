from __future__ import annotations

from collections.abc import Iterable

import polars as pl

from policy_lab.domain import DerivedFeatureDefinition


class FeatureResolver:
    def resolve(
        self,
        frame: pl.DataFrame,
        catalog: Iterable[DerivedFeatureDefinition],
        feature_ids: list[str] | None = None,
    ) -> pl.DataFrame:
        requested_ids = set(feature_ids or [])
        features_by_id = {feature.feature_id: feature for feature in catalog}

        ordered = self._ordered_features(features_by_id, requested_ids)
        resolved = frame
        for feature in ordered:
            if feature.name in resolved.columns:
                continue
            expression = self._compile_expression(feature.expression, resolved.columns)
            resolved = resolved.with_columns(expression.alias(feature.name))
        return resolved

    def _ordered_features(
        self,
        features_by_id: dict[str, DerivedFeatureDefinition],
        requested_ids: set[str],
    ) -> list[DerivedFeatureDefinition]:
        if not requested_ids:
            requested_ids = {
                feature_id
                for feature_id, feature in features_by_id.items()
                if feature.mode.value == "materialized"
            }

        ordered: list[DerivedFeatureDefinition] = []
        visited: set[str] = set()

        def visit(feature_id: str) -> None:
            if feature_id in visited or feature_id not in features_by_id:
                return
            feature = features_by_id[feature_id]
            for dependency in feature.dependencies:
                match = next(
                    (
                        other_id
                        for other_id, other_feature in features_by_id.items()
                        if other_feature.name == dependency
                    ),
                    None,
                )
                if match:
                    visit(match)
            visited.add(feature_id)
            ordered.append(feature)

        for feature_id in requested_ids:
            visit(feature_id)
        return ordered

    def _compile_expression(
        self,
        expression: str,
        columns: list[str],
    ) -> pl.Expr:
        env = {column: pl.col(column) for column in columns}
        env["pl"] = pl
        compiled = eval(expression, {"__builtins__": {}}, env)
        if not isinstance(compiled, pl.Expr):
            raise TypeError(f"Expression '{expression}' did not compile to a Polars expression.")
        return compiled
