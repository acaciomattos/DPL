from __future__ import annotations

import polars as pl

from policy_lab.domain import PolicyDefinition


class UncertaintyEstimator:
    def estimate(
        self,
        frame: pl.DataFrame,
        policy: PolicyDefinition,
        *,
        reference_decision_column: str,
    ) -> tuple[float, str]:
        numeric_features = [
            predicate.field
            for predicate in policy.iter_predicates()
            if predicate.field in frame.columns
            and _is_numeric_dtype(frame.schema.get(predicate.field))
        ]
        numeric_features = sorted(set(numeric_features))
        if not numeric_features:
            return 0.0, "low"

        reference_population = frame.filter(pl.col(reference_decision_column) == "approve")
        if reference_population.height == 0:
            reference_population = frame

        scenario_approved = frame.filter(pl.col(policy.decision_column) == "approve")
        if scenario_approved.height == 0:
            return 0.0, "low"

        support_expressions: list[pl.Expr] = []
        for feature_name in numeric_features:
            bounds = reference_population.select(
                [
                    pl.col(feature_name).quantile(0.05).alias("lower"),
                    pl.col(feature_name).quantile(0.95).alias("upper"),
                ]
            ).to_dicts()[0]
            lower = bounds["lower"]
            upper = bounds["upper"]
            if lower is None or upper is None:
                continue
            support_expressions.append(
                (pl.col(feature_name) < lower) | (pl.col(feature_name) > upper)
            )

        if not support_expressions:
            return 0.0, "low"

        out_of_support_ratio = (
            scenario_approved.select(pl.any_horizontal(support_expressions).mean()).item()
            or 0.0
        )
        if out_of_support_ratio >= 0.15:
            return float(out_of_support_ratio), "high"
        if out_of_support_ratio >= 0.05:
            return float(out_of_support_ratio), "medium"
        return float(out_of_support_ratio), "low"


def _is_numeric_dtype(dtype: pl.DataType | None) -> bool:
    return bool(dtype is not None and getattr(dtype, "is_numeric", lambda: False)())
