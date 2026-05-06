from __future__ import annotations

import polars as pl

from policy_lab.domain import PolicyDefinition, ScenarioMetrics


class ImpactEstimator:
    def estimate(
        self,
        frame: pl.DataFrame,
        policy: PolicyDefinition,
        *,
        baseline_expected_profit: float | None = None,
        performance_columns: dict[str, str] | None = None,
    ) -> ScenarioMetrics:
        decision_column = policy.decision_column
        decision_values = set(frame.get_column(decision_column).unique().to_list())
        approved = pl.col(decision_column) == "approve"
        review = pl.col(decision_column) == "review"
        rejected = pl.col(decision_column) == "reject"
        performance_columns = performance_columns or {}
        profit_column = performance_columns.get("profit")
        risk_column = performance_columns.get("risk_event")
        churn_column = performance_columns.get("churn")

        approval_rate = frame.select(approved.mean()).item() or 0.0
        review_rate = frame.select(review.mean()).item() if "review" in decision_values else 0.0
        rejection_rate = (
            frame.select(rejected.mean()).item() if "reject" in decision_values else 0.0
        )

        if profit_column and profit_column in frame.columns:
            expected_profit = (
                frame.select(
                    pl.when(approved)
                    .then(pl.col(profit_column))
                    .otherwise(0.0)
                    .mean()
                ).item()
                or 0.0
            )
        else:
            expected_profit = None

        if expected_profit is None:
            expected_profit_index = None
        else:
            denominator = baseline_expected_profit or expected_profit or 1.0
            expected_profit_index = (expected_profit / denominator) * 100.0

        if risk_column and risk_column in frame.columns:
            risk_estimate = (
                frame.filter(approved).select(pl.col(risk_column).mean()).item() or 0.0
            )
        else:
            risk_estimate = None

        if churn_column and churn_column in frame.columns:
            churn_estimate = (
                frame.filter(approved).select(pl.col(churn_column).mean()).item() or 0.0
            )
        else:
            churn_estimate = None

        features_used = sorted({predicate.field for predicate in policy.iter_predicates()})
        return ScenarioMetrics(
            approval_rate=float(approval_rate),
            review_rate=float(review_rate),
            rejection_rate=float(rejection_rate),
            expected_profit=float(expected_profit) if expected_profit is not None else None,
            expected_profit_index=(
                float(expected_profit_index) if expected_profit_index is not None else None
            ),
            risk_estimate=float(risk_estimate) if risk_estimate is not None else None,
            churn_estimate=float(churn_estimate) if churn_estimate is not None else None,
            out_of_support_ratio=None,
            uncertainty_label=None,
            complexity_score=0.0,
            features_used=features_used,
            rules_count=len(policy.rules),
            records_evaluated=frame.height,
        )
